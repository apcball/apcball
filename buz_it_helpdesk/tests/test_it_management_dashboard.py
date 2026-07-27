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
