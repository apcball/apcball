from odoo import fields, models


class CrmTeam(models.Model):
    _inherit = "crm.team"

    spe_count_in_sales = fields.Boolean(
        string="Count in Sales Dashboard",
        default=True,
        help="When no team is picked on the Sales Performance dashboard, "
             "only teams with this box ticked are counted. Keep it in line "
             "with the team list of the Invoices Analysis report.",
    )

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
