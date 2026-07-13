from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestHelpdeskTicket(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ticket_model = cls.env["it.helpdesk.ticket"]
        cls.category = cls.env.ref("buz_it_helpdesk.category_hardware")
        cls.priority = cls.env.ref("buz_it_helpdesk.priority_high")
        cls.agent = cls.env.ref("base.user_admin")

    def test_requester_uses_standard_chatter_followers(self):
        ticket = self.ticket_model.with_user(self.agent).create({
            "subject": "Monitor failure", "category_id": self.category.id, "priority_id": self.priority.id,
        })
        self.assertFalse("follower_ids" in self.ticket_model._fields)
        self.assertIn(self.agent.partner_id, ticket.message_follower_ids.mapped("partner_id"))

    def test_requester_can_create_ticket_with_default_team(self):
        requester = self.env["res.users"].create({
            "name": "Helpdesk Requester Test",
            "login": "helpdesk.requester.test",
            "groups_id": [fields.Command.set([
                self.env.ref("base.group_user").id,
                self.env.ref("buz_it_helpdesk.group_it_helpdesk_requester").id,
            ])],
        })

        ticket = self.ticket_model.with_user(requester).create({
            "subject": "Requester save test",
            "category_id": self.category.id,
            "priority_id": self.priority.id,
        })

        self.assertEqual(ticket.requester_id, requester)
        self.assertTrue(ticket.team_id)
        self.assertTrue(ticket.can_confirm)
        self.assertTrue(ticket.can_edit_ticket)

        ticket.write({"subject": "Edited while Draft"})
        ticket.with_user(requester).action_confirm()
        self.assertEqual(ticket.with_user(self.agent).stage_id.name, "New")
        self.assertFalse(ticket.can_confirm)
        self.assertFalse(ticket.can_edit_ticket)

        with self.assertRaises(AccessError):
            ticket.write({"subject": "Edit after Confirm"})

    def test_requester_must_confirm_draft_ticket(self):
        ticket = self.ticket_model.with_user(self.agent).create({
            "subject": "Confirmation test", "category_id": self.category.id, "priority_id": self.priority.id,
        })
        self.assertEqual(ticket.stage_id.name, "Draft")
        ticket.with_user(self.agent).action_confirm()
        self.assertEqual(ticket.with_user(self.agent).stage_id.name, "New")

    def test_overdue_and_sla_metrics(self):
        ticket = self.ticket_model.create({
            "subject": "SLA test", "category_id": self.category.id, "priority_id": self.priority.id,
        })
        ticket.write({"sla_deadline": fields.Datetime.now() - timedelta(hours=1)})
        self.assertTrue(ticket.is_overdue)

    def test_closed_ticket_requires_resolved_stage(self):
        ticket = self.ticket_model.create({
            "subject": "Status test", "category_id": self.category.id, "priority_id": self.priority.id,
        })
        closed = self.env["it.helpdesk.stage"].search([("name", "=", "Closed")], limit=1)
        with self.assertRaises(UserError):
            ticket.action_close()
        self.assertTrue(closed)

    def test_unassigned_ticket_is_supported(self):
        ticket = self.ticket_model.create({
            "subject": "Unassigned", "category_id": self.category.id, "priority_id": self.priority.id,
            "assigned_to": False,
        })
        self.assertFalse(ticket.assigned_to)
