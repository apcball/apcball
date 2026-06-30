from odoo import models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def button_validate(self):
        res = super().button_validate()
        # Recompute only when the picking is actually done (not a backorder wizard return).
        done_pickings = self.filtered(lambda p: p.state == "done")
        if done_pickings:
            sol_ids = done_pickings.move_ids.sudo().mapped("sale_line_id").ids
            if sol_ids:
                self.env["buz.sales.performance.result"]._recompute_for_sol(sol_ids)
        return res
