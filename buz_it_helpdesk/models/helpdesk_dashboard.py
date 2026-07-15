from datetime import datetime, timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError


class HelpdeskTicketDashboard(models.Model):
    _inherit = "it.helpdesk.ticket"

    @api.model
    def _dashboard_domain(self, filters=None):
        filters = filters or {}
        allowed_company_ids = self.env.companies.ids
        domain = [("company_id", "in", allowed_company_ids)]

        def valid_id(value, allowed_ids):
            try:
                value = int(value)
            except (TypeError, ValueError):
                return False
            return value if value in allowed_ids else False

        company_id = valid_id(filters.get("company_id"), allowed_company_ids)
        if filters.get("company_id") and not company_id:
            return [("id", "=", 0)]
        if company_id:
            domain.append(("company_id", "=", company_id))
        for key, field_name in (("team_id", "team_id"), ("assignee_id", "assigned_to"), ("priority_id", "priority_id"), ("category_id", "category_id")):
            if filters.get(key):
                try:
                    domain.append((field_name, "=", int(filters[key])))
                except (TypeError, ValueError):
                    return [("id", "=", 0)]
        if filters.get("date_from"):
            domain.append(("create_date", ">=", "%s 00:00:00" % filters["date_from"]))
        if filters.get("date_to"):
            try:
                end_date = datetime.strptime(filters["date_to"], "%Y-%m-%d") + timedelta(days=1)
            except (TypeError, ValueError):
                return [("id", "=", 0)]
            domain.append(("create_date", "<", fields.Datetime.to_string(end_date)))
        return domain

    @api.model
    def _dashboard_stage_code(self, stage):
        if not stage:
            return "other"
        if stage.sequence == 0:
            return "draft"
        if stage.sequence == 1:
            return "new"
        if stage.sequence == 3:
            return "in_progress"
        if stage.sequence == 4:
            return "pending_user"
        if stage.sequence == 5:
            return "resolved"
        if stage.sequence == 6 and stage.is_closed:
            return "closed"
        if stage.sequence >= 7 and stage.is_closed:
            return "cancelled"
        return "other"

    @api.model
    def get_dashboard_data(self, filters=None):
        if not (
            self.env.user.has_group("buz_it_helpdesk.group_it_helpdesk_agent")
            or self.env.user.has_group("buz_it_helpdesk.group_it_helpdesk_manager")
        ):
            raise AccessError("Only Helpdesk Agents and Managers can view the dashboard.")
        domain = self._dashboard_domain(filters)
        stages = self.env["it.helpdesk.stage"].search([("company_id", "in", self.env.companies.ids + [False])], order="sequence, id")
        stage_ids_by_code = {}
        for stage in stages:
            stage_ids_by_code.setdefault(self._dashboard_stage_code(stage), []).append(stage.id)
        status_labels = {"draft": "Draft", "new": "New", "in_progress": "In Progress", "pending_user": "Pending User", "resolved": "Resolved", "closed": "Closed", "cancelled": "Cancelled", "other": "Other"}
        status_overview = []
        for code, label in status_labels.items():
            count_domain = list(domain)
            stage_ids = stage_ids_by_code.get(code)
            count_domain.append(("stage_id", "in", stage_ids) if stage_ids else ("id", "=", 0))
            status_overview.append({"code": code, "label": label, "count": self.search_count(count_domain), "domain": count_domain})
        open_domain = list(domain) + [("stage_id.is_closed", "=", False)]
        kpis = [{"code": "open", "label": "Open Tickets", "count": self.search_count(open_domain), "domain": open_domain}]
        for code in ("new", "in_progress", "pending_user", "resolved", "closed"):
            status = next(item for item in status_overview if item["code"] == code)
            kpis.append({"code": code, "label": status["label"], "count": status["count"], "domain": status["domain"]})
        for code, label, field_name in (("sla_overdue", "SLA Overdue", "is_overdue"), ("response_sla_overdue", "Response SLA Overdue", "is_response_overdue")):
            count_domain = list(domain) + [(field_name, "=", True)]
            kpis.append({"code": code, "label": label, "count": self.search_count(count_domain), "domain": count_domain})

        def grouped(field_name):
            result = []
            for group in self.read_group(domain, [field_name], [field_name], lazy=False):
                value = group.get(field_name)
                value_id, label = value if isinstance(value, (list, tuple)) else (False, "Unassigned")
                count = group.get("%s_count" % field_name, group.get("__count", 0))
                result.append({"id": value_id, "label": label or "Unassigned", "count": count, "domain": list(domain) + [(field_name, "=", value_id)]})
            return sorted(result, key=lambda item: (-item["count"], item["label"]))[:12]

        trend = [{"label": group.get("create_date:day") or "", "count": group.get("__count", 0)} for group in self.read_group(domain, ["__count"], ["create_date:day"], lazy=False)]
        options = {}
        specs = (("companies", "res.company", [("id", "in", self.env.companies.ids)]), ("teams", "it.helpdesk.team", [("company_id", "in", self.env.companies.ids), ("active", "=", True)]), ("priorities", "it.helpdesk.priority", [("company_id", "in", self.env.companies.ids), ("active", "=", True)]), ("categories", "it.helpdesk.category", [("company_id", "in", self.env.companies.ids), ("active", "=", True)]))
        for key, model_name, option_domain in specs:
            options[key] = [{"id": record.id, "label": record.display_name} for record in self.env[model_name].search(option_domain, order="name, id")]
        options["assignees"] = [{"id": user.id, "label": user.display_name} for user in self.env["res.users"].search([("company_ids", "in", self.env.companies.ids), ("share", "=", False)], order="name, id")]
        return {"domain": domain, "kpis": kpis, "status_overview": status_overview, "trend": trend, "by_team": grouped("team_id"), "by_assignee": grouped("assigned_to"), "by_priority": grouped("priority_id"), "by_category": grouped("category_id"), "options": options}
