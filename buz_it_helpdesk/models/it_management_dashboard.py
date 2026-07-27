from datetime import datetime, timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError


class ItManagementDashboard(models.Model):
    _name = "it.management.dashboard"
    _auto = False
    _description = "IT Management Unified Dashboard"

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
    def _options(self):
        return {
            "companies": [
                {"id": company.id, "label": company.display_name}
                for company in self.env.companies
            ],
        }

    @api.model
    def _previous_period_filters(self, filters):
        """Return a non-overlapping period with the same duration."""
        filters = filters or {}
        date_from = filters.get("date_from")
        date_to = filters.get("date_to")
        if not date_from or not date_to:
            return None
        try:
            current_from = datetime.strptime(date_from, "%Y-%m-%d").date()
            current_to = datetime.strptime(date_to, "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return None
        if current_to < current_from:
            return None
        duration = (current_to - current_from).days + 1
        previous_to = current_from - timedelta(days=1)
        previous_from = previous_to - timedelta(days=duration - 1)
        previous = dict(filters)
        previous["date_from"] = fields.Date.to_string(previous_from)
        previous["date_to"] = fields.Date.to_string(previous_to)
        return previous

    @api.model
    def _comparison(self, count, previous_count):
        delta = count - previous_count
        if not previous_count:
            return {"delta": delta, "delta_percent": None, "direction": "up" if delta > 0 else "flat"}
        percentage = (delta * 100.0) / previous_count
        return {
            "delta": delta,
            "delta_percent": round(percentage, 2),
            "direction": "up" if delta > 0 else "down" if delta < 0 else "flat",
        }

    @api.model
    def _add_comparison(self, current_kpis, previous_kpis):
        previous_by_code = {item["code"]: item["count"] for item in previous_kpis}
        result = []
        for item in current_kpis:
            current = dict(item)
            previous_count = previous_by_code.get(item["code"])
            current["previous_count"] = previous_count
            current.update(
                self._comparison(item["count"], previous_count)
                if previous_count is not None
                else {"delta": None, "delta_percent": None, "direction": "na"}
            )
            result.append(current)
        return result

    @api.model
    def _asset_data(self, filters):
        domain = self._company_domain(filters)
        Asset = self.env["buz.it.asset"]
        status_specs = (
            ("in_use", "In Use"), ("available", "Available"),
            ("repair", "Under Repair"), ("lost", "Lost"), ("retired", "Retired"),
        )
        kpis = []
        for code, label, extra_domain in (
            ("in_use", "Asset In Use", [("status", "=", "in_use")]),
            ("repair", "Under Repair", [("status", "=", "repair")]),
            ("license_expiring", "License Expiring", [
                ("asset_type", "=", "software_license"),
                ("license_expiry_date", "!=", False),
                ("license_expiry_date", ">=", filters.get("date_from") or fields.Date.context_today(self)),
                ("license_expiry_date", "<=", filters.get("date_to") or fields.Date.context_today(self),),
            ]),
        ):
            count_domain = list(domain) + extra_domain
            kpis.append({"code": code, "label": label, "count": Asset.search_count(count_domain), "domain": count_domain})

        def grouped(field_name):
            rows = []
            for group in Asset.read_group(domain, [field_name], [field_name], lazy=False):
                value = group.get(field_name)
                value_id, label = value if isinstance(value, (list, tuple)) else (False, "Unassigned")
                rows.append({
                    "id": value_id, "label": label or "Unassigned",
                    "count": group.get("%s_count" % field_name, group.get("__count", 0)),
                    "domain": list(domain) + [(field_name, "=", value_id)],
                })
            return sorted(rows, key=lambda row: (-row["count"], row["label"]))[:12]

        status_rows = []
        for code, label in status_specs:
            status_domain = list(domain) + [("status", "=", code)]
            status_rows.append({"code": code, "label": label, "count": Asset.search_count(status_domain), "domain": status_domain})
        total = sum(row["count"] for row in status_rows)
        for row in status_rows:
            row["percentage"] = round((row["count"] * 100.0) / total, 2) if total else 0.0
        asset_status_chart = {"total": total, "rows": status_rows}
        type_rows = grouped("asset_type")
        department_rows = grouped("department_id")
        repair_domain = list(domain) + [("status", "=", "repair")]
        return {
            "kpis": kpis,
            "status": status_rows,
            "types": type_rows,
            "departments": department_rows,
            "repair": {"count": Asset.search_count(repair_domain), "domain": repair_domain},
            "charts": {"asset_status": asset_status_chart},
            "options": self._options(),
        }

    @api.model
    def _overview_data(self, filters):
        tickets = self.env["it.helpdesk.ticket"].get_dashboard_data(filters)
        assets = self._asset_data(filters)
        ticket_map = {item["code"]: item for item in tickets.get("kpis", [])}
        asset_map = {item["code"]: item for item in assets["kpis"]}
        current_kpis = [
            ticket_map.get("open", {"code": "open", "label": "Open Tickets", "count": 0, "domain": []}),
            ticket_map.get("sla_overdue", {"code": "sla_overdue", "label": "SLA Overdue", "count": 0, "domain": []}),
            asset_map["in_use"], asset_map["repair"], asset_map["license_expiring"],
        ]
        previous_filters = self._previous_period_filters(filters)
        if previous_filters:
            previous_tickets = self.env["it.helpdesk.ticket"].get_dashboard_data(previous_filters)
            previous_assets = self._asset_data(previous_filters)
            previous_kpis = [
                {"code": "open", "count": next((item["count"] for item in previous_tickets["kpis"] if item["code"] == "open"), 0)},
                {"code": "sla_overdue", "count": next((item["count"] for item in previous_tickets["kpis"] if item["code"] == "sla_overdue"), 0)},
                next(item for item in previous_assets["kpis"] if item["code"] == "in_use"),
                next(item for item in previous_assets["kpis"] if item["code"] == "repair"),
                next(item for item in previous_assets["kpis"] if item["code"] == "license_expiring"),
            ]
            current_kpis = self._add_comparison(current_kpis, previous_kpis)
        else:
            current_kpis = self._add_comparison(current_kpis, [])
        return {
            "kpis": current_kpis,
            "tickets": tickets.get("status_overview", []),
            "assets": assets["status"],
            "charts": {
                "created_resolved": tickets["charts"]["created_resolved"],
                "ticket_backlog": tickets["charts"]["ticket_backlog"],
                "asset_status": assets["charts"]["asset_status"],
            },
            "options": assets["options"],
        }

    @api.model
    def get_dashboard_data(self, section="overview", filters=None):
        self._check_access()
        if section not in ("overview", "helpdesk", "asset"):
            raise ValidationError("Unknown dashboard section.")
        filters = filters or {}
        if section == "helpdesk":
            return self.env["it.helpdesk.ticket"].get_dashboard_data(filters)
        if section == "asset":
            return self._asset_data(filters)
        return self._overview_data(filters)
