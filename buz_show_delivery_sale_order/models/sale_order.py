from odoo import api, fields, models

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    delivery_address_display = fields.Many2one(
        'res.partner',
        string='Full Delivery Address',
        related='partner_shipping_id',
        store=True,
        readonly=True,
        groups='account.group_delivery_invoice_address',
    )