from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestPhase7RegressionSecurity(TransactionCase):
    """Regression and security checks required before UAT."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.other_company = cls.env["res.company"].sudo().create(
            {"name": "Phase 7 Other Company"}
        )
        cls.requester_group = cls.env.ref("buz_it_helpdesk.group_it_helpdesk_requester")
        cls.agent_group = cls.env.ref("buz_it_helpdesk.group_it_helpdesk_agent")
        cls.manager_group = cls.env.ref("buz_it_helpdesk.group_it_helpdesk_manager")

        def make_user(login, name, group):
            return cls.env["res.users"].sudo().create(
                {
                    "name": name,
                    "login": login,
                    "company_id": cls.company.id,
                    "company_ids": [fields.Command.link(cls.company.id)],
                    "groups_id": [
                        fields.Command.set(
                            [cls.env.ref("base.group_user").id, group.id]
                        )
                    ],
                }
            )

        cls.requester = make_user(
            "phase7.requester", "Phase 7 Requester", cls.requester_group
        )
        cls.agent = make_user("phase7.agent", "Phase 7 Agent", cls.agent_group)
        cls.manager = make_user(
            "phase7.manager", "Phase 7 Manager", cls.manager_group
        )

    def test_phase_7_role_matrix_and_dashboard_asset_boundary(self):
        dashboard = self.env["it.management.dashboard"]
        with self.assertRaises(AccessError):
            dashboard.with_user(self.requester).get_dashboard_data("overview", {})

        agent_data = dashboard.with_user(self.agent).get_dashboard_data("asset", {})
        manager_data = dashboard.with_user(self.manager).get_dashboard_data("asset", {})
        self.assertIn("kpis", agent_data)
        self.assertIn("kpis", manager_data)
        self.assertNotIn("license_key", repr(agent_data).lower())

        asset = self.env["buz.it.asset"].with_user(self.agent).create(
            {
                "asset_name": "Phase 7 security asset",
                "company_id": self.company.id,
            }
        )
        other_asset = self.env["buz.it.asset"].sudo().with_company(
            self.other_company
        ).create(
            {
                "asset_name": "Phase 7 other-company asset",
                "company_id": self.other_company.id,
            }
        )
        visible = self.env["buz.it.asset"].with_user(self.agent).search(
            [("id", "in", [asset.id, other_asset.id])]
        )
        self.assertIn(asset.id, visible.ids)
        self.assertNotIn(other_asset.id, visible.ids)

    def test_phase_7_email_intake_does_not_enqueue_outbound_mail(self):
        ticket_model = self.env["it.helpdesk.ticket"].with_user(self.agent)
        before = self.env["mail.mail"].sudo().search_count([])
        ticket = ticket_model.message_new(
            {"subject": "Phase 7 inbound email", "body": "<p>Inbound</p>"}
        )
        after = self.env["mail.mail"].sudo().search_count([])
        self.assertEqual(after, before)
        self.assertEqual(ticket_model.browse(ticket).source, "email")