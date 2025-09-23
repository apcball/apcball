
from odoo import models, fields, _, api
from odoo.exceptions import UserError, ValidationError

class AdvanceTopupWizard(models.TransientModel):
    _name = "advance.topup.wizard"
    _description = "Top-up Employee Advance"

    employee_id = fields.Many2one(
        "hr.employee", 
        required=True,
        string="Employee"
    )
    advance_box_id = fields.Many2one(
        "employee.advance.box",
        string="Advance Box",
        domain="[('employee_id', '=', employee_id)]"
    )
    amount = fields.Monetary(
        required=True,
        string="Top-up Amount"
    )
    journal_id = fields.Many2one(
        "account.journal", 
        required=True, 
        domain=[("type", "in", ("cash", "bank"))],
        string="Payment Journal"
    )
    currency_id = fields.Many2one(
        "res.currency", 
        default=lambda self: self.env.company.currency_id,
        string="Currency"
    )
    description = fields.Char(
        string="Description",
        default="Advance Top-up",
        help="Description for journal entry"
    )
    current_balance = fields.Monetary(
        string="Current Balance",
        compute="_compute_current_balance",
        help="Current advance balance"
    )
    new_balance = fields.Monetary(
        string="New Balance",
        compute="_compute_new_balance",
        help="Balance after top-up"
    )
    date = fields.Date(
        string="Date",
        default=fields.Date.context_today,
        required=True
    )

    @api.depends("advance_box_id")
    def _compute_current_balance(self):
        for wizard in self:
            if wizard.advance_box_id:
                wizard.current_balance = wizard.advance_box_id.balance
            else:
                wizard.current_balance = 0.0

    @api.depends("current_balance", "amount")
    def _compute_new_balance(self):
        for wizard in self:
            wizard.new_balance = wizard.current_balance + (wizard.amount or 0.0)

    @api.onchange("employee_id")
    def _onchange_employee_id(self):
        if self.employee_id:
            # Find existing advance box
            advance_box = self.env["employee.advance.box"].search([
                ("employee_id", "=", self.employee_id.id),
                ("active", "=", True)
            ], limit=1)
            
            if advance_box:
                self.advance_box_id = advance_box.id
                if advance_box.journal_id:
                    self.journal_id = advance_box.journal_id.id
            else:
                self.advance_box_id = False
                
    @api.constrains("amount")
    def _check_amount(self):
        for wizard in self:
            if wizard.amount <= 0:
                raise ValidationError(_("Top-up amount must be positive."))

    def action_topup(self):
        """Create journal entry for advance top-up"""
        self.ensure_one()
        
        # Validations
        if self.amount <= 0:
            raise UserError(_("Amount must be positive."))
            
        partner = self.employee_id.user_partner_id
        if not partner:
            raise UserError(_("Employee %s has no Private Address (partner).") % self.employee_id.name)
            
        # Get or create advance box
        if not self.advance_box_id:
            self.advance_box_id = self.env["employee.advance.box"].create_for_employee(self.employee_id.id)
            
        if not self.advance_box_id.account_id:
            raise UserError(_("Please set Advance Account in the Advance Box."))

        # Get journal's default account
        default_acc = self.journal_id.default_account_id
        if not default_acc:
            # Try to get payment debit account
            default_acc = self.journal_id.payment_debit_account_id
            
        if not default_acc:
            raise UserError(_("Journal %s must have a default account.") % self.journal_id.name)

        # Create journal entry
        move_vals = {
            "move_type": "entry",
            "journal_id": self.journal_id.id,
            "date": self.date,
            "ref": f"Advance Top-up: {self.employee_id.name}",
            "line_ids": [
                # Dr: Employee Advance Account
                (0, 0, {
                    "name": self.description or _("Advance Top-up"),
                    "account_id": self.advance_box_id.account_id.id,
                    "debit": self.amount,
                    "credit": 0.0,
                    "partner_id": partner.id,
                }),
                # Cr: Bank/Cash Account
                (0, 0, {
                    "name": f"{self.journal_id.name} - {self.description or _('Advance Top-up')}",
                    "account_id": default_acc.id,
                    "debit": 0.0,
                    "credit": self.amount,
                    "partner_id": False,  # Bank account usually has no partner
                }),
            ]
        }
        
        move = self.env["account.move"].create(move_vals)
        
        # Post the move
        try:
            move.action_post()
        except Exception as e:
            raise UserError(_("Failed to post journal entry: %s") % str(e))

        # Add message to advance box
        self.advance_box_id.message_post(
            body=_("Advance top-up of %s %s posted. New balance: %s") % (
                self.amount,
                self.currency_id.symbol,
                self.new_balance
            )
        )

        # Return action to view the created journal entry
        return {
            "type": "ir.actions.act_window",
            "name": _("Journal Entry"),
            "res_model": "account.move",
            "res_id": move.id,
            "view_mode": "form",
            "target": "current",
        }
