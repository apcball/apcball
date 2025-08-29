from odoo import models, fields


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    trade_channel = fields.Selection([('shopee', 'Shopee'), ('lazada', 'Lazada'), ('nocnoc', 'Noc Noc'), ('tiktok', 'Tiktok'), ('other', 'Other')], string='Trade Channel')

    def _prepare_invoice(self):
        """Extend invoice preparation to copy trade_channel from the sale order.

        This ensures invoices created from sale orders carry the same channel
        so the settlement wizard can filter by it.
        """
        vals = super()._prepare_invoice()
        # Some flows may create invoices for multiple orders; use order's value.
        vals['trade_channel'] = self.trade_channel
        return vals


class AccountMove(models.Model):
    _inherit = 'account.move'

    trade_channel = fields.Selection([('shopee', 'Shopee'), ('lazada', 'Lazada'), ('nocnoc', 'Noc Noc'), ('tiktok', 'Tiktok'), ('other', 'Other')], string='Trade Channel')
