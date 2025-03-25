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

    @api.constrains('amount')
    def _check_amount(self):
        for wizard in self:
            if wizard.amount <= 0:
                raise ValidationError(_('Payment amount must be positive.'))
            if wizard.amount > wizard.billing_note_id.amount_residual:
                raise ValidationError(_('Payment amount cannot exceed the remaining amount to pay (%s).') % 
                    wizard.billing_note_id.currency_id.symbol + str(wizard.billing_note_id.amount_residual))

    def action_register_payment(self):
        self.ensure_one()
        payment_vals = {
            'billing_note_id': self.billing_note_id.id,
            'name': self.reference or '/',
            'amount': self.amount,
            'payment_date': self.payment_date,
            'payment_method': self.payment_method,
            'notes': self.notes,
        }
        payment = self.env['billing.note.payment'].create(payment_vals)
        
        if self.billing_note_id.state == 'draft':
            self.billing_note_id.action_confirm()
            
        if self.billing_note_id.amount_residual <= 0:
            self.billing_note_id.action_done()
            
        return {'type': 'ir.actions.act_window_close'}