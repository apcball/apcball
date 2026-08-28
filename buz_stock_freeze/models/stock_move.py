from odoo import models


class StockMove(models.Model):
    _inherit = "stock.move"

    def _action_done(self, cancel_backorder=False):
        freeze = self.env["stock.freeze.period"].sudo()
        to_log = freeze._check_moves(self)
        res = super()._action_done(cancel_backorder=cancel_backorder)
        if to_log:
            freeze._log_overrides(to_log, res)
        return res
