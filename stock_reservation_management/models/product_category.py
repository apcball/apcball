from odoo import fields, models


class ProductCategory(models.Model):
    """Extend product.category with safety reserve configuration."""

    _inherit = "product.category"

    safety_reserve_qty = fields.Float(
        string="Safety Reserve Quantity",
        digits="Product Unit of Measure",
        default=0.0,
        help="Minimum quantity to keep as safety buffer. "
        "This quantity is excluded from 'Available to Promise' calculations.",
    )
