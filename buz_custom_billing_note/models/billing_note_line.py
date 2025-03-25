from odoo import models, fields, api

class BillingNoteLine(models.Model):
    _name = 'billing.note.line'
    _description = 'Billing Note Line'

    billing_note_id = fields.Many2one('billing.note', string='Billing Note', required=True, ondelete='cascade')
    name = fields.Char(string='Description', required=True)
    quantity = fields.Float(string='Quantity', default=1.0)
    price_unit = fields.Float(string='Unit Price')
    amount = fields.Float(string='Amount', compute='_compute_amount', store=True)
    company_id = fields.Many2one(related='billing_note_id.company_id', store=True)

    @api.depends('quantity', 'price_unit')
    def _compute_amount(self):
        for line in self:
            line.amount = line.quantity * line.price_unit