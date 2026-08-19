from odoo import fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    tag_ids = fields.Many2many("buz.picking.tag", string="Tags")
