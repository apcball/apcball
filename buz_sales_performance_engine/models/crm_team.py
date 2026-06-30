from odoo import models


class CrmTeam(models.Model):
    _inherit = "crm.team"

    def action_view_performance(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Team Performance",
            "res_model": "buz.sales.performance.result",
            "view_mode": "tree,pivot,graph,form",
            "domain": [("team_id", "=", self.id)],
            "context": {"default_team_id": self.id, "search_default_groupby_salesperson_id": 1},
        }
