from datetime import date

from odoo import fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase


class TestItManagementDashboard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.agent_group = cls.env.ref("buz_it_helpdesk.group_it_helpdesk_agent")
        cls.requester_group = cls.env.ref("buz_it_helpdesk.group_it_helpdesk_requester")
        cls.agent = cls.env["res.users"].sudo().create({
            "name": "Dashboard Agent", "login": "dashboard.agent.6",
            "groups_id": [fields.Command.set([cls.env.ref("base.group_user").id, cls.agent_group.id])],
        })
        cls.requester = cls.env["res.users"].sudo().create({
            "name": "Dashboard Requester", "login": "dashboard.requester.6",
            "groups_id": [fields.Command.set([cls.env.ref("base.group_user").id, cls.requester_group.id])],
        })

    def _asset(self, status="in_use", asset_type="computer"):
        values = {
            "asset_type": asset_type, "asset_name": "Dashboard Asset",
            "company_id": self.env.company.id,
            "assigned_user_id": self.agent.id if status == "in_use" else False,
        }
        if asset_type == "software_license":
            values.update({
                "license_product": "Dashboard License", "license_version": "1",
                "license_start_date": date(2026, 1, 1), "license_expiry_date": date(2026, 12, 31),
                "license_seats": 1,
            })
        asset = self.env["buz.it.asset"].with_user(self.agent).create(values)
        if status not in ("available", "in_use"):
            asset.write({"status": status})
        return asset

    def test_phase_6_agent_can_load_asset_dashboard_and_drilldown_domains(self):
        asset = self._asset()
        self._asset(status="repair")
        self._asset(asset_type="software_license")
        data = self.env["it.management.dashboard"].with_user(self.agent).get_dashboard_data(
            "asset", {"company_id": self.env.company.id, "date_from": "2026-01-01", "date_to": "2026-12-31"}
        )
        self.assertEqual({item["code"] for item in data["kpis"]}, {"in_use", "repair", "license_expiring"})
        self.assertEqual(next(item for item in data["kpis"] if item["code"] == "in_use")["count"], 1)
        self.assertTrue(next(item for item in data["kpis"] if item["code"] == "in_use")["domain"])
        self.assertNotIn("license_key", repr(data).lower())
        self.assertIn(asset.id, self.env["buz.it.asset"].search(
            next(item for item in data["kpis"] if item["code"] == "in_use")["domain"]
        ).ids)

    def test_phase_6_dashboard_rejects_requester_and_invalid_section(self):
        dashboard = self.env["it.management.dashboard"]
        with self.assertRaises(AccessError):
            dashboard.with_user(self.requester).get_dashboard_data("asset", {})
        with self.assertRaises(ValidationError):
            dashboard.with_user(self.agent).get_dashboard_data("secret", {})

    def test_phase_6_company_filter_cannot_escape_allowed_companies(self):
        other_company = self.env["res.company"].sudo().create({"name": "Dashboard Other Company"})
        dashboard = self.env["it.management.dashboard"].with_user(self.agent)
        domain = dashboard._company_domain({"company_id": other_company.id})
        self.assertEqual(domain, [("id", "=", 0)])
    def test_phase_6_overview_and_helpdesk_sections_return_server_kpis(self):
        dashboard = self.env["it.management.dashboard"].with_user(self.agent)
        overview = dashboard.get_dashboard_data("overview", {"date_from": "2026-01-01", "date_to": "2026-12-31"})
        self.assertEqual(
            {item["code"] for item in overview["kpis"]},
            {"open", "sla_overdue", "in_use", "repair", "license_expiring"},
        )
        helpdesk = dashboard.get_dashboard_data("helpdesk", {"date_from": "2026-01-01", "date_to": "2026-12-31"})
        self.assertIn("kpis", helpdesk)
        self.assertIn("status_overview", helpdesk)

    def test_ui2_previous_period_is_adjacent_and_comparison_handles_zero(self):
        dashboard = self.env["it.management.dashboard"].with_user(self.agent)
        previous = dashboard._previous_period_filters({
            "company_id": self.env.company.id,
            "date_from": "2026-01-01",
            "date_to": "2026-01-31",
        })
        self.assertEqual(previous["date_from"], "2025-12-01")
        self.assertEqual(previous["date_to"], "2025-12-31")
        self.assertLess(previous["date_to"], "2026-01-01")
        self.assertEqual(dashboard._comparison(12, 8), {
            "delta": 4, "delta_percent": 50.0, "direction": "up",
        })
        self.assertEqual(dashboard._comparison(3, 0), {
            "delta": 3, "delta_percent": None, "direction": "up",
        })

    def test_ui2_five_kpis_match_source_record_counts_and_domains(self):
        dashboard = self.env["it.management.dashboard"].with_user(self.agent)
        filters = {
            "company_id": self.env.company.id,
            "date_from": "2026-01-01",
            "date_to": "2026-12-31",
        }
        data = dashboard.get_dashboard_data("overview", filters)
        self.assertEqual(
            {item["code"] for item in data["kpis"]},
            {"open", "sla_overdue", "in_use", "repair", "license_expiring"},
        )
        for item in data["kpis"]:
            model_name = (
                "it.helpdesk.ticket"
                if item["code"] in {"open", "sla_overdue"}
                else "buz.it.asset"
            )
            self.assertEqual(
                item["count"],
                self.env[model_name].search_count(item["domain"]),
                item["code"],
            )

            self.assertNotIn("license_key", repr(item).lower())
            self.assertNotIn("password", repr(item).lower())

    def test_ui2_overview_comparison_payload_has_no_secret_fields(self):
        dashboard = self.env["it.management.dashboard"].with_user(self.agent)
        data = dashboard.get_dashboard_data(
            "overview",
            {"date_from": "2026-01-01", "date_to": "2026-12-31"},
        )
        for item in data["kpis"]:
            self.assertIn("previous_count", item)
            self.assertIn("delta", item)
            self.assertIn("delta_percent", item)
            self.assertIn("direction", item)
            self.assertNotIn("license_key", item)
            self.assertNotIn("secret", item)
    def test_ui3_created_resolved_series_fills_empty_days_and_domains(self):
        ticket_model = self.env["it.helpdesk.ticket"].with_user(self.agent)
        filters = {
            "company_id": self.env.company.id,
            "date_from": "2026-01-01",
            "date_to": "2026-01-03",
        }
        chart = ticket_model.get_chart_data(filters)
        self.assertEqual([row["date"] for row in chart["series"]], ["2026-01-01", "2026-01-02", "2026-01-03"])
        for row in chart["series"]:
            self.assertEqual(row["created_count"], ticket_model.search_count(row["created_domain"]))
            self.assertEqual(row["resolved_count"], ticket_model.search_count(row["resolved_domain"]))
            self.assertIn(("company_id", "=", self.env.company.id), row["created_domain"])
            self.assertIn(("company_id", "=", self.env.company.id), row["resolved_domain"])

    def test_ui3_backlog_excludes_closed_and_cancelled(self):
        data = self.env["it.management.dashboard"].with_user(self.agent).get_dashboard_data(
            "helpdesk",
            {"company_id": self.env.company.id, "date_from": "2026-01-01", "date_to": "2026-01-03"},
        )
        rows = data["charts"]["ticket_backlog"]["rows"]
        self.assertFalse({row["code"] for row in rows} & {"closed", "cancelled"})
        for row in rows:
            self.assertEqual(
                row["count"],
                self.env["it.helpdesk.ticket"].search_count(row["domain"]),
            )

    def test_ui3_asset_status_percentages_and_drilldown(self):
        dashboard = self.env["it.management.dashboard"].with_user(self.agent)
        self._asset(status="available")
        self._asset(status="repair")
        data = dashboard.get_dashboard_data(
            "overview",
            {"company_id": self.env.company.id, "date_from": "2026-01-01", "date_to": "2026-12-31"},
        )
        chart = data["charts"]["asset_status"]
        self.assertEqual(chart["total"], sum(row["count"] for row in chart["rows"]))
        self.assertAlmostEqual(sum(row["percentage"] for row in chart["rows"]), 100.0, places=2)
        for row in chart["rows"]:
            self.assertEqual(row["count"], self.env["buz.it.asset"].search_count(row["domain"]))

    def test_ui3_empty_data_returns_zero_series_and_zero_asset_total(self):
        dashboard = self.env["it.management.dashboard"].with_user(self.agent)
        filters = {"company_id": self.env.company.id, "date_from": "1990-01-01", "date_to": "1990-01-03"}
        chart = self.env["it.helpdesk.ticket"].with_user(self.agent).get_chart_data(filters)
        self.assertEqual(len(chart["series"]), 3)
        self.assertTrue(all(row["created_count"] == 0 and row["resolved_count"] == 0 for row in chart["series"]))
        asset_chart = dashboard.get_dashboard_data("overview", filters)["charts"]["asset_status"]
        self.assertEqual(asset_chart["total"], 0)
        self.assertTrue(all(row["percentage"] == 0.0 for row in asset_chart["rows"]))