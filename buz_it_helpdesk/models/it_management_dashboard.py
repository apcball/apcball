from datetime import datetime, timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError


class ItManagementDashboard(models.Model):
    _name = "it.management.dashboard"
    _auto = False
    _description = "IT Management Helpdesk Dashboard"
    _LIST_LIMIT = 10

    @api.model
    def _cleanup_legacy_asset_data(self):
        """Remove the retired Asset subsystem during module upgrade.

        This is intentionally SQL-based because the legacy models are no longer
        registered. The statements are idempotent so fresh installations are
        safe as well.
        """
        self.env.cr.execute("""
            DELETE FROM ir_attachment WHERE res_model LIKE 'buz.it.asset%%';
            DELETE FROM mail_activity WHERE res_model LIKE 'buz.it.asset%%';
            DELETE FROM mail_followers WHERE res_model LIKE 'buz.it.asset%%';
            DELETE FROM mail_message WHERE model LIKE 'buz.it.asset%%';
            DELETE FROM ir_cron WHERE model_id IN (
                SELECT id FROM ir_model WHERE model LIKE 'buz.it.asset%%'
            );
            DELETE FROM ir_act_window WHERE res_model LIKE 'buz.it.asset%%';
            DELETE FROM ir_ui_view WHERE model LIKE 'buz.it.asset%%';
            DELETE FROM ir_ui_menu WHERE id IN (
                SELECT res_id FROM ir_model_data
                 WHERE module = 'buz_it_helpdesk' AND model = 'ir.ui.menu'
                   AND (name LIKE '%%asset%%' OR name LIKE '%%renewal%%')
            );
            DELETE FROM ir_model_access WHERE model_id IN (
                SELECT id FROM ir_model WHERE model LIKE 'buz.it.asset%%'
            );
            DELETE FROM ir_rule WHERE model_id IN (
                SELECT id FROM ir_model WHERE model LIKE 'buz.it.asset%%'
            );
            DELETE FROM ir_model_fields WHERE model_id IN (
                SELECT id FROM ir_model WHERE model LIKE 'buz.it.asset%%'
            );
            DELETE FROM ir_model_constraint WHERE model IN (
                SELECT model FROM ir_model WHERE model LIKE 'buz.it.asset%%'
            );
            DELETE FROM ir_model_data
             WHERE module = 'buz_it_helpdesk'
               AND name != 'asset_cleanup'
               AND (name LIKE '%%asset%%' OR name LIKE '%%renewal%%');
            DELETE FROM res_groups_implied_rel
             WHERE gid IN (SELECT id FROM res_groups WHERE name ILIKE 'IT Asset%%')
                OR hid IN (SELECT id FROM res_groups WHERE name ILIKE 'IT Asset%%');
            DELETE FROM res_groups_users_rel
             WHERE gid IN (SELECT id FROM res_groups WHERE name ILIKE 'IT Asset%%');
            DELETE FROM res_groups WHERE name ILIKE 'IT Asset%%';
            DELETE FROM ir_model WHERE model LIKE 'buz.it.asset%%';
        """)
        for table in (
            "buz_it_asset_notification_log", "buz_it_asset_notification_config",
            "buz_it_asset_license_allocation", "buz_it_asset_renewal",
            "buz_it_asset_log", "buz_it_asset_spec_line", "buz_it_asset",
            "buz_it_asset_software", "buz_it_asset_spec_category", "buz_it_asset_category",
        ):
            self.env.cr.execute('DROP TABLE IF EXISTS "%s" CASCADE' % table)

    def _check_access(self):
        if not self.env.user.has_group("buz_it_helpdesk.group_it_helpdesk_agent"):
            raise AccessError("Only IT Helpdesk Agents and Managers can view the dashboard.")

    @api.model
    def _company_domain(self, filters=None):
        filters = filters or {}
        allowed_company_ids = self.env.companies.ids
        domain = [("company_id", "in", allowed_company_ids)]
        company_id = filters.get("company_id")
        if company_id:
            try:
                company_id = int(company_id)
            except (TypeError, ValueError):
                return [("id", "=", 0)]
            if company_id not in allowed_company_ids:
                return [("id", "=", 0)]
            domain = [("company_id", "=", company_id)]
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
    def _navigation(self):
        if not self.env.user.has_group("buz_it_helpdesk.group_it_helpdesk_agent"):
            return []
        return [
            {"key": "overview", "label": "Dashboard", "icon": "fa-home", "kind": "section", "section": "overview"},
            {"key": "helpdesk", "label": "Helpdesk", "icon": "fa-life-ring", "kind": "section", "section": "helpdesk"},
        ]

    @api.model
    def _options(self):
        return {
            "companies": [{"id": company.id, "label": company.display_name} for company in self.env.companies],
            "navigation": self._navigation(),
        }

    @api.model
    def _bounded_limit(self, filters, key):
        try:
            requested = int((filters or {}).get(key, self._LIST_LIMIT))
        except (TypeError, ValueError):
            requested = self._LIST_LIMIT
        return max(1, min(requested, self._LIST_LIMIT))

    @api.model
    def _recent_tickets(self, filters):
        Ticket = self.env["it.helpdesk.ticket"]
        domain = Ticket._dashboard_domain(filters)
        limit = self._bounded_limit(filters, "recent_limit")
        records = Ticket.search(domain, order="create_date desc, id desc", limit=limit)
        rows = [{
            "id": ticket.id, "ticket_no": ticket.name, "subject": ticket.subject or "",
            "requester": ticket.requester_id.display_name or "",
            "priority": ticket.priority_id.display_name or "", "priority_code": ticket.priority_code or "",
            "status": ticket.stage_id.display_name or "", "status_code": ticket.stage_code or "other",
            "created": fields.Datetime.to_string(ticket.create_date) if ticket.create_date else False,
            "res_model": "it.helpdesk.ticket", "res_id": ticket.id,
        } for ticket in records]
        return {"rows": rows, "limit": limit, "domain": domain, "res_model": "it.helpdesk.ticket",
                "action_xml_id": "buz_it_helpdesk.action_helpdesk_tickets"}

    @api.model
    def _previous_period_filters(self, filters):
        filters = filters or {}
        if not filters.get("date_from") or not filters.get("date_to"):
            return None
        try:
            current_from = datetime.strptime(filters["date_from"], "%Y-%m-%d").date()
            current_to = datetime.strptime(filters["date_to"], "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return None
        if current_to < current_from:
            return None
        duration = (current_to - current_from).days + 1
        previous_to = current_from - timedelta(days=1)
        previous = dict(filters)
        previous["date_from"] = fields.Date.to_string(previous_to - timedelta(days=duration - 1))
        previous["date_to"] = fields.Date.to_string(previous_to)
        return previous

    @api.model
    def _comparison(self, count, previous_count):
        delta = count - previous_count
        if not previous_count:
            return {"delta": delta, "delta_percent": None, "direction": "up" if delta > 0 else "flat"}
        percentage = (delta * 100.0) / previous_count
        return {"delta": delta, "delta_percent": round(percentage, 2),
                "direction": "up" if delta > 0 else "down" if delta < 0 else "flat"}

    @api.model
    def _add_comparison(self, current_kpis, previous_kpis):
        previous_by_code = {item["code"]: item["count"] for item in previous_kpis}
        result = []
        for item in current_kpis:
            current = dict(item)
            previous_count = previous_by_code.get(item["code"])
            current["previous_count"] = previous_count
            current.update(self._comparison(item["count"], previous_count) if previous_count is not None else {
                "delta": None, "delta_percent": None, "direction": "na",
            })
            result.append(current)
        return result

    @api.model
    def _overview_data(self, filters):
        tickets = self.env["it.helpdesk.ticket"].get_dashboard_data(filters)
        ticket_map = {item["code"]: item for item in tickets.get("kpis", [])}
        current_kpis = [
            ticket_map.get("open", {"code": "open", "label": "Open Tickets", "count": 0, "domain": []}),
            ticket_map.get("sla_overdue", {"code": "sla_overdue", "label": "SLA Overdue", "count": 0, "domain": []}),
        ]
        previous_filters = self._previous_period_filters(filters)
        previous_kpis = []
        if previous_filters:
            previous_tickets = self.env["it.helpdesk.ticket"].get_dashboard_data(previous_filters)
            previous_kpis = [{"code": code, "count": next(
                (item["count"] for item in previous_tickets["kpis"] if item["code"] == code), 0
            )} for code in ("open", "sla_overdue")]
        return {
            "kpis": self._add_comparison(current_kpis, previous_kpis),
            "tickets": tickets.get("status_overview", []),
            "charts": {
                "created_resolved": tickets["charts"]["created_resolved"],
                "ticket_backlog": tickets["charts"]["ticket_backlog"],
            },
            "recent_tickets": self._recent_tickets(filters),
            "options": self._options(),
        }

    @api.model
    def get_dashboard_data(self, section="overview", filters=None):
        self._check_access()
        if section not in ("overview", "helpdesk"):
            raise ValidationError("Unknown dashboard section.")
        filters = filters or {}
        if section == "helpdesk":
            data = self.env["it.helpdesk.ticket"].get_dashboard_data(filters)
            data.setdefault("options", {})["navigation"] = self._navigation()
            return data
        return self._overview_data(filters)
