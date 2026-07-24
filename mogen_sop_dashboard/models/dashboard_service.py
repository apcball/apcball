"""Bounded, permission-filtered data shared by dashboard consumers."""
from odoo import models


class MogenSopDashboardService(models.AbstractModel):
    _name = "mogen.sop.dashboard.service"
    _description = "S&OP Dashboard Aggregation Service"

    def get_active_context(self, plan_id=False, scenario_id=False, filters=None, limit=50):
        filters = filters or {}
        limit = min(max(int(limit or 50), 1), 100)
        result = {"snapshot_date": self.env.cr.now(), "plan": False, "scenario": False, "filters": filters, "alerts": [], "recommendations": [], "source_links": []}
        if plan_id:
            plan = self.env["mogen.sop.plan"].browse(plan_id).exists()
            if plan:
                plan.check_access_rights("read"); plan.check_access_rule("read")
                result["plan"] = {"id": plan.id, "name": plan.display_name, "state": plan.state}
                result["source_links"].append({"model": "mogen.sop.plan", "id": plan.id, "name": plan.display_name})
                alerts = self.env["mogen.sop.alert"].search([("plan_id", "=", plan.id), ("state", "!=", "resolved")], limit=limit, order="severity desc, id desc")
                recommendations = self.env["mogen.sop.recommendation"].search([("plan_id", "=", plan.id), ("state", "in", ("draft", "reviewed"))], limit=limit, order="priority desc, id desc")
                result["alerts"] = [{"id": row.id, "name": row.name, "severity": row.severity, "type": row.alert_type} for row in alerts]
                result["recommendations"] = [{"id": row.id, "name": row.name, "priority": row.priority, "type": row.recommendation_type} for row in recommendations]
                result["source_links"] += [{"model": "mogen.sop.alert", "id": row.id, "name": row.name} for row in alerts]
        if scenario_id:
            scenario = self.env["mogen.sop.scenario"].browse(scenario_id).exists()
            if scenario:
                scenario.check_access_rights("read"); scenario.check_access_rule("read")
                result["scenario"] = {"id": scenario.id, "name": scenario.display_name}
                result["source_links"].append({"model": "mogen.sop.scenario", "id": scenario.id, "name": scenario.display_name})
        return result
