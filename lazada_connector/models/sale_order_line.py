from odoo import fields, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    # Lines the connector adds from Lazada payment data; replaced on re-apply.
    lazada_line_type = fields.Selection(
        [("shipping", "Lazada Shipping"), ("voucher", "Lazada Seller Voucher")],
        copy=False, readonly=True,
    )
