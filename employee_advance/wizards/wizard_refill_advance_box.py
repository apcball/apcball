# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class WizardRefillAdvanceBox(models.TransientModel):
    _name = 'wizard.refill.advance.box'
    _description = 'Wizard: Refill Advance Box'

    box_id = fields.Many2one(
        'employee.advance.box',
        string='Advance Box',
        required=True,
        help='Select the advance box to refill'
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        related='box_id.employee_id',
        readonly=True
    )
    
    # Accounting fields
    debit_account_id = fields.Many2one(
        'account.account',
        string='Account',
        required=False,
        domain="[('deprecated', '=', False), ('company_id', '=', company_id)]",
        default=lambda self: self._default_debit_account(),
        help='Account to debit (usually 113001 - Advance Payment)'
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Journal',
        required=False,
        domain=[('type', 'in', ['bank', 'cash'])],
        help='Journal for the transaction'
    )
    credit_account_id = fields.Many2one(
        'account.account',
        string='Credit Account (Bank)',
        compute='_compute_credit_account',
        store=True,
        readonly=False,
        domain="[('deprecated', '=', False), ('company_id', '=', company_id)]",
        help='Bank account to credit (from journal default account)'
    )
    
    # Legacy fields for backward compatibility
    journal_bank_id = fields.Many2one(
        'account.journal',
        string='Bank Journal (Legacy)',
        domain=[('type', '=', 'bank')],
        help='Legacy field - use journal_id instead'
    )
    destination_journal_id = fields.Many2one(
        'account.journal',
        string='Destination Journal',
        compute='_compute_destination_journal',
        store=True,
        readonly=True,
        help='Journal of the advance box (automatically set)'
    )
    
    amount = fields.Monetary(
        string='Amount',
        required=False,
        currency_field='currency_id',
        help='Amount to refill into the advance box'
    )
    date = fields.Date(
        string='Date',
        required=True,
        default=fields.Date.context_today,
        help='Date of the refill transaction'
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id,
        required=True
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )
    notes = fields.Text(string='Notes')
    current_balance = fields.Monetary(
        string='Current Balance',
        related='box_id.balance',
        readonly=True,
        currency_field='currency_id'
    )
    base_amount = fields.Monetary(
        string='Base Amount',
        related='box_id.remember_base_amount',
        readonly=True,
        currency_field='currency_id'
    )

    @api.model
    def _default_debit_account(self):
        """Default to account 113001"""
        account = self.env['account.account'].search([
            ('code', '=like', '113001%'),
            ('company_id', '=', self.env.company.id)
        ], limit=1)
        return account

    @api.depends('journal_id')
    def _compute_credit_account(self):
        """Set credit account from journal's default account"""
        for wizard in self:
            if wizard.journal_id and wizard.journal_id.default_account_id:
                wizard.credit_account_id = wizard.journal_id.default_account_id

    @api.depends('box_id', 'box_id.journal_id')
    def _compute_destination_journal(self):
        for wizard in self:
            wizard.destination_journal_id = wizard.box_id.journal_id if wizard.box_id else False

    @api.constrains('amount')
    def _check_amount(self):
        for wizard in self:
            if wizard.amount <= 0:
                raise ValidationError(_('Amount must be greater than zero.'))

    @api.constrains('box_id', 'journal_bank_id')
    def _check_journals(self):
        for wizard in self:
            if wizard.box_id and wizard.box_id.journal_id and wizard.journal_bank_id:
                if wizard.box_id.journal_id.id == wizard.journal_bank_id.id:
                    raise ValidationError(_('Source and destination journals must be different.'))

    @api.onchange('box_id')
    def _onchange_box_id(self):
        """Set destination journal when box is selected"""
        if self.box_id and self.box_id.journal_id:
            self.destination_journal_id = self.box_id.journal_id

    bank_charge_amount = fields.Monetary(
        string='Bank Charges (THB)',
        currency_field='bank_charge_currency_id',
        default=0.0
    )
    bank_charge_currency_id = fields.Many2one(
        'res.currency',
        string='Bank Charge Currency',
        default=lambda self: self.env.ref('base.THB'),
        required=True
    )

    def action_confirm_refill(self):
        """
        Confirm the refill using simple journal entry:
        Debit: 113001 เงินทดรองจ่าย
        Debit: Bank Charges (if any)
        Credit: Bank account (Total)
        """
        self.ensure_one()
        
        # Validate required fields
        if not self.journal_id:
            raise UserError(_('Please select a bank journal.'))
        
        if not self.debit_account_id:
            raise UserError(_('Please configure advance account (113001).'))
        
        if not self.amount or self.amount <= 0:
            raise UserError(_('Amount must be greater than zero.'))

        # Validate bank charges
        if self.bank_charge_amount > 0 and not self.journal_id.default_bank_charge_account_id:
            raise UserError(_('Please configure Bank Charge Account on the selected journal "%s".') % self.journal_id.name)

        try:
            # Get employee partner
            partner_id = self.box_id._get_employee_partner()
            if not partner_id:
                raise UserError(_('Cannot find partner for employee "%s". Please set the employee\'s private address.') % self.box_id.employee_id.name)
            
            # Verify partner exists
            partner = self.env['res.partner'].browse(partner_id)
            if not partner.exists():
                raise UserError(_('Partner ID %s does not exist in the system.') % partner_id)
            
            _logger.info('✅ Using partner: %s (ID: %s) for employee: %s', 
                        partner.name, partner_id, self.box_id.employee_id.name)
            
            # Get credit account from journal
            if not self.credit_account_id:
                if self.journal_id.default_account_id:
                    self.credit_account_id = self.journal_id.default_account_id
                else:
                    raise UserError(_('Cannot determine bank account. Please set default account for journal "%s".') % self.journal_id.name)
            
            # Calculate validation amounts
            bank_charge_converted = 0.0
            if self.bank_charge_amount > 0:
                if self.bank_charge_currency_id != self.company_id.currency_id:
                    bank_charge_converted = self.bank_charge_currency_id._convert(
                        self.bank_charge_amount,
                        self.company_id.currency_id,
                        self.company_id,
                        self.date
                    )
                else:
                    bank_charge_converted = self.bank_charge_amount

            total_credit = self.amount + bank_charge_converted

            # Create journal entry
            _logger.info('📝 Creating journal entry: Debit %s (Amount: %.2f), Debit Charges (%.2f), Credit %s (Total: %.2f)',
                        self.debit_account_id.code, self.amount, bank_charge_converted,
                        self.credit_account_id.code, total_credit)
            
            line_ids = [
                (0, 0, {
                    'account_id': self.debit_account_id.id,
                    'partner_id': partner_id,
                    'debit': self.amount,
                    'credit': 0.0,
                    'name': _('Transfer from %s') % self.journal_id.name
                })
            ]

            # Add bank charge line if exists
            if self.bank_charge_amount > 0:
                line_ids.append((0, 0, {
                    'account_id': self.journal_id.default_bank_charge_account_id.id,
                    'partner_id': partner_id,
                    'debit': bank_charge_converted,
                    'credit': 0.0,
                    'name': _('Bank Charges')
                }))

            # Credit line (Total)
            line_ids.append((0, 0, {
                'account_id': self.credit_account_id.id,
                'partner_id': partner_id,
                'debit': 0.0,
                'credit': total_credit,
                'name': _('Transfer from %s') % self.journal_id.name
            }))

            move_vals = {
                'journal_id': self.journal_id.id,
                'partner_id': partner_id,  # Add partner to journal entry header
                'company_id': self.company_id.id,
                'move_type': 'entry',
                'date': self.date,
                'ref': _('Refill Advance Box: %s') % self.box_id.name,
                'line_ids': line_ids
            }
            
            move = self.env['account.move'].create(move_vals)
            _logger.info('✅ Journal entry created: %s (ID: %s)', move.name, move.id)
            
            # Post the journal entry
            move.action_post()
            _logger.info('✅ Journal entry posted successfully')
            
            # Create refill record
            refill_vals = {
                'box_id': self.box_id.id,
                'amount': self.amount,
                'payment_id': False,
                'state': 'posted',
                'date': self.date,
                'currency_id': self.currency_id.id,
                'company_id': self.company_id.id,
                'journal_bank_id': self.journal_id.id,
                'bank_charge_amount': self.bank_charge_amount,
                'bank_charge_currency_id': self.bank_charge_currency_id.id,
                'notes': self.notes or _('Refill via journal entry %s') % move.name,
            }
            
            refill = self.env['advance.box.refill'].create(refill_vals)
            _logger.info('✅ Refill record created: %s (ID: %s)', refill.name, refill.id)
            
            # Refresh balance
            self.box_id._trigger_balance_recompute()
            
            # Post message to chatter
            msg_body = _('Advance box refilled with amount %s<br/>Journal Entry: %s<br/>Debit: %s<br/>Credit: %s') % (
                self.amount, move.name, self.debit_account_id.display_name, self.credit_account_id.display_name
            )
            if self.bank_charge_amount > 0:
                msg_body += _('<br/>Bank Charges: %s %s') % (self.bank_charge_amount, self.bank_charge_currency_id.name)

            self.box_id.message_post(
                body=msg_body,
                subject=_('Refill Completed')
            )
            
            # Show success message and return
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _('Advance box refilled successfully! Journal Entry: %s') % move.name,
                    'type': 'success',
                    'sticky': False,
                    'next': {
                        'type': 'ir.actions.act_window_close'
                    }
                }
            }
            
        except Exception as e:
            _logger.error('❌ Error creating refill: %s', str(e))
            raise UserError(_('Error creating refill: %s') % str(e))
