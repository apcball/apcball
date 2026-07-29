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
            "name": "Dashboard Agent", "login": "dashboard.agent.final",
            "groups_id": [fields.Command.set([cls.env.ref("base.group_user").id, cls.agent_group.id])],
        })
        cls.requester = cls.env["res.users"].sudo().create({
            "name": "Dashboard Requester", "login": "dashboard.requester.final",
            "groups_id": [fields.Command.set([cls.env.ref("base.group_user").id, cls.requester_group.id])],
        })

    def test_dashboard_has_only_helpdesk_sections(self):
        dashboard = self.env["it.management.dashboard"].with_user(self.agent)
        navigation = dashboard._navigation()
        self.assertEqual({item["section"] for item in navigation}, {"overview", "helpdesk"})
        self.assertEqual({item["label"] for item in navigation}, {"Dashboard", "Helpdesk"})

    def test_dashboard_rejects_asset_section_and_requester(self):
        dashboard = self.env["it.management.dashboard"]
        with self.assertRaises(ValidationError):
            dashboard.with_user(self.agent).get_dashboard_data("asset", {})
        with self.assertRaises(AccessError):
            dashboard.with_user(self.requester).get_dashboard_data("overview", {})

    def test_overview_contains_only_helpdesk_payload(self):
        data = self.env["it.management.dashboard"].with_user(self.agent).get_dashboard_data(
            "overview", {"date_from": "2026-01-01", "date_to": "2026-12-31"}
        )
        self.assertEqual({item["code"] for item in data["kpis"]}, {"open", "sla_overdue"})
        self.assertEqual(set(data["charts"]), {"created_resolved", "ticket_backlog"})
        self.assertNotIn("assets", data)
        self.assertNotIn("renewals_due", data)
