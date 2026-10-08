import math

from odoo import models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def _nc_tag_units(self):
        """Return one move line record per physical unit (qty 3 -> 3 entries)."""
        self.ensure_one()
        units = []
        for line in self.move_line_ids:
            units.extend([line] * math.ceil(line.quantity or 0))
        return units
