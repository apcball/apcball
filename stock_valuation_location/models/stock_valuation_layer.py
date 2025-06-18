"""
Adds the location to stock valuation layer, much in the same way the base code adds
warehouse_id.
"""

from odoo import models, fields, api


class StockValuationLayer(models.Model):
    _inherit = "stock.valuation.layer"

    location_id = fields.Many2one(
        comodel_name="stock.location",
        string="Location",
        compute="_compute_location_id",
        store=True,
        compute_sudo=True,
    )

    def _compute_location_id(self):
        for svl in self:
            if svl.stock_move_id.location_id.usage == "internal":
                svl.location_id = svl.stock_move_id.location_id
            else:
                svl.location_id = svl.stock_move_id.location_dest_id
