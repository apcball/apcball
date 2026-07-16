from odoo import fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    pos_lite_order_line_id = fields.Many2one(
        "pos.lite.order.line", readonly=True, copy=False
    )
