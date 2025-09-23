from odoo import models, fields, _, api
from odoo.exceptions import UserError, ValidationError

class AdvanceSettlementWizard(models.TransientModel):
    _name = "advance.settlement.wizard"
    _description = "Settle Employee Advance"

    employee_id = fields.Many2one(
        "hr.employee", 
        required=True,
        string="Employee"
    )
    advance_box_id = fields.Many2one(
        "employee.advance.box",
        string="Advance Box",
        domain="[('employee_id', '=', employee_id)]",
        required=True
    )
    current_balance = fields.Monetary(
        string="Current Balance",
        help="Current advance balance (positive = employee has advance, negative = company owes employee)"
    )
    settlement_type = fields.Selection([
        ("return", "Employee Returns Excess"),
        ("pay", "Company Pays Difference"),
        ("clear", "Clear All Balance")
    ], string="Settlement Type", required=True)
    
    amount = fields.Monetary(
        string="Settlement Amount",
        help="Amount to settle"
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
        default="Advance Settlement",
        help="Description for journal entry"
    )
    date = fields.Date(
        string="Date",
        default=fields.Date.context_today,
        required=True
    )
    final_balance = fields.Monetary(
        string="Final Balance",
        compute="_compute_final_balance",
        help="Expected balance after settlement"
    )

    @api.depends("current_balance", "amount", "settlement_type")
    def _compute_final_balance(self):
        for wizard in self:
            if wizard.settlement_type == "return":
                # Employee returns money, reduces their advance
                wizard.final_balance = wizard.current_balance - (wizard.amount or 0.0)
            elif wizard.settlement_type == "pay":
                # Company pays employee, increases their advance (or reduces negative balance)
                wizard.final_balance = wizard.current_balance + (wizard.amount or 0.0)
            elif wizard.settlement_type == "clear":
                # Clear all balance
                wizard.final_balance = 0.0
                wizard.amount = abs(wizard.current_balance)
            else:
                wizard.final_balance = wizard.current_balance

    @api.onchange("settlement_type", "current_balance")
    def _onchange_settlement_type(self):
        if self.settlement_type == "clear":
            self.amount = abs(self.current_balance)
        elif self.settlement_type == "return" and self.current_balance > 0:
            self.amount = self.current_balance
        elif self.settlement_type == "pay" and self.current_balance < 0:
            self.amount = abs(self.current_balance)
        else:
            self.amount = 0.0

    @api.onchange("employee_id")
    def _onchange_employee_id(self):
        if self.employee_id:
            advance_box = self.env["employee.advance.box"].search([
                ("employee_id", "=", self.employee_id.id),
                ("active", "=", True)
            ], limit=1)
            
            if advance_box:
                self.advance_box_id = advance_box.id
                self.current_balance = advance_box.balance
                if advance_box.journal_id:
                    self.journal_id = advance_box.journal_id.id
                    
                # Auto-suggest settlement type
                if advance_box.balance > 0:
                    self.settlement_type = "return"
                elif advance_box.balance < 0:
                    self.settlement_type = "pay"
                else:
                    self.settlement_type = "clear"
            else:
                self.advance_box_id = False
                self.current_balance = 0.0

    @api.constrains("amount")
    def _check_amount(self):
        for wizard in self:
            if wizard.amount < 0:
                raise ValidationError(_("Settlement amount cannot be negative."))
            if wizard.settlement_type in ("return", "pay") and wizard.amount <= 0:
                raise ValidationError(_("Settlement amount must be positive."))

    def action_settle(self):
        """Create journal entry for advance settlement"""
        self.ensure_one()
        
        if not self.amount:
            raise UserError(_("Please specify settlement amount."))
            
        partner = self.employee_id.user_partner_id
        if not partner:
            raise UserError(_("Employee %s has no Private Address (partner).") % self.employee_id.name)
            
        if not self.advance_box_id.account_id:
            raise UserError(_("Please set Advance Account in the Advance Box."))

        # Get journal's default account
        default_acc = self.journal_id.default_account_id
        if not default_acc:
            default_acc = self.journal_id.payment_debit_account_id
            
        if not default_acc:
            raise UserError(_("Journal %s must have a default account.") % self.journal_id.name)

        # Create journal entry based on settlement type
        move_vals = self._prepare_settlement_move(partner, default_acc)
        move = self.env["account.move"].create(move_vals)
        
        # Post the move
        try:
            move.action_post()
        except Exception as e:
            raise UserError(_("Failed to post journal entry: %s") % str(e))

        # Add message to advance box
        self.advance_box_id.message_post(
            body=_("Advance settlement: %s of %s %s. Final balance: %s") % (
                dict(self._fields["settlement_type"].selection)[self.settlement_type],
                self.amount,
                self.currency_id.symbol,
                self.final_balance
            )
        )

        # Return action to view the created journal entry
        return {
            "type": "ir.actions.act_window",
            "name": _("Settlement Journal Entry"),
            "res_model": "account.move",
            "res_id": move.id,
            "view_mode": "form",
            "target": "current",
        }

    def _prepare_settlement_move(self, partner, bank_account):
        """Prepare journal entry values for settlement"""
        advance_account = self.advance_box_id.account_id
        
        if self.settlement_type == "return":
            # Employee returns excess advance
            # Dr: Bank/Cash, Cr: Employee Advance
            line_ids = [
                (0, 0, {
                    "name": f"{self.description} - Receipt",
                    "account_id": bank_account.id,
                    "debit": self.amount,
                    "credit": 0.0,
                    "partner_id": False,
                }),
                (0, 0, {
                    "name": f"{self.description} - Return",
                    "account_id": advance_account.id,
                    "debit": 0.0,
                    "credit": self.amount,
                    "partner_id": partner.id,
                }),
            ]
        elif self.settlement_type == "pay":
            # Company pays additional amount to employee
            # Dr: Employee Advance, Cr: Bank/Cash
            line_ids = [
                (0, 0, {
                    "name": f"{self.description} - Additional Payment",
                    "account_id": advance_account.id,
                    "debit": self.amount,
                    "credit": 0.0,
                    "partner_id": partner.id,
                }),
                (0, 0, {
                    "name": f"{self.description} - Payment",
                    "account_id": bank_account.id,
                    "debit": 0.0,
                    "credit": self.amount,
                    "partner_id": False,
                }),
            ]
        else:  # clear
            # Clear balance (could be either direction)
            if self.current_balance > 0:
                # Employee returns all advance
                line_ids = [
                    (0, 0, {
                        "name": f"{self.description} - Final Return",
                        "account_id": bank_account.id,
                        "debit": self.amount,
                        "credit": 0.0,
                        "partner_id": False,
                    }),
                    (0, 0, {
                        "name": f"{self.description} - Clear Balance",
                        "account_id": advance_account.id,
                        "debit": 0.0,
                        "credit": self.amount,
                        "partner_id": partner.id,
                    }),
                ]
            else:
                # Company pays final amount
                line_ids = [
                    (0, 0, {
                        "name": f"{self.description} - Final Payment",
                        "account_id": advance_account.id,
                        "debit": self.amount,
                        "credit": 0.0,
                        "partner_id": partner.id,
                    }),
                    (0, 0, {
                        "name": f"{self.description} - Clear Balance",
                        "account_id": bank_account.id,
                        "debit": 0.0,
                        "credit": self.amount,
                        "partner_id": False,
                    }),
                ]

        return {
            "move_type": "entry",
            "journal_id": self.journal_id.id,
            "date": self.date,
            "ref": f"Advance Settlement: {self.employee_id.name}",
            "line_ids": line_ids
        }