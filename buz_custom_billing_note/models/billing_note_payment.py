from odoo import models, fields, api, _


class BillingNotePayment(models.Model):
    _name = 'billing.note.payment'
    _description = 'Billing Note Payment'
    _order = 'payment_date desc, id desc'
    _check_company_auto = True

    name = fields.Char(string='Reference', compute='_compute_name', store=True)
    billing_note_id = fields.Many2one('billing.note', string='Billing Note', required=True,
                                      ondelete='cascade', check_company=True)
    payment_id = fields.Many2one('account.payment', string='Payment', check_company=True)
    payment_date = fields.Date(string='Payment Date', required=True)
    payment_method = fields.Selection([
        ('cash', 'Cash'),
        ('transfer', 'Bank Transfer'),
        ('check', 'Check'),
        ('other', 'Other')
    ], string='Payment Method', required=True, default='transfer')
    amount = fields.Monetary(string='Amount', required=True)
    currency_id = fields.Many2one('res.currency', string='Currency',
                                  related='billing_note_id.currency_id', store=True, readonly=True)
    company_id = fields.Many2one('res.company', string='Company',
                                 related='billing_note_id.company_id', store=True, readonly=True)
    notes = fields.Text(string='Notes')

    @api.depends('payment_id', 'payment_date')
    def _compute_name(self):
        for record in self:
            if record.payment_id and record.payment_id.name:
                record.name = record.payment_id.name
            elif record.payment_date:
                record.name = _('Payment %s') % record.payment_date.strftime('%Y/%m/%d')
            else:
                record.name = _('New Payment')

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        billing_notes = records.mapped('billing_note_id')
        for note in billing_notes:
            note._compute_amount_paid()
            note._compute_payment_state()
        return records
