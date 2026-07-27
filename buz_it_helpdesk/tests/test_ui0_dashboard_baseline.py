from datetime import date

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestUI0DashboardBaseline(TransactionCase):
    """Small source-record fixture for the UI-0 contract only."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.agent_group = cls.env.ref("buz_it_helpdesk.group_it_helpdesk_agent")
        cls.requester_group = cls.env.ref("buz_it_helpdesk.group_it_helpdesk_requester")
        cls.agent = cls.env["res.users"].sudo().create({
            "name": "UI-0 Dashboard Agent", "login": "ui0.dashboard.agent",
            "company_id": cls.company.id,
            "company_ids": [fields.Command.link(cls.company.id)],
            "groups_id": [fields.Command.set([
                cls.env.ref("base.group_user").id, cls.agent_group.id,
            ])],
        })
        cls.requester = cls.env["res.users"].sudo().create({
            "name": "UI-0 Dashboard Requester", "login": "ui0.dashboard.requester",
            "company_id": cls.company.id,
            "company_ids": [fields.Command.link(cls.company.id)],
            "groups_id": [fields.Command.set([
                cls.env.ref("base.group_user").id, cls.requester_group.id,
            ])],
        })
        cls.stage = cls.env["it.helpdesk.stage"].sudo().create({
            "name": "UI-0 New", "company_id": cls.company.id, "sequence": 1,
        })
        cls.category = cls.env["it.helpdesk.category"].sudo().create({
            "name": "UI-0 Category", "company_id": cls.company.id,
        })
        cls.priority = cls.env["it.helpdesk.priority"].sudo().create({
            "name": "UI-0 Priority", "code": "medium", "company_id": cls.company.id,
        })
        cls.ticket = cls.env["it.helpdesk.ticket"].sudo().create({
            "subject": "UI-0 baseline ticket", "description": "UI-0 fixture",
            "requester_id": cls.requester.id, "company_id": cls.company.id,
            "stage_id": cls.stage.id, "category_id": cls.category.id,
            "priority_id": cls.priority.id,
        })
        cls.asset = cls.env["buz.it.asset"].with_user(cls.agent).create({
            "asset_type": "software_license", "asset_name": "UI-0 baseline license",
            "company_id": cls.company.id, "license_product": "UI-0 Fixture License",
            "license_version": "1", "license_start_date": date(2026, 1, 1),
            "license_expiry_date": date(2026, 12, 31), "license_seats": 1,
        })
        cls.renewal = cls.env["buz.it.asset.renewal"].with_user(cls.agent).create({
            "asset_id": cls.asset.id, "start_date": date(2026, 1, 1),
        })

    def test_ui0_sections_and_source_record_traceability(self):
        dashboard = self.env["it.management.dashboard"].with_user(self.agent)
        filters = {"company_id": self.company.id, "date_from": "2026-01-01", "date_to": "2026-12-31"}
        overview = dashboard.get_dashboard_data("overview", filters)
        helpdesk = dashboard.get_dashboard_data("helpdesk", filters)
        asset = dashboard.get_dashboard_data("asset", filters)
        self.assertIn("open", {item["code"] for item in overview["kpis"]})
        license_kpi = next(item for item in asset["kpis"] if item["code"] == "license_expiring")
        self.assertEqual(license_kpi["count"], 1)
        self.assertIn(self.asset.id, self.env["buz.it.asset"].search(license_kpi["domain"]).ids)
        self.assertIn(self.ticket.id, self.env["it.helpdesk.ticket"].search(helpdesk["domain"]).ids)
        self.assertTrue(self.renewal.exists())
        self.assertIn("status_overview", helpdesk)
        self.assertIn("status", asset)

    def test_ui0_role_company_and_action_contract(self):
        dashboard = self.env["it.management.dashboard"]
        with self.assertRaises(AccessError):
            dashboard.with_user(self.requester).get_dashboard_data("overview", {})
        other_company = self.env["res.company"].sudo().create({"name": "UI-0 Other Company"})
        self.assertEqual(
            dashboard.with_user(self.agent)._company_domain({"company_id": other_company.id}),
            [("id", "=", 0)],
        )
        for xml_id in (
            "action_helpdesk_dashboard_overview", "action_helpdesk_report",
            "action_buz_it_asset_software_licenses", "action_buz_it_asset_renewals",
            "action_buz_it_asset_notification_config", "action_helpdesk_categories",
            "action_helpdesk_priorities", "action_helpdesk_stages", "action_helpdesk_tags",
            "action_helpdesk_teams", "action_buz_it_asset_categories",
            "action_buz_it_asset_spec_categories", "action_buz_it_asset_software",
        ):
            self.assertTrue(self.env.ref("buz_it_helpdesk.%s" % xml_id))
