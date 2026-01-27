from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    payment_reference = fields.Char(string="Payment Reference", required=False, )

    # =========================== Built-in functions =========================== #
    def _prepare_invoice(self):
        res = super(SaleOrder, self)._prepare_invoice()
        res['payment_reference'] = self.payment_reference
        return res
