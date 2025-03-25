from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class BillingNotePayment(models.Model):
    _name = 'billing.note.payment'
    _description = 'Billing Note Payment'
    _order = 'payment_date desc, id desc'
    _rec_name = 'name'

    billing_note_id = fields.Many2one('billing.note', string='Billing Note', required=True)
    name = fields.Char(string='Reference', required=True)
    amount = fields.Monetary(string='Amount', required=True)
    payment_date = fields.Date(string='Payment Date', required=True, default=fields.Date.context_today)
    payment_method = fields.Selection([
        ('cash', 'Cash'),
        ('bank', 'Bank Transfer'),
        ('check', 'Check'),
    ], string='Payment Method', required=True)
    notes = fields.Text(string='Notes')
    company_id = fields.Many2one('res.company', related='billing_note_id.company_id', store=True)
    currency_id = fields.Many2one('res.currency', related='billing_note_id.currency_id')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('posted', 'Posted'),
        ('cancelled', 'Cancelled')
    ], string='Status', default='draft', required=True)
    
    total_amount = fields.Monetary(string='Total Amount', compute='_compute_amounts')
    paid_amount = fields.Monetary(string='Paid Amount', compute='_compute_amounts')
    remaining_amount = fields.Monetary(string='Remaining Amount', compute='_compute_amounts')

    @api.depends('billing_note_id', 'billing_note_id.invoice_ids', 'billing_note_id.payment_line_ids')
    def _compute_amounts(self):
        for payment in self:
            total_amount = sum(payment.billing_note_id.invoice_ids.mapped('amount_total'))
            paid_amount = sum(payment.billing_note_id.payment_line_ids.filtered(
                lambda p: p.id != payment.id and p.state == 'posted'
            ).mapped('amount'))
            payment.total_amount = total_amount
            payment.paid_amount = paid_amount
            payment.remaining_amount = total_amount - paid_amount

    @api.constrains('amount')
    def _check_amount(self):
        for payment in self:
            if payment.amount <= 0:
                raise ValidationError(_('Payment amount must be positive.'))
            
            if payment.amount > payment.remaining_amount:
                raise ValidationError(_(
                    'Payment amount (%(amount)s) cannot exceed the remaining amount to pay (%(remaining)s).',
                    amount=payment.currency_id.symbol + str(payment.amount),
                    remaining=payment.currency_id.symbol + str(payment.remaining_amount)
                ))

    def name_get(self):
        result = []
        for payment in self:
            name = payment.name
            if payment.payment_date:
                name = '%s (%s)' % (name, payment.payment_date)
            result.append((payment.id, name))
        return result