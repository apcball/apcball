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
                # Clear all balance - final balance is always 0
                wizard.final_balance = 0.0
            else:
                wizard.final_balance = wizard.current_balance

    @api.onchange("settlement_type", "current_balance")
    def _onchange_settlement_type(self):
        if self.settlement_type == "clear":
            # For clear type, amount should be absolute value of current balance
            self.amount = abs(self.current_balance or 0.0)
        elif self.settlement_type == "return" and self.current_balance > 0:
            # For return type, suggest returning all positive balance
            self.amount = self.current_balance
        elif self.settlement_type == "pay" and self.current_balance < 0:
            # For pay type, suggest paying all negative balance
            self.amount = abs(self.current_balance)
        else:
            # Reset amount for other cases
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

    @api.constrains("amount", "settlement_type", "current_balance")
    def _check_amount(self):
        for wizard in self:
            if wizard.amount < 0:
                raise ValidationError(_("Settlement amount cannot be negative."))
            
            # For return and pay types, amount must be positive
            if wizard.settlement_type in ("return", "pay") and wizard.amount <= 0:
                raise ValidationError(_("Settlement amount must be positive."))
            
            # For clear type, amount must match the absolute current balance
            if wizard.settlement_type == "clear":
                expected_amount = abs(wizard.current_balance or 0.0)
                if expected_amount > 0 and abs(wizard.amount - expected_amount) > 0.01:
                    raise ValidationError(
                        _("For clearing settlement, amount must equal the absolute current balance (%s).") % expected_amount
                    )
                elif expected_amount == 0 and wizard.amount != 0:
                    raise ValidationError(_("No balance to clear."))

    def get_formview_id(self, access_uid=None):
        """Override to use custom form view without save button"""
        return self.env.ref('hr_expense_advance_clearing.view_advance_settlement_wizard').id

    def action_settle(self):
        """Create journal entry for advance settlement - Simple Implementation"""
        import logging
        _logger = logging.getLogger(__name__)
        _logger.info("=== ACTION_SETTLE CALLED ===")
        
        self.ensure_one()
        
        # Basic validation
        if not self.amount or self.amount <= 0:
            from odoo.exceptions import UserError
            raise UserError("กรุณากำหนดจำนวนเงินที่ต้องการ settlement")
            
        partner = self.employee_id.user_partner_id
        if not partner:
            from odoo.exceptions import UserError
            raise UserError("ไม่พบข้อมูล partner ของพนักงาน %s" % self.employee_id.name)
            
        # Get accounts
        advance_account = self.advance_box_id.account_id
        bank_account = self.journal_id.default_account_id
        
        if not bank_account:
            bank_account = self.journal_id.payment_debit_account_id
            
        if not advance_account or not bank_account:
            from odoo.exceptions import UserError
            raise UserError("ไม่พบ account ที่จำเป็นสำหรับการทำ journal entry")
        
        # Create simple journal entry based on settlement type
        if self.settlement_type == "clear" or self.settlement_type == "return":
            # Employee returns advance: Dr Bank, Cr Advance (ตาม README)
            move_lines = [
                (0, 0, {
                    'name': f'Settlement: {self.employee_id.name}',
                    'account_id': bank_account.id,
                    'debit': self.amount,
                    'credit': 0.0,
                    'partner_id': False,
                }),
                (0, 0, {
                    'name': f'Clear Advance: {self.employee_id.name}',
                    'account_id': advance_account.id,
                    'debit': 0.0,
                    'credit': self.amount,
                    'partner_id': partner.id,
                }),
            ]
        else:  # pay type
            # Company pays employee: Dr Advance, Cr Bank (ตาม README)
            move_lines = [
                (0, 0, {
                    'name': f'Pay to Employee: {self.employee_id.name}',
                    'account_id': advance_account.id,
                    'debit': self.amount,
                    'credit': 0.0,
                    'partner_id': partner.id,
                }),
                (0, 0, {
                    'name': f'Payment: {self.employee_id.name}',
                    'account_id': bank_account.id,
                    'debit': 0.0,
                    'credit': self.amount,
                    'partner_id': False,
                }),
            ]
        
        # Create and post journal entry
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': self.journal_id.id,
            'date': self.date,
            'ref': f'Advance Settlement: {self.employee_id.name}',
            'line_ids': move_lines,
        })
        
        # Post the move
        move.action_post()
        _logger.info("Settlement posted successfully: %s", move.name)
        
        # Return success message
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Settlement สำเร็จ!',
                'message': f'สร้าง Journal Entry {move.name} เรียบร้อยแล้ว',
                'type': 'success',
            }
        }
            
        if not default_acc:
            raise UserError(_("Journal %s must have a default account.") % self.journal_id.name)

        # Store initial balance for comparison
        initial_balance = self.current_balance

        # Create journal entry based on settlement type
        move_vals = self._prepare_settlement_move(partner, default_acc)
        move = self.env["account.move"].create(move_vals)
        
        # Post the move
        try:
            move.action_post()
        except Exception as e:
            raise UserError(_("Failed to post journal entry: %s") % str(e))

        # Ensure all database operations are flushed before reading balance
        self.env.flush_all()
        
        # Log settlement details for debugging
        import logging
        _logger = logging.getLogger(__name__)
        _logger.info("Settlement posted: Move %s, Type: %s, Amount: %s", 
                   move.name, self.settlement_type, self.amount)
        
        # Force refresh the advance box balance
        self.advance_box_id.invalidate_recordset(['balance'])
        # Re-read the advance box to get updated balance
        updated_box = self.env['employee.advance.box'].browse(self.advance_box_id.id)
        updated_balance = updated_box.balance
        
        _logger.info("Balance after settlement: Previous %s, Updated %s", 
                   initial_balance, updated_balance)
        
        # Add detailed message to advance box
        settlement_name = dict(self._fields["settlement_type"].selection)[self.settlement_type]
        message_body = _("""
            <p><strong>Advance Settlement Completed</strong></p>
            <ul>
                <li>Settlement Type: %s</li>
                <li>Amount: %s %s</li>
                <li>Previous Balance: %s %s</li>
                <li>Updated Balance: %s %s</li>
                <li>Journal Entry: %s</li>
            </ul>
        """) % (
            settlement_name,
            self.amount, self.currency_id.symbol,
            initial_balance, self.currency_id.symbol,
            updated_balance, self.currency_id.symbol,
            move.name
        )
        
        self.advance_box_id.message_post(body=message_body)

        # For clear settlement, verify the balance is actually zero or close to zero
        if self.settlement_type == "clear" and abs(updated_balance) > 0.01:
            # Log a warning but don't raise an error as there might be rounding differences
            import logging
            _logger = logging.getLogger(__name__)
            _logger.warning("Settlement marked as 'clear' but balance is not zero: %s", updated_balance)
        
        # Return success notification with option to view journal entry
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Settlement Completed"),
                "message": _("Settlement completed successfully! Updated balance: %s %s") % (
                    updated_balance, self.currency_id.symbol
                ),
                "type": "success",
                "sticky": False,
                "next": {
                    "type": "ir.actions.act_window",
                    "name": _("Settlement Journal Entry"),
                    "res_model": "account.move",
                    "res_id": move.id,
                    "view_mode": "form",
                    "target": "current",
                }
            }
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