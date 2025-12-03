from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class AdvanceRefillBaseWizard(models.TransientModel):
    _name = 'advance.refill.base.wizard'
    _description = 'Advance Refill to Base Wizard'

    advance_box_id = fields.Many2one(
        'employee.advance.box',
        string='Advance Box',
        required=True,
        ondelete='cascade'
    )
    current_balance = fields.Monetary(
        string='Current Balance',
        currency_field='currency_id'
    )
    base_amount_ref = fields.Monetary(
        string='Base Amount',
        currency_field='currency_id'
    )
    topup_amount = fields.Monetary(
        string='Top-up Amount',
        currency_field='currency_id'
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id
    )
    refill_method = fields.Selection([
        ('payment', 'Standard Payment (Recommended)'),
        ('journal', 'Direct Journal Entry (Legacy)')
    ], string='Refill Method', default='payment', required=True,
       help="Choose how to refill the advance box: Standard payment uses Odoo's payment system, Direct journal creates journal entry directly")

    def action_confirm(self):
        """Confirm refill using selected method"""
        self.ensure_one()
        advance_box = self.advance_box_id
        
        _logger.info("💰 REFILL DEBUG: Starting refill for box %s, employee: %s, method: %s",
                   advance_box.id, advance_box.employee_id.name, self.refill_method)
        _logger.info("💰 REFILL DEBUG: Current balance: %s, Base amount: %s, Topup: %s",
                   self.current_balance, self.base_amount_ref, self.topup_amount)

        # Check if required fields are set
        if not advance_box.account_id:
            raise UserError(_("Please set the advance account for the selected advance box."))
        if not advance_box.journal_id:
            raise UserError(_("Please set the journal for advance transactions."))
        
        if self.topup_amount <= 0:
            raise UserError(_("Top-up amount must be greater than zero."))

        if self.refill_method == 'payment':
            return self._create_payment_refill()
        else:
            return self._create_journal_refill()
    
    def _create_payment_refill(self):
        """Create refill using standard Odoo payment system"""
        advance_box = self.advance_box_id
        
        _logger.info("💳 REFILL PAYMENT: Creating payment-based refill")
        
        # Create a dummy bill to use with payment register for internal transfer
        bill_vals = {
            'move_type': 'in_invoice',
            'partner_id': advance_box._get_employee_partner(),
            'invoice_date': fields.Date.context_today(self),
            'date': fields.Date.context_today(self),
            'currency_id': self.currency_id.id,
            'company_id': advance_box.company_id.id,
            'ref': f'Advance Box Refill - {advance_box.name}',
            'line_ids': [
                (0, 0, {
                    'name': f'Advance Box Refill - {advance_box.name}',
                    'account_id': advance_box.account_id.id,
                    'price_unit': self.topup_amount,
                    'quantity': 1,
                })
            ]
        }
        
        temp_bill = self.env['account.move'].create(bill_vals)
        temp_bill.action_post()
        
        # Link to advance box
        temp_bill.write({
            'advance_box_id': advance_box.id,
            'is_expense_advance_bill': True
        })
        
        # Open payment register with context for internal transfer
        return {
            'type': 'ir.actions.act_window',
            'name': _('Register Payment'),
            'res_model': 'account.payment.register',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_model': 'account.move',
                'active_ids': [temp_bill.id],
                'default_advance_box_id': advance_box.id,
                'default_payment_type': 'outbound',
                'default_journal_id': advance_box.journal_id.id,
                'advance_box_refill': True,
                'internal_transfer_destination_account_id': advance_box.account_id.id,
                'default_amount': self.topup_amount,
            }
        }
    
    def _create_journal_refill(self):
        """Create refill using direct journal entry (legacy method)"""
        advance_box = self.advance_box_id
        
        _logger.info("📝 REFILL JOURNAL: Creating journal-based refill (legacy)")
        
        # Use the same partner resolution method as advance box and other wizards for consistency
        partner_id = advance_box._get_employee_partner()
        
        if not partner_id:
            raise UserError(_("Please set the employee's private address or ensure employee partner exists."))
            
        partner = self.env['res.partner'].browse(partner_id)
        _logger.info("💰 REFILL DEBUG: Final partner - %s (ID: %s)", partner.name, partner_id)

        # Ensure journal has sequence and create if missing
        self.env['hr.expense.advance.journal.utils'].ensure_journal_sequence(advance_box.journal_id)

        # Get credit account (default account from journal or company cash account)
        credit_account_id = advance_box.journal_id.default_account_id.id if advance_box.journal_id.default_account_id else False
        if not credit_account_id:
            # Fallback to company's cash account
            credit_account_id = self.env.company.account_journal_early_pay_discount_gain_account_id.id
            
        if not credit_account_id:
            raise UserError(_("Please set the default account for the journal or configure the company cash account."))
            
        _logger.info("💰 REFILL DEBUG: Using credit account ID: %s", credit_account_id)

        je_vals = {
            'journal_id': advance_box.journal_id.id,
            'company_id': advance_box.company_id.id or self.env.company.id,
            'move_type': 'entry',
            'date': fields.Date.context_today(self),
            'ref': f'Refill Advance to Base for {advance_box.employee_id.name}',
            'line_ids': [
                (0, 0, {
                    'account_id': advance_box.account_id.id,
                    'partner_id': partner_id,
                    'debit': self.topup_amount,
                    'credit': 0.0,
                    'name': f'Refill Advance to Base for {advance_box.employee_id.name}'
                }),
                (0, 0, {
                    'account_id': credit_account_id,
                    'debit': 0.0,
                    'credit': self.topup_amount,
                    'name': f'Refill Advance to Base for {advance_box.employee_id.name}'
                }),
            ]
        }

        # Create without explicit 'name' so the posting will assign sequence-based name
        _logger.info("💰 REFILL DEBUG: Creating journal entry with vals: %s", je_vals)
        je = self.env['account.move'].create(je_vals)
        _logger.info("💰 REFILL DEBUG: Created journal entry %s (ID: %s)", je.name, je.id)
        
        je.action_post()
        _logger.info("💰 REFILL DEBUG: Posted journal entry %s", je.name)

        # Update remember_base_amount in advance box
        advance_box.remember_base_amount = self.base_amount_ref
        _logger.info("💰 REFILL DEBUG: Updated base amount to %s", self.base_amount_ref)

        # Force refresh of the balance by triggering recomputation
        old_balance = advance_box.balance
        advance_box._trigger_balance_recompute()
        new_balance = advance_box.balance
        _logger.info("💰 REFILL DEBUG: Balance changed from %s to %s", old_balance, new_balance)

        # Log in chatter
        advance_box.message_post(
            body=_("Advance box refilled to base amount of %s. Journal entry: %s" %
                  (self.base_amount_ref, je.name))
        )

        return je