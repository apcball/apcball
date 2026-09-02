# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare


class BuzCustomerRefundVoucher(models.Model):
    _name = "buz.customer.refund.voucher"
    _description = "Customer Refund Voucher (CV)"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"
    _check_company_auto = True

    name = fields.Char(string="CV Number", required=True, copy=False, tracking=True)
    date = fields.Date(string="CV Date", default=fields.Date.context_today, required=True, tracking=True)
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company,
        tracking=True,
    )
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)
    partner_id = fields.Many2one("res.partner", string="Customer", required=True, check_company=True, tracking=True)
    credit_note_id = fields.Many2one(
        "account.move", string="Customer Credit Note", required=True, check_company=True,
        index=True, tracking=True,
        domain="[('move_type','=','out_refund'),('state','=','posted'),('company_id','=',company_id)]",
    )
    cn_amount = fields.Monetary(related="credit_note_id.amount_total", currency_field="currency_id", readonly=True)
    cn_residual = fields.Monetary(
        string="CN Residual", currency_field="currency_id", compute="_compute_cn_residual"
    )
    refund_amount = fields.Monetary(
        string="Actual Refund Amount", currency_field="currency_id", required=True, tracking=True
    )
    amount_total = fields.Monetary(related="refund_amount", currency_field="currency_id", readonly=True)
    destination_journal_id = fields.Many2one(
        "account.journal", string="Payment Journal", required=False, check_company=True,
        tracking=True, domain="[('type','in',('bank','cash')),('company_id','=',company_id)]",
    )
    payment_method_line_id = fields.Many2one(
        "account.payment.method.line", string="Payment Method", check_company=True,
        tracking=True, domain="[('payment_type','=','outbound'),('journal_id','=',destination_journal_id)]",
    )
    customer_account_id = fields.Many2one("account.account", string="Customer Account", readonly=True)
    other_income_dis = fields.Monetary(
        string="Adjustment / Write-off Amount", currency_field="currency_id",
        compute="_compute_other_income", readonly=True,
    )
    other_income_account_id = fields.Many2one(
        "account.account", string="Adjustment / Write-off Account", check_company=True,
        tracking=True, domain="[('internal_group','in',('income','expense')),('company_id','=',company_id)]",
    )
    refund_reason = fields.Text(string="Adjustment / Write-off Reason", tracking=True)
    payment_type = fields.Selection(
        [("cash", "Cash"), ("transfer", "Transfer"), ("check", "Cheque")],
        default="transfer", required=True, tracking=True,
    )
    bank_free_dis = fields.Monetary(string="Bank Fee", currency_field="currency_id")
    check_number = fields.Char(string="Cheque Number", tracking=True)
    check_date = fields.Date(string="Cheque Date", tracking=True)
    check_pay_to = fields.Char(string="Pay to", tracking=True)
    billing_note = fields.Char(string="Billing Note", tracking=True)
    note = fields.Text(string="Internal Note")
    adjustment_method = fields.Selection(
        [("writeoff", "Adjustment / Write-off"), ("keep_open", "Keep CN Residual Open")],
        default="writeoff", required=True, tracking=True,
        help="A partial refund must use Adjustment / Write-off to close the CN.",
    )
    state = fields.Selection(
        [("draft", "Draft"), ("confirmed", "Confirmed"), ("registered", "Registered"), ("cancel", "Cancelled")],
        default="draft", required=True, tracking=True, copy=False,
    )
    payment_id = fields.Many2one(
        "account.payment", string="Refund Payment", readonly=True, copy=False,
        index=True, ondelete="set null",
    )
    payment_count = fields.Integer(compute="_compute_payment_count")
    payment_status = fields.Selection(
        [("not_paid", "Not Paid"), ("paid", "Paid"), ("cancelled", "Cancelled")],
        string="Payment Status", compute="_compute_payment_status", store=True,
    )
    partner_bank_id = fields.Many2one(
        "res.partner.bank", string="Recipient Bank Account", check_company=True,
        tracking=True, domain="[('partner_id', '=', partner_id)]",
    )
    journal_entry_id = fields.Many2one(
        "account.move", string="Journal Entry", related="payment_id.move_id", readonly=True,
    )

    _sql_constraints = [
        ("cv_number_company_unique", "unique(company_id, name)", "CV Number must be unique within the company."),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            cn = self.env["account.move"].browse(vals.get("credit_note_id")).exists()
            if cn:
                self._validate_credit_note(cn)
                vals.setdefault("company_id", cn.company_id.id)
                vals.setdefault("partner_id", cn.partner_id.id)
                vals.setdefault("refund_amount", self._credit_note_residual(cn))
                vals.setdefault("customer_account_id", self._receivable_account(cn).id)
            vals.setdefault("name", self.env["ir.sequence"].next_by_code("buz.customer.refund.voucher"))
        records = super().create(vals_list)
        records._check_unique_credit_note()
        return records

    def write(self, vals):
        locked_fields = {
            "name", "company_id", "partner_id", "credit_note_id", "refund_amount",
            "destination_journal_id", "payment_method_line_id", "partner_bank_id", "other_income_account_id",
            "refund_reason", "adjustment_method", "date",
        }
        if locked_fields.intersection(vals):
            for record in self:
                if record.state != "draft":
                    raise UserError(_("Confirmed CV cannot change its number, CN, journal, amount, or adjustment data."))
        result = super().write(vals)
        if "credit_note_id" in vals:
            self._check_unique_credit_note()
        return result

    @staticmethod
    def _credit_note_residual(credit_note):
        return abs(credit_note.amount_residual_signed or credit_note.amount_residual or 0.0)

    @staticmethod
    def _receivable_account(credit_note):
        line = credit_note.line_ids.filtered(
            lambda item: item.account_id.account_type == "asset_receivable"
        )[:1]
        return line.account_id or credit_note.partner_id.property_account_receivable_id

    @api.depends("credit_note_id.amount_residual", "credit_note_id.amount_residual_signed")
    def _compute_cn_residual(self):
        for record in self:
            record.cn_residual = (
                self._credit_note_residual(record.credit_note_id)
                if record.credit_note_id else 0.0
            )

    @api.depends("cn_residual", "refund_amount")
    def _compute_other_income(self):
        for record in self:
            record.other_income_dis = max(record.cn_residual - (record.refund_amount or 0.0), 0.0)

    @api.depends("payment_id")
    @api.depends("payment_id", "payment_id.state", "state")
    def _compute_payment_status(self):
        for record in self:
            if record.payment_id and record.payment_id.state == "cancel":
                record.payment_status = "cancelled"
            elif record.payment_id:
                record.payment_status = "paid"
            else:
                record.payment_status = "not_paid"

    @api.depends("payment_id")
    def _compute_payment_count(self):
        for record in self:
            record.payment_count = bool(record.payment_id)

    @api.onchange("credit_note_id")
    def _onchange_credit_note_id(self):
        if self.credit_note_id:
            self.company_id = self.credit_note_id.company_id
            self.partner_id = self.credit_note_id.partner_id
            self.refund_amount = self._credit_note_residual(self.credit_note_id)
            self.customer_account_id = self._receivable_account(self.credit_note_id)

    @api.onchange("destination_journal_id")
    def _onchange_destination_journal_id(self):
        if self.payment_method_line_id and self.payment_method_line_id.journal_id != self.destination_journal_id:
            self.payment_method_line_id = False

    @api.constrains(
        "credit_note_id", "company_id", "partner_id", "refund_amount", "state",
        "destination_journal_id", "other_income_account_id", "refund_reason", "adjustment_method",
    )
    def _check_business_rules(self):
        for record in self:
            if not record.credit_note_id:
                continue
            self._validate_credit_note(record.credit_note_id, record.company_id)
            if record.partner_id != record.credit_note_id.partner_id:
                raise ValidationError(_("CV customer must match the Credit Note customer."))
            if record.state in ("draft", "confirmed"):
                record._validate_refund_amount(self._credit_note_residual(record.credit_note_id))
            if record.destination_journal_id and record.destination_journal_id.type not in ("bank", "cash"):
                raise ValidationError(_("Payment Journal must be Bank or Cash."))
            if record.payment_method_line_id and (
                record.payment_method_line_id.journal_id != record.destination_journal_id
                or record.payment_method_line_id.payment_type != "outbound"
            ):
                raise ValidationError(_("Payment Method must be outbound and belong to the selected journal."))
            if record.other_income_account_id and record.other_income_account_id.internal_group not in ("income", "expense"):
                raise ValidationError(_("Adjustment / Write-off Account must be Income or Expense."))

    @api.constrains("name")
    def _check_cv_number(self):
        for record in self:
            self._validate_cv_number(record.name)

    @staticmethod
    def _validate_cv_number(value):
        if not value or not value.strip():
            raise ValidationError(_("CV Number cannot be empty."))
        return True

    @classmethod
    def _validate_credit_note(cls, credit_note, company=None):
        if credit_note.move_type != "out_refund" or credit_note.state != "posted":
            raise UserError(_("Only a Posted Customer Credit Note (out_refund) can create a CV."))
        if company and credit_note.company_id != company:
            raise ValidationError(_("Credit Note and CV must belong to the same company."))
        if cls._credit_note_residual(credit_note) <= 0:
            raise UserError(_("The Credit Note must have a positive residual amount."))

    def _check_unique_credit_note(self):
        for record in self:
            duplicate = self.search([
                ("credit_note_id", "=", record.credit_note_id.id), ("id", "!=", record.id)
            ], limit=1)
            if duplicate:
                raise ValidationError(
                    _("Credit Note %s is already linked to CV %s.")
                    % (record.credit_note_id.name, duplicate.name)
                )

    def _validate_refund_amount(self, residual=None):
        self.ensure_one()
        residual = self.cn_residual if residual is None else residual
        rounding = self.currency_id.rounding if self.currency_id else 0.01
        if float_compare(self.refund_amount or 0.0, 0.0, precision_rounding=rounding) <= 0:
            raise UserError(_("Actual Refund Amount must be greater than zero."))
        if float_compare(self.refund_amount, residual, precision_rounding=rounding) > 0:
            raise UserError(_("Actual Refund Amount cannot exceed the Credit Note residual."))
        return residual

    def _validate_for_register(self):
        self.ensure_one()
        if self.state != "confirmed":
            raise UserError(_("Only a Confirmed CV can register payment."))
        if self.payment_id:
            raise UserError(_("Payment has already been registered for this CV."))
        self._validate_credit_note(self.credit_note_id, self.company_id)
        residual = self._validate_refund_amount(self._credit_note_residual(self.credit_note_id))
        difference = residual - self.refund_amount
        if float_compare(difference, 0.0, precision_rounding=self.currency_id.rounding) > 0:
            if self.adjustment_method != "writeoff":
                raise UserError(_("A partial refund must use Adjustment / Write-off."))
            if not self.other_income_account_id:
                raise UserError(_("Select an Adjustment / Write-off Account."))
            if not self.refund_reason or not self.refund_reason.strip():
                raise UserError(_("Adjustment / Write-off Reason is required."))
            if self.other_income_account_id.internal_group not in ("income", "expense"):
                raise UserError(_("Adjustment / Write-off Account must be Income or Expense."))
        return residual, difference

    def action_confirm(self):
        for record in self:
            if record.state != "draft":
                continue
            record._validate_credit_note(record.credit_note_id, record.company_id)
            record._validate_cv_number(record.name)
            record._validate_refund_amount()
            if not record.destination_journal_id:
                raise UserError(_("Select a Bank or Cash Payment Journal before confirming."))
            record.write({"state": "confirmed"})
            record.message_post(body=_("CV Confirmed."))
        return True

    def action_register_refund(self):
        self.ensure_one()
        self._validate_for_register()
        context = {
            "active_model": "account.move",
            "active_ids": [self.credit_note_id.id],
            "active_id": self.credit_note_id.id,
            "default_journal_id": self.destination_journal_id.id,
            "default_amount": self.refund_amount,
            "default_communication": self.credit_note_id.name,
            "default_ref": "CV %s" % self.name,
            "default_partner_bank_id": self.partner_bank_id.id,
            "buz_cv_id": self.id,
        }
        if self.payment_method_line_id:
            context["default_payment_method_line_id"] = self.payment_method_line_id.id
        return {
            "name": _("Register Payment"),
            "type": "ir.actions.act_window",
            "res_model": "account.payment.register",
            "view_mode": "form",
            "view_id": self.env.ref("account.view_account_payment_register_form").id,
            "target": "new",
            "context": context,
        }

    def action_print_cv(self):
        self.ensure_one()
        return self.env.ref(
            "buz_accounting_addon.action_report_buz_customer_refund_voucher"
        ).report_action(self)

    def action_open_payment(self):
        self.ensure_one()
        if not self.payment_id:
            raise UserError(_("No payment is linked to this CV."))
        return {
            "type": "ir.actions.act_window", "res_model": "account.payment",
            "view_mode": "form", "res_id": self.payment_id.id,
        }

    def action_open_credit_note(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "res_model": "account.move",
            "view_mode": "form", "res_id": self.credit_note_id.id,
        }

    def action_cancel(self):
        for record in self:
            if record.state not in ("draft", "confirmed"):
                raise UserError(_("Only Draft or Confirmed CV can be cancelled."))
            record.write({"state": "cancel"})
        return True

    def action_reset_to_draft(self):
        if not self.env.user.has_group("account.group_account_manager"):
            raise UserError(_("Only Accounting Managers can reset a CV to Draft."))
        for record in self:
            if record.payment_id:
                raise UserError(_("A CV with a registered payment cannot be reset to Draft."))
            if record.state in ("confirmed", "cancel"):
                record.write({"state": "draft"})
                record.message_post(body=_("CV reset to Draft."))
        return True
    def unlink(self):
        if any(record.state != "draft" for record in self):
            raise UserError(_("Only Draft CV can be deleted."))
        return super().unlink()



class BuzCustomerRefundVoucherLine(models.Model):
    """Legacy line model retained for ACL and existing database metadata.

    CV เน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเน€เธยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเน€เธยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเน€เธยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเน€เธยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเนยเธเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเน€เธยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเน€เธยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเน€เธยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเน€เธยเน€เธเธเธขย header เน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเนยเธเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธโฌเน€เธยเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเน€เธยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเน€เธยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเนยเธเนโฌยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเน€เธยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเน€เธยเน€เธเธเธขย Credit Note เน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเน€เธยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเนยเธเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเน€เธยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเน€เธยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเน€เธยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเน€เธยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเน€เธยเน€เธเธเธขย line เน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเน€เธยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเน€เธยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเน€เธยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเนยเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเน€เธยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเนยเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเน€เธยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเน€เธยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเนยเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเน€เธยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเน€เธยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเธขยเน€เธยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธเธเธขยเน€เธโฌเน€เธยเนยเธเน€เธโฌเน€เธยเธขยเน€เธยเนยเธเน€เธย
    """
    _name = "buz.customer.refund.voucher.line"
    _description = "Customer Refund Voucher Legacy Line"
    _check_company_auto = True

    voucher_id = fields.Many2one(
        "buz.customer.refund.voucher", required=True, ondelete="cascade", index=True
    )
    company_id = fields.Many2one(related="voucher_id.company_id", store=True, readonly=True)
    currency_id = fields.Many2one(related="voucher_id.currency_id", readonly=True)
    credit_note_id = fields.Many2one("account.move", string="Credit Note", check_company=True)
    refund_amount = fields.Monetary(currency_field="currency_id")
