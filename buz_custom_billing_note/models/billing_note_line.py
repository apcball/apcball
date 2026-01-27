from odoo import models, fields, api

class BillingNoteLine(models.Model):
    _name = 'billing.note.line'
    _description = 'Billing Note Line'
    _order = 'id'

    billing_note_id = fields.Many2one('billing.note', string='Billing Note', required=True, ondelete='cascade')
    invoice_id = fields.Many2one('account.move', string='Invoice', required=True)
    date = fields.Date(related='invoice_id.invoice_date', string='Invoice Date', store=True)
    due_date = fields.Date(related='invoice_id.invoice_date_due', string='Due Date', store=True)
    amount_total = fields.Monetary(related='invoice_id.amount_total', string='Total Amount', store=True)
    amount_residual = fields.Monetary(related='invoice_id.amount_residual', string='Amount Due', store=True)
    currency_id = fields.Many2one('res.currency', string='Currency',
        default=lambda self: self.env.company.currency_id)
    company_id = fields.Many2one(related='billing_note_id.company_id')