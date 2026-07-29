from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestPhase7RegressionSecurity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.requester_group = cls.env.ref("buz_it_helpdesk.group_it_helpdesk_requester")
        cls.agent_group = cls.env.ref("buz_it_helpdesk.group_it_helpdesk_agent")
        cls.agent = cls.env["res.users"].sudo().create({
            "name": "Phase 7 Agent", "login": "phase7.agent.final",
            "groups_id": [fields.Command.set([cls.env.ref("base.group_user").id, cls.agent_group.id])],
        })
        cls.requester = cls.env["res.users"].sudo().create({
            "name": "Phase 7 Requester", "login": "phase7.requester.final",
            "groups_id": [fields.Command.set([cls.env.ref("base.group_user").id, cls.requester_group.id])],
        })

    def test_role_matrix_and_asset_section_removal(self):
        dashboard = self.env["it.management.dashboard"]
        with self.assertRaises(AccessError):
            dashboard.with_user(self.requester).get_dashboard_data("helpdesk", {})
        navigation = dashboard.with_user(self.agent)._navigation()
        self.assertEqual([item["section"] for item in navigation], ["helpdesk"])

    def test_email_intake_does_not_enqueue_outbound_mail(self):
        ticket_model = self.env["it.helpdesk.ticket"].with_user(self.agent)
        before = self.env["mail.mail"].sudo().search_count([])
        ticket_id = ticket_model.message_new({"subject": "Phase 7 inbound email", "body": "<p>Inbound</p>"})
        self.assertEqual(self.env["mail.mail"].sudo().search_count([]), before)
        self.assertEqual(ticket_model.browse(ticket_id).source, "email")
