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
