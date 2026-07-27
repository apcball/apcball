from types import SimpleNamespace

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestHelpdeskTicket(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.other_company = cls.env["res.company"].sudo().create({"name": "BUZ Helpdesk Test Other Company"})

        cls.group_user = cls.env.ref("base.group_user")
        cls.group_requester = cls.env.ref("buz_it_helpdesk.group_it_helpdesk_requester")
        cls.group_agent = cls.env.ref("buz_it_helpdesk.group_it_helpdesk_agent")
        cls.group_manager = cls.env.ref("buz_it_helpdesk.group_it_helpdesk_manager")

        cls.stage_draft = cls.env["it.helpdesk.stage"].sudo().create(
            {"name": "Draft", "company_id": cls.company.id, "sequence": 1}
        )
        cls.stage_new = cls.env["it.helpdesk.stage"].sudo().create(
            {"name": "New", "company_id": cls.company.id, "sequence": 2}
        )
        cls.other_stage_new = cls.env["it.helpdesk.stage"].sudo().create(
            {"name": "New", "company_id": cls.other_company.id, "sequence": 2}
        )
        cls.category = cls.env["it.helpdesk.category"].sudo().create(
            {"name": "Test Category", "company_id": cls.company.id}
        )
        cls.priority = cls.env["it.helpdesk.priority"].sudo().create(
            {"name": "Test Priority", "code": "medium", "company_id": cls.company.id}
        )
        cls.other_category = cls.env["it.helpdesk.category"].sudo().create(
            {"name": "Other Category", "company_id": cls.other_company.id}
        )
        cls.other_priority = cls.env["it.helpdesk.priority"].sudo().create(
            {"name": "Other Priority", "code": "low", "company_id": cls.other_company.id}
        )

        cls.member_a = cls._create_internal_user("helpdesk.member.a", "Helpdesk Member A")
        cls.member_b = cls._create_internal_user("helpdesk.member.b", "Helpdesk Member B")
        cls.member_c = cls._create_internal_user("helpdesk.member.c", "Helpdesk Member C")
        cls.member_d = cls._create_internal_user("helpdesk.member.d", "Helpdesk Member D")
        cls.requester = cls._create_internal_user(
            "helpdesk.requester",
            "Helpdesk Requester",
            groups=[cls.group_requester],
        )
        cls.agent = cls._create_internal_user(
            "helpdesk.agent",
            "Helpdesk Agent",
            groups=[cls.group_agent],
        )
        cls.manager = cls._create_internal_user(
            "helpdesk.manager",
            "Helpdesk Manager",
            groups=[cls.group_manager],
        )

        cls.team = cls.env["it.helpdesk.team"].sudo().create(
            {
                "name": "Test Helpdesk Team",
                "company_id": cls.company.id,
                "member_ids": [
                    fields.Command.link(cls.member_a.id),
                    fields.Command.link(cls.member_b.id),
                    fields.Command.link(cls.member_c.id),
                ],
            }
        )

    @classmethod
    def _create_internal_user(cls, login, name, groups=None):
        return cls.env["res.users"].with_context(no_reset_password=True).sudo().create(
            {
                "name": name,
                "login": login,
                "email": "%s@example.com" % login,
                "company_id": cls.company.id,
                "company_ids": [fields.Command.link(cls.company.id)],
                "groups_id": [fields.Command.link(group.id) for group in (groups or [cls.group_user])],
            }
        )

    def _make_upload(self, filename, payload):
        return SimpleNamespace(filename=filename, read=lambda: payload)

    def test_responsible_users_become_followers_and_receive_activities_after_assignment_changes(self):
        ticket = self.env["it.helpdesk.ticket"].with_context(mail_create_nosubscribe=True).sudo().create(
            {
                "subject": "Assignment notification test",
                "description": "Test body",
                "requester_id": self.requester.id,
                "company_id": self.company.id,
                "stage_id": self.stage_draft.id,
                "category_id": self.category.id,
                "priority_id": self.priority.id,
                "team_id": self.team.id,
                "assigned_to": self.member_a.id,
                "assignee_ids": [fields.Command.link(self.member_b.id)],
            }
        )

        follower_partner_ids = set(ticket.message_follower_ids.mapped("partner_id").ids)
        self.assertTrue({self.requester.partner_id.id, self.member_a.partner_id.id, self.member_b.partner_id.id}.issubset(follower_partner_ids))

        ticket.with_user(self.requester).action_confirm()
        activity_user_ids = set(ticket.activity_ids.mapped("user_id").ids)
        self.assertSetEqual(activity_user_ids, {self.member_a.id, self.member_b.id, self.member_c.id})

        ticket.with_user(self.agent).write(
            {
                "assigned_to": self.member_c.id,
                "assignee_ids": [fields.Command.set([self.member_b.id, self.member_d.id])],
            }
        )

        follower_partner_ids = set(ticket.message_follower_ids.mapped("partner_id").ids)
        self.assertTrue({self.member_c.partner_id.id, self.member_d.partner_id.id}.issubset(follower_partner_ids))
        activity_user_ids = ticket.activity_ids.mapped("user_id").ids
        self.assertEqual(sorted(activity_user_ids), sorted({self.member_a.id, self.member_b.id, self.member_c.id, self.member_d.id}))
        self.assertEqual(len(ticket.activity_ids.filtered(lambda activity: activity.user_id == self.member_c)), 1)

    def test_portal_uploads_link_to_ticket_attachments(self):
        ticket = self.env["it.helpdesk.ticket"].sudo().create(
            {
                "subject": "Attachment linkage test",
                "description": "Test body",
                "requester_id": self.requester.id,
                "company_id": self.company.id,
                "stage_id": self.stage_draft.id,
                "category_id": self.category.id,
                "priority_id": self.priority.id,
            }
        )

        ticket.sudo()._add_uploaded_attachments([self._make_upload("create.txt", b"create payload")])
        ticket.sudo()._add_uploaded_attachments([self._make_upload("reply.txt", b"reply payload")])

        self.assertEqual(set(ticket.attachment_ids.mapped("name")), {"create.txt", "reply.txt"})
        self.assertTrue(all(att.res_model == ticket._name and att.res_id == ticket.id for att in ticket.attachment_ids))

    def test_manager_sees_drafts_and_agent_does_not_see_other_users_drafts(self):
        draft_ticket = self.env["it.helpdesk.ticket"].sudo().create(
            {
                "subject": "Draft visibility test",
                "description": "Draft body",
                "requester_id": self.requester.id,
                "company_id": self.company.id,
                "stage_id": self.stage_draft.id,
                "category_id": self.category.id,
                "priority_id": self.priority.id,
            }
        )
        new_ticket = self.env["it.helpdesk.ticket"].sudo().create(
            {
                "subject": "New visibility test",
                "description": "New body",
                "requester_id": self.requester.id,
                "company_id": self.company.id,
                "stage_id": self.stage_new.id,
                "category_id": self.category.id,
                "priority_id": self.priority.id,
            }
        )
        other_ticket = self.env["it.helpdesk.ticket"].sudo().create(
            {
                "subject": "Other company test",
                "description": "Other body",
                "requester_id": self.requester.id,
                "company_id": self.other_company.id,
                "stage_id": self.other_stage_new.id,
                "category_id": self.other_category.id,
                "priority_id": self.other_priority.id,
            }
        )

        domain = [("id", "in", [draft_ticket.id, new_ticket.id, other_ticket.id])]
        manager_ids = set(self.env["it.helpdesk.ticket"].with_user(self.manager).search(domain).ids)
        agent_ids = set(self.env["it.helpdesk.ticket"].with_user(self.agent).search(domain).ids)

        self.assertIn(draft_ticket.id, manager_ids)
        self.assertIn(new_ticket.id, manager_ids)
        self.assertNotIn(other_ticket.id, manager_ids)

        self.assertNotIn(draft_ticket.id, agent_ids)
        self.assertIn(new_ticket.id, agent_ids)
        self.assertNotIn(other_ticket.id, agent_ids)

    def test_backend_and_email_creation_use_company_defaults(self):
        model = self.env["it.helpdesk.ticket"].with_user(self.agent)
        ticket = model.create({"subject": "Backend defaults"})
        self.assertEqual(ticket.source, "manual")
        self.assertTrue(ticket.category_id)
        self.assertTrue(ticket.priority_id)
        self.assertTrue(ticket.team_id)
        self.assertEqual(ticket.category_id.company_id, self.company)
        self.assertEqual(ticket.priority_id.company_id, self.company)
        self.assertEqual(ticket.team_id.company_id, self.company)

        email_ticket_id = model.message_new(
            {"subject": "Email defaults", "body": "<p>Email body</p>"}
        )
        email_ticket = model.browse(email_ticket_id)
        self.assertEqual(email_ticket.source, "email")
        self.assertEqual(email_ticket.subject, "Email defaults")
        self.assertEqual(email_ticket.description, "<p>Email body</p>")
        self.assertEqual(email_ticket.category_id, ticket.category_id)
        self.assertEqual(email_ticket.priority_id, ticket.priority_id)

    def test_portal_selection_rejects_invalid_and_cross_company_values(self):
        model = self.env["it.helpdesk.ticket"]
        self.assertEqual(
            model._validate_portal_selection(self.category.id, self.priority.id),
            (self.category.id, self.priority.id),
        )
        with self.assertRaises(ValidationError):
            model._validate_portal_selection("not-an-id", self.priority.id)
        with self.assertRaises(ValidationError):
            model._validate_portal_selection(self.other_category.id, self.other_priority.id)

    def test_defaults_are_provisioned_for_each_company(self):
        model = self.env["it.helpdesk.ticket"]
        model.sudo()._ensure_company_defaults(self.other_company)
        for model_name in (
            "it.helpdesk.stage",
            "it.helpdesk.category",
            "it.helpdesk.priority",
            "it.helpdesk.team",
            "it.helpdesk.sla",
        ):
            records = self.env[model_name].sudo().search([("company_id", "=", self.other_company.id)])
            self.assertTrue(records, model_name)

        ticket = model.sudo().create(
            {"subject": "Other company defaults", "company_id": self.other_company.id}
        )
        self.assertEqual(ticket.company_id, self.other_company)
        self.assertTrue(ticket.stage_id and ticket.category_id and ticket.priority_id and ticket.team_id)

    def test_ticket_rejects_references_from_another_company(self):
        base_vals = {
            "subject": "Cross company reference",
            "company_id": self.company.id,
            "category_id": self.category.id,
            "priority_id": self.priority.id,
            "team_id": self.team.id,
        }
        for field, value in (
            ("category_id", self.other_category.id),
            ("priority_id", self.other_priority.id),
        ):
            with self.assertRaises(UserError):
                self.env["it.helpdesk.ticket"].sudo().create({**base_vals, field: value})

        other_team = self.env["it.helpdesk.team"].sudo().create(
            {"name": "Other Company Team", "company_id": self.other_company.id}
        )
        with self.assertRaises(UserError):
            self.env["it.helpdesk.ticket"].sudo().create({**base_vals, "team_id": other_team.id})

        other_sla = self.env["it.helpdesk.sla"].sudo().create(
            {
                "name": "Other Company SLA",
                "company_id": self.other_company.id,
                "category_id": self.other_category.id,
                "priority_id": self.other_priority.id,
            }
        )
        with self.assertRaises(UserError):
            self.env["it.helpdesk.ticket"].sudo().create({**base_vals, "sla_id": other_sla.id})

    def test_manager_only_group_can_run_agent_workflow(self):
        self.assertTrue(self.manager.has_group("buz_it_helpdesk.group_it_helpdesk_agent"))
        manager_team = self.env["it.helpdesk.team"].sudo().create(
            {
                "name": "Manager Workflow Team",
                "company_id": self.company.id,
                "member_ids": [fields.Command.link(self.manager.id)],
            }
        )
        ticket = self.env["it.helpdesk.ticket"].sudo().create(
            {
                "subject": "Manager workflow",
                "company_id": self.company.id,
                "stage_id": self.stage_new.id,
                "category_id": self.category.id,
                "priority_id": self.priority.id,
                "team_id": manager_team.id,
            }
        )
        ticket.with_user(self.manager).action_assign()
        self.assertEqual(ticket.assigned_to, self.manager)