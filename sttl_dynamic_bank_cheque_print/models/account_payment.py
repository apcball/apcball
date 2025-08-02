from odoo import models, fields, api
from num2words import num2words


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    amount_total_words = fields.Char(string="Amount in Words", compute='_compute_amount_total_words')
    payment_method_name = fields.Char(compute='_compute_payment_method_name', store=True)

    @api.depends('payment_method_line_id')
    def _compute_payment_method_name(self):
        for rec in self:
            rec.payment_method_name = rec.payment_method_line_id.name or ''
            print(f'\n\n\n{rec.payment_method_name}\n\n\n')

    def _compute_amount_total_words(self):
        for payment in self:
            payment.amount_total_words = payment.currency_id.amount_to_text(payment.amount)

    def number_to_words(self, number):
        return num2words(number, lang='en').replace(",", "").title() + " Only"

    def action_open_cheque_wizard(self):
        self.ensure_one()
        return {
            'name': 'Advance Print Cheque',
            'type': 'ir.actions.act_window',
            'res_model': 'cheque.print',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_pay_to': self.partner_id.name,
                'default_amount': self.amount,
                'default_currency_id': self.currency_id.id,
                'default_amt_2_words': self.amount_total_words,
                'default_payment_id': self.id,
            }
        }
