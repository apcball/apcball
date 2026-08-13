from odoo import models


class PosLiteOrder(models.Model):
    _inherit = "pos.lite.order"

    def write(self, vals):
        res = super().write(vals)
        if "state" in vals:
            line_ids = self.sudo().mapped("line_ids").ids
            if line_ids:
                self.env["buz.sales.performance.result"]._recompute_for_pos_lines(line_ids)
        return res
