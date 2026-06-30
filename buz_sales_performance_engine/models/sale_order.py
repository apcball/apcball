from odoo import models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _action_confirm(self):
        res = super()._action_confirm()
        self._recompute_performance()
        return res

    def button_done(self):
        res = super().button_done()
        self._recompute_performance()
        return res

    def action_view_performance(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Performance",
            "res_model": "buz.sales.performance.result",
            "view_mode": "tree,pivot,graph,form",
            "domain": [("sale_order_id", "=", self.id)],
            "context": {"default_sale_order_id": self.id},
        }

    def _recompute_performance(self):
        """Recompute SPE rows for every line of these orders."""
        return self.env["buz.sales.performance.result"]._recompute_for_orders(self.ids)
