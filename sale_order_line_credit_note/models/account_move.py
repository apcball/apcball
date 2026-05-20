from odoo import fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    source_sale_id = fields.Many2one(
        "sale.order",
        string="Source Sale Order",
        copy=False,
        help="Sale Order from which this credit note originated.",
    )


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    source_sale_line_id = fields.Many2one(
        "sale.order.line",
        string="Source Sale Order Line",
        copy=False,
        help="Sale Order Line that was credited.",
    )
    source_invoice_line_id = fields.Many2one(
        "account.move.line",
        string="Source Invoice Line",
        copy=False,
        help="Original invoice line that was credited.",
    )
