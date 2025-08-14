# Copyright 2019 Kitti Upariphutthiphong <kittiu@ecosoft.co.th>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import Command, _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import float_compare, float_is_zero
from odoo.tools.safe_eval import safe_eval


class HrExpenseSheet(models.Model):
    _inherit = "hr.expense.sheet"

    advance = fields.Boolean(
        string="Employee Advance",
    )
    advance_sheet_id = fields.Many2one(
        comodel_name="hr.expense.sheet",
        string="Clear Advance",
        domain="[('advance', '=', True), ('employee_id', '=', employee_id),"
        " ('clearing_residual', '>', 0.0)]",
        readonly=True,
        states={
            "draft": [("readonly", False)],
            "submit": [("readonly", False)],
            "approve": [("readonly", False)],
        },
        help="Show remaining advance of this employee",
    )
    clearing_sheet_ids = fields.One2many(
        comodel_name="hr.expense.sheet",
        inverse_name="advance_sheet_id",
        string="Clearing Sheet",
        readonly=True,
        help="Show reference clearing on advance",
    )
    clearing_count = fields.Integer(
        compute="_compute_clearing_count",
    )
    clearing_residual = fields.Monetary(
        string="Amount to clear",
        compute="_compute_clearing_residual",
        store=True,
        help="Amount to clear of this expense sheet in company currency",
    )
    advance_sheet_residual = fields.Monetary(
        string="Advance Remaining",
        related="advance_sheet_id.clearing_residual",
        store=True,
        help="Remaining amount to clear the selected advance sheet",
    )
    amount_payable = fields.Monetary(
        string="Payable Amount",
        compute="_compute_amount_payable",
        help="Final regiter payment amount even after advance clearing",
    )

    @api.constrains("advance_sheet_id", "expense_line_ids")
    def _check_advance_expense(self):
        advance_lines = self.expense_line_ids.filtered("advance")
        if self.advance_sheet_id and advance_lines:
            raise ValidationError(
                _("Advance clearing must not contain any advance expense line")
            )
        if advance_lines and len(advance_lines) != len(self.expense_line_ids):
            raise ValidationError(_("Advance must contain only advance expense line"))

    @api.depends("account_move_ids.payment_state")
    def _compute_payment_state(self):
        """After clear advance.
        if amount residual is zero, payment state will change to 'paid'
        """
        super()._compute_payment_state()
        for sheet in self:
            if (
                sheet.advance_sheet_id
                and sheet.account_move_ids
                and sheet.account_move_ids[:1].state == "posted"
                and sheet.state in ("post", "done")
            ):
                # Check if all move lines are reconciled
                move_lines = sheet.account_move_ids.line_ids.filtered(
                    lambda l: l.account_id.account_type == 'liability_payable'
                )
                if all(line.reconciled for line in move_lines):
                    sheet.payment_state = "paid"

    def _get_product_advance(self):
        return self.env.ref("hr_expense_advance_clearing.product_emp_advance", False)

    @api.depends("account_move_ids.line_ids.amount_residual")
    def _compute_clearing_residual(self):
        for sheet in self:
            emp_advance = sheet._get_product_advance()
            residual_company = 0.0
            if emp_advance:
                property_account_expense_id = emp_advance.with_company(
                    sheet.company_id
                ).property_account_expense_id
                for line in sheet.sudo().account_move_ids.line_ids:
                    if line.account_id == property_account_expense_id:
                        residual_company += line.amount_residual
            sheet.clearing_residual = residual_company

    def _compute_amount_payable(self):
        for sheet in self:
            rec_lines = sheet.account_move_ids.line_ids.filtered(
                lambda x: x.credit and x.account_id.reconcile and not x.reconciled
            )
            sheet.amount_payable = -sum(rec_lines.mapped("amount_residual"))

    def _compute_clearing_count(self):
        for sheet in self:
            sheet.clearing_count = len(sheet.clearing_sheet_ids)

    def action_sheet_move_create(self):
        res = super().action_sheet_move_create()
        for sheet in self:
            if not sheet.advance_sheet_id:
                continue
            amount_residual_bf_reconcile = sheet.advance_sheet_residual
            advance_residual = float_compare(
                amount_residual_bf_reconcile,
                sheet.total_amount,
                precision_rounding=sheet.currency_id.rounding,
            )
            move_lines = (
                sheet.account_move_ids.line_ids
                | sheet.advance_sheet_id.account_move_ids.line_ids
            )
            emp_advance = sheet._get_product_advance()
            account_id = emp_advance.property_account_expense_id.id
            adv_move_lines = (
                self.env["account.move.line"]
                .sudo()
                .search(
                    [
                        ("id", "in", move_lines.ids),
                        ("account_id", "=", account_id),
                        ("reconciled", "=", False),
                    ]
                )
            )
            adv_move_lines.reconcile()
            # Update state on clearing advance when advance residual > total amount
            if advance_residual != -1:
                sheet.write(
                    {
                        "state": "done",
                    }
                )
            # Update amount residual and state when advance residual < total amount
            else:
                # Calculate remaining amount to pay
                remaining_amount = sheet.total_amount - amount_residual_bf_reconcile
                sheet.write(
                    {
                        "state": "post",
                        "payment_state": "not_paid",
                    }
                )
        return res

    def _get_move_line_vals(self):
        self.ensure_one()
        move_line_vals = []
        advance_to_clear = self.advance_sheet_residual
        emp_advance = self._get_product_advance()
        account_advance = emp_advance.property_account_expense_id
        for expense in self.expense_line_ids:
            move_line_name = (
                expense.employee_id.name + ": " + expense.name.split("\n")[0][:64]
            )
            total_amount = 0.0
            total_amount_currency = 0.0
            partner_id = (
                expense.employee_id.sudo().address_home_id.commercial_partner_id.id
            )
            # source move line
            move_line_src = expense._get_move_line_src(move_line_name, partner_id)
            move_line_values = [move_line_src]
            total_amount -= expense.total_amount_company
            total_amount_currency -= expense.total_amount

            # destination move line
            move_line_dst = expense._get_move_line_dst(
                move_line_name,
                partner_id,
                total_amount,
                total_amount_currency,
                account_advance,
            )
            # Check clearing > advance, it will split line
            credit = move_line_dst["credit"]
            # cr payable -> cr advance
            remain_payable = 0.0
            payable_move_line = []
            rounding = expense.currency_id.rounding
            if (
                float_compare(
                    credit,
                    advance_to_clear,
                    precision_rounding=rounding,
                )
                == 1
            ):
                remain_payable = credit - advance_to_clear
                move_line_dst["credit"] = advance_to_clear
                move_line_dst["amount_currency"] = -advance_to_clear
                advance_to_clear = 0.0
                # extra payable line
                payable_move_line = move_line_dst.copy()
                payable_move_line["credit"] = remain_payable
                payable_move_line["amount_currency"] = -remain_payable
                payable_move_line[
                    "account_id"
                ] = expense._get_expense_account_destination()
            else:
                advance_to_clear -= credit
            # Add destination first (if credit is not zero)
            if not float_is_zero(move_line_dst["credit"], precision_rounding=rounding):
                move_line_values.append(move_line_dst)
            if payable_move_line:
                move_line_values.append(payable_move_line)
            move_line_vals.extend(move_line_values)
        return move_line_vals

    def _prepare_bill_vals(self):
        """create journal entry instead of bills when clearing document"""
        self.ensure_one()
        res = super()._prepare_bill_vals()
        if self.advance_sheet_id and self.payment_mode == "own_account":
            if (
                self.advance_sheet_residual <= 0.0
            ):  # Advance Sheets with no residual left
                raise ValidationError(
                    _("Advance: %s has no amount to clear") % (self.name)
                )
            res["move_type"] = "entry"
            move_line_vals = self._get_move_line_vals()
            res["line_ids"] = [Command.create(x) for x in move_line_vals]
        return res

    def open_clear_advance(self):
        self.ensure_one()
        action = self.env.ref(
            "hr_expense_advance_clearing.action_hr_expense_sheet_advance_clearing"
        )
        vals = action.sudo().read()[0]
        context1 = vals.get("context", {})
        if context1:
            context1 = safe_eval(context1)
        context1["default_advance_sheet_id"] = self.id
        context1["default_employee_id"] = self.employee_id.id
        vals["context"] = context1
        return vals

    def get_domain_advance_sheet_expense_line(self):
        return self.advance_sheet_id.expense_line_ids.filtered("clearing_product_id")

    @api.onchange("advance_sheet_id")
    def _onchange_advance_sheet_id(self):
        # Clear existing auto-generated lines
        if hasattr(self, '_origin') and self._origin.id:
            # For existing records, remove only auto-generated lines
            self.expense_line_ids = [(6, 0, [
                line.id for line in self.expense_line_ids 
                if not line.av_line_id
            ])]
        else:
            # For new records, clear all lines that reference advance lines
            self.expense_line_ids = [(5, 0, 0)]  # Clear all
        
        if self.advance_sheet_id:
            # Get advance lines that have clearing products
            advance_lines = self.advance_sheet_id.expense_line_ids.filtered('clearing_product_id')
            
            # Create clearing lines
            expense_lines = []
            for line in advance_lines:
                clearing_vals = self._prepare_clear_advance(line)
                expense_lines.append((0, 0, clearing_vals))
            
            if expense_lines:
                self.expense_line_ids = expense_lines

    def _prepare_clear_advance(self, line):
        # Prepare the clearing expense based on advance line
        vals = {
            'advance': False,
            'name': line.clearing_product_id.display_name or line.name,
            'product_id': line.clearing_product_id.id if line.clearing_product_id else line.product_id.id,
            'clearing_product_id': False,
            'date': fields.Date.context_today(self),
            'employee_id': self.employee_id.id,
            'company_id': self.company_id.id,
            'currency_id': line.currency_id.id,
            'av_line_id': line.id,
            'unit_amount': line.unit_amount,
            'quantity': line.quantity,
            'total_amount': line.total_amount,
            'payment_mode': line.payment_mode,
        }
        
        # Set account based on product
        if line.clearing_product_id:
            product = line.clearing_product_id
        else:
            product = line.product_id
            
        if product:
            account = product._get_product_accounts()['expense']
            if account:
                vals['account_id'] = account.id
        
        return vals

    def action_open_clearings(self):
        self.ensure_one()
        return {
            "name": _("Clearing Sheets"),
            "type": "ir.actions.act_window",
            "res_model": "hr.expense.sheet",
            "view_mode": "tree,form",
            "domain": [("id", "in", self.clearing_sheet_ids.ids)],
        }

    def action_register_payment(self):
        action = super().action_register_payment()
        if self.env.context.get("hr_return_advance"):
            action["context"].update(
                {
                    "clearing_sheet_ids": self.clearing_sheet_ids.ids,
                }
            )
        return action
