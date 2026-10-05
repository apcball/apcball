from odoo import fields, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    # Lines the connector adds from Shopee payment data; replaced on re-apply.
    shopee_line_type = fields.Selection(
        [("shipping", "Shopee Shipping"), ("voucher", "Shopee Seller Voucher")],
        copy=False, readonly=True,
    )
