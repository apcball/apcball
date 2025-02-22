from odoo import models, fields, api
from datetime import datetime

class AccountPayment(models.Model):
    _inherit = 'account.payment'

    def amount_in_words(self):
        return self.currency_id.amount_to_text(self.amount)

    def get_formatted_date(self):
        return self.date.strftime('%B %d, %Y')

    @api.depends('reconciled_bill_ids')
    def _compute_order_lines(self):
        for payment in self:
            payment.order_lines = payment.reconciled_bill_ids.mapped('invoice_line_ids')

    order_lines = fields.One2many('account.move.line', compute='_compute_order_lines')