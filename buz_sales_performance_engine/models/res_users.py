from odoo import models


class ResUsers(models.Model):
    _inherit = "res.users"

    def action_view_performance(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "My Performance",
            "res_model": "buz.sales.performance.result",
            "view_mode": "tree,pivot,graph,form",
            "domain": [("salesperson_id", "=", self.id)],
            "context": {"default_salesperson_id": self.id},
        }
