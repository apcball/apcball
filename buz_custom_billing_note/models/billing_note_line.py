from odoo import models, fields, api


class BillingNoteLine(models.Model):
    _name = 'billing.note.line'
    _description = 'Billing Note Line'
    _order = 'id'
    _check_company_auto = True

    billing_note_id = fields.Many2one('billing.note', string='Billing Note', required=True, ondelete='cascade',
                                      check_company=True)
    invoice_id = fields.Many2one('account.move', string='Invoice', required=True, check_company=True)
    date = fields.Date(related='invoice_id.invoice_date', string='Invoice Date', store=True)
    due_date = fields.Date(related='invoice_id.invoice_date_due', string='Due Date', store=True)
    amount_total = fields.Monetary(related='invoice_id.amount_total', string='Total Amount', store=True)
    amount_residual = fields.Monetary(related='invoice_id.amount_residual', string='Amount Due', store=True)
    currency_id = fields.Many2one('res.currency', string='Currency', related='billing_note_id.currency_id',
                                  store=True, readonly=True)
    company_id = fields.Many2one('res.company', string='Company', related='billing_note_id.company_id',
                                 store=True, readonly=True, index=True)
