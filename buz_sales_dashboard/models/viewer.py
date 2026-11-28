from odoo import api, fields, models


class SalesDashboardViewer(models.AbstractModel):
    """Whoever leads a sales team sees the figures and targets of every team.

    A search field rather than a group: the record rule asks at query time, so
    naming or replacing a team leader takes effect at once.
    """

    _name = "buz.sales.dashboard.viewer"
    _description = "Sales Dashboard Viewer"

    viewer_leads_team = fields.Boolean(
        "ผู้ดูเป็นหัวหน้าทีมขาย", compute="_compute_viewer_leads_team",
        search="_search_viewer_leads_team")

    @api.model
    def _leads_sales_team(self):
        return bool(self.env["crm.team"].sudo().search_count(
            [("user_id", "=", self.env.uid)], limit=1))

    @api.depends_context("uid")
    def _compute_viewer_leads_team(self):
        self.viewer_leads_team = self._leads_sales_team()

    @api.model
    def _search_viewer_leads_team(self, operator, value):
        wanted = (operator == "=") == bool(value)
        return [(1, "=", 1)] if self._leads_sales_team() == wanted else [(0, "=", 1)]
