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
        ticket.team_id.sudo().write({"member_ids": [fields.Command.link(self.agent.id)]})

        ticket.write({"subject": "Edited while Draft", "description": "<p>Draft details</p>", "category_id": self.category.id, "priority_id": self.priority.id, "requester_id": requester.id, "team_id": ticket.team_id.id, "company_id": ticket.company_id.id})
        self.assertFalse(ticket.sla_id)
        ticket.with_user(requester).action_confirm()
        self.assertEqual(ticket.with_user(self.agent).stage_id.name, "New")
        self.assertFalse(ticket.can_confirm)
        self.assertFalse(ticket.can_edit_ticket)
        activities = ticket.with_user(self.agent).activity_ids.filtered(
            lambda activity: activity.activity_type_id == self.env.ref("mail.mail_activity_data_todo")
            and activity.summary == "New IT Helpdesk Ticket"
        )
        self.assertIn(self.agent, activities.mapped("user_id"))
        ticket.with_user(self.agent).action_clear_new_ticket_activity()
        self.assertFalse(activities.exists())

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

    def test_dashboard_is_readonly_and_group_limited(self):
        data = self.ticket_model.with_user(self.agent).get_dashboard_data({"date_from": "2020-01-01", "date_to": "2030-12-31"})
        self.assertIn("kpis", data)
        self.assertIn("status_overview", data)
        with self.assertRaises(AccessError):
            self.ticket_model.with_user(self.env.user).get_dashboard_data({})

    def test_unassigned_ticket_is_supported(self):
        ticket = self.ticket_model.create({
            "subject": "Unassigned", "category_id": self.category.id, "priority_id": self.priority.id,
            "assigned_to": False,
        })
        self.assertFalse(ticket.assigned_to)

    def test_workflow_transitions_and_reopen_reset_sla_state(self):
        new_stage = self.env["it.helpdesk.stage"].search([("name", "=", "New")], limit=1)
        in_progress = self.env["it.helpdesk.stage"].search([("name", "=", "In Progress")], limit=1)
        pending = self.env["it.helpdesk.stage"].search([("name", "=", "Pending User")], limit=1)
        resolved = self.env["it.helpdesk.stage"].search([("name", "=", "Resolved")], limit=1)
        closed = self.env["it.helpdesk.stage"].search([("name", "=", "Closed")], limit=1)
        self.assertTrue(all((new_stage, in_progress, pending, resolved, closed)))

        ticket = self.ticket_model.with_user(self.agent).create(
            {"subject": "Workflow transition test", "category_id": self.category.id, "priority_id": self.priority.id}
        )
        ticket.team_id.sudo().write({"member_ids": [fields.Command.link(self.agent.id)]})
        ticket.write({"stage_id": new_stage.id})
        ticket._schedule_new_ticket_activities(users=self.agent)
        self.assertTrue(ticket.activity_ids)
        with self.assertRaises(UserError):
            ticket.write({"stage_id": resolved.id})

        ticket.action_assign()
        self.assertEqual(ticket.stage_id, in_progress)
        self.assertFalse(ticket.activity_ids.filtered(lambda activity: activity.summary == "New IT Helpdesk Ticket"))
        ticket.action_pending_user()
        self.assertEqual(ticket.stage_id, pending)
        ticket.action_in_progress()
        ticket.action_resolve()
        self.assertEqual(ticket.stage_id, resolved)
        self.assertTrue(ticket.resolved_at)
        ticket.action_close()
        self.assertEqual(ticket.stage_id, closed)

        ticket.with_context(skip_sla=True).write(
            {
                "sla_overdue_notified_at": fields.Datetime.now(),
                "sla_paused_hours": 3,
            }
        )
        ticket.action_reopen()
        self.assertEqual(ticket.stage_id, in_progress)
        self.assertFalse(ticket.resolved_at)
        self.assertFalse(ticket.sla_overdue_notified_at)
        self.assertEqual(ticket.sla_paused_hours, 0)

    def test_cancel_and_closed_ticket_guards(self):
        ticket = self.ticket_model.with_user(self.agent).create(
            {"subject": "Cancel transition test", "category_id": self.category.id, "priority_id": self.priority.id}
        )
        ticket.action_cancel()
        self.assertEqual(ticket.stage_code, "cancelled")
        with self.assertRaises(UserError):
            ticket.action_cancel()
        ticket.action_reopen()
        self.assertEqual(ticket.stage_code, "in_progress")

    def test_internal_note_does_not_count_as_first_response(self):
        ticket = self.ticket_model.with_user(self.agent).create(
            {"subject": "First response test", "category_id": self.category.id, "priority_id": self.priority.id}
        )
        ticket.message_post(body="Internal note", subtype_xmlid="mail.mt_note")
        self.assertFalse(ticket.first_response_at)
        ticket.message_post(body="External response", subtype_xmlid="mail.mt_comment")
        self.assertTrue(ticket.first_response_at)

    def test_requester_cannot_change_ticket_owner(self):
        requester = self.env["res.users"].create(
            {
                "name": "Workflow Requester",
                "login": "workflow.requester",
                "groups_id": [fields.Command.set(
                    [
                        self.env.ref("base.group_user").id,
                        self.env.ref("buz_it_helpdesk.group_it_helpdesk_requester").id,
                    ]
                )],
            }
        )
        ticket = self.ticket_model.with_user(requester).create(
            {"subject": "Owner protection", "category_id": self.category.id, "priority_id": self.priority.id}
        )
        with self.assertRaises(AccessError):
            ticket.write({"requester_id": self.agent.id})

    def test_category_priority_change_requires_reason_after_confirmation(self):
        ticket = self.ticket_model.with_user(self.agent).create(
            {"subject": "SLA reason test", "category_id": self.category.id, "priority_id": self.priority.id}
        )
        new_stage = self.env["it.helpdesk.stage"].search([("name", "=", "New")], limit=1)
        ticket.write({"stage_id": new_stage.id})
        category = self.env.ref("buz_it_helpdesk.category_software")
        with self.assertRaises(UserError):
            ticket.write({"category_id": category.id})
        ticket.with_context(sla_change_reason="Customer reclassification").write(
            {"category_id": category.id}
        )