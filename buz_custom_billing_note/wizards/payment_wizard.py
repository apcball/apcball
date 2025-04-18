from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class BillingNotePaymentWizard(models.TransientModel):
    _name = 'billing.note.payment.wizard'
    _description = 'Register Payment for Billing Note'

    billing_note_id = fields.Many2one('billing.note', string='Billing Note', required=True)
    amount = fields.Monetary(string='Payment Amount', required=True)
    payment_date = fields.Date(string='Payment Date', required=True, default=fields.Date.context_today)
    payment_method = fields.Selection([
        ('cash', 'Cash'),
        ('bank', 'Bank Transfer'),
        ('check', 'Check'),
    ], string='Payment Method', required=True)
    reference = fields.Char(string='Reference')
    notes = fields.Text(string='Notes')
    currency_id = fields.Many2one('res.currency', related='billing_note_id.currency_id')
    journal_id = fields.Many2one('account.journal', string='Payment Journal', required=True)
    partner_bank_id = fields.Many2one('res.partner.bank', string='Recipient Bank Account',
        domain="[('partner_id', '=', partner_id)]")
    partner_id = fields.Many2one('res.partner', related='billing_note_id.partner_id')

    @api.constrains('amount')
    def _check_amount(self):
        for wizard in self:
            if wizard.amount <= 0:
                raise ValidationError(_('Payment amount must be positive.'))
            if wizard.amount > wizard.billing_note_id.amount_residual:
                raise ValidationError(_('Payment amount cannot exceed the remaining amount to pay (%s).') % 
                    wizard.billing_note_id.currency_id.symbol + str(wizard.billing_note_id.amount_residual))

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        if 'payment_method' in defaults:
            journal_type = 'cash' if defaults['payment_method'] == 'cash' else 'bank'
            journal = self.env['account.journal'].search([
                ('type', '=', journal_type),
                '|',
                ('company_id', '=', self.env.company.id),
                ('company_id', '=', False)
            ], limit=1)
            if journal:
                defaults['journal_id'] = journal.id
        return defaults

    @api.onchange('payment_method')
    def _onchange_payment_method(self):
        """Update journal domain based on payment method"""
        if not self.payment_method:
            self.journal_id = False
            return
            
        if self.payment_method == 'cash':
            domain = [('type', '=', 'cash')]
        else:
            domain = [('type', '=', 'bank')]
            
        if self.billing_note_id.note_type == 'receivable':
            domain.append(('inbound_payment_method_line_ids.payment_method_id.code', '=', 'manual'))
        else:
            domain.append(('outbound_payment_method_line_ids.payment_method_id.code', '=', 'manual'))
            
        domain.extend(['|', ('company_id', '=', self.env.company.id), ('company_id', '=', False)])
        
        # Auto-select first available journal
        journal = self.env['account.journal'].search(domain, limit=1)
        if journal:
            self.journal_id = journal.id
            
        return {'domain': {'journal_id': domain}}

    def _prepare_payment_values(self):
        """Prepare the dict of values to create the payment"""
        payment_type = 'inbound' if self.billing_note_id.note_type == 'receivable' else 'outbound'
        partner_type = 'customer' if self.billing_note_id.note_type == 'receivable' else 'supplier'

        # Get appropriate payment method line
        payment_method_line = self.journal_id.inbound_payment_method_line_ids if payment_type == 'inbound' \
            else self.journal_id.outbound_payment_method_line_ids
        payment_method_line = payment_method_line.filtered(lambda x: x.payment_method_id.code == 'manual')

        if not payment_method_line:
            raise ValidationError(_('No manual payment method available for this journal.'))

        values = {
            'date': self.payment_date,
            'amount': self.amount,
            'payment_type': payment_type,
            'partner_type': partner_type,
            'ref': self.reference or self.billing_note_id.name,
            'journal_id': self.journal_id.id,
            'currency_id': self.currency_id.id,
            'partner_id': self.partner_id.id,
            'partner_bank_id': self.partner_bank_id.id,
            'payment_method_line_id': payment_method_line[0].id,
        }
        return values

    def action_register_payment(self):
        self.ensure_one()

        # Create account.payment
        payment_values = self._prepare_payment_values()
        payment = self.env['account.payment'].create(payment_values)
        
        # Post the payment
        payment.action_post()

        # Create billing.note.payment
        self.env['billing.note.payment'].create({
            'billing_note_id': self.billing_note_id.id,
            'payment_id': payment.id,
            'payment_date': self.payment_date,
            'payment_method': self.payment_method,
            'amount': self.amount,
            'notes': self.notes,
            'currency_id': self.currency_id.id,
            'company_id': self.billing_note_id.company_id.id,
        })

        # Update billing note state if needed
        if self.billing_note_id.state == 'draft':
            self.billing_note_id.action_confirm()

        if self.billing_note_id.amount_residual <= 0:
            self.billing_note_id.action_done()

        return {'type': 'ir.actions.act_window_close'}