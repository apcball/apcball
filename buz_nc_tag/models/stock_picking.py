import math

from odoo import models
from odoo.tools import html2plaintext


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def _nc_tag_units(self):
        """Return one move line record per physical unit (qty 3 -> 3 entries)."""
        self.ensure_one()
        units = []
        for line in self.move_line_ids:
            units.extend([line] * math.ceil(line.quantity or 0))
        return units

    def _nc_tag_problem_text(self):
        """Picking note as plain text for the 'ปัญหาที่พบ' field."""
        self.ensure_one()
        return html2plaintext(self.note or '').strip()
