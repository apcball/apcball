from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger


class TestResolutionWorkflow(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.requester_group = cls.env.ref('buz_it_helpdesk.group_it_requester')
        cls.support_group = cls.env.ref('buz_it_helpdesk.group_it_support_agent')
        cls.manager_group = cls.env.ref('buz_it_helpdesk.group_it_helpdesk_manager')
        cls.base_user_group = cls.env.ref('base.group_user')
        cls.requester = cls.env['res.users'].create({
            'name': 'Resolution Requester',
            'login': 'resolution_requester',
            'email': 'resolution_requester@example.com',
            'groups_id': [fields.Command.set([
                cls.base_user_group.id,
                cls.requester_group.id,
            ])],
        })
        cls.support = cls.env['res.users'].create({
            'name': 'Resolution Support',
            'login': 'resolution_support',
            'email': 'resolution_support@example.com',
            'groups_id': [fields.Command.set([
                cls.base_user_group.id,
                cls.support_group.id,
            ])],
        })
        cls.manager = cls.env['res.users'].create({
            'name': 'Resolution Manager',
            'login': 'resolution_manager',
            'email': 'resolution_manager@example.com',
            'groups_id': [fields.Command.set([
                cls.base_user_group.id,
                cls.manager_group.id,
            ])],
        })
        cls.category = cls.env['buz.helpdesk.category'].create({
            'name': 'Resolution Workflow Test',
        })
        cls.team = cls.env['buz.helpdesk.team'].create({
            'name': 'Resolution Workflow Team',
            'user_ids': [fields.Command.set([cls.support.id, cls.manager.id])],
        })

    def _resolved_ticket(self):
        ticket = self.env['buz.helpdesk.ticket'].with_user(
            self.requester
        ).create({
            'subject': 'Resolution workflow test',
            'category_id': self.category.id,
        })
        ticket.with_user(self.requester).action_create_ticket()
        ticket.with_user(self.support).action_receive_ticket()
        ticket.with_user(self.support)._write_workflow_fields({
            'stage_id': self.env.ref(
                'buz_it_helpdesk.stage_resolved'
            ).id,
        })
        ticket.with_user(self.support).activity_schedule(
            'buz_it_helpdesk.mail_activity_type_resolution_confirmation',
            user_id=self.requester.id,
            summary='Confirm IT Resolution',
            note='Please review the resolution.',
        )
        return ticket

    def test_requester_can_request_rework_and_it_can_resolve_again(self):
        ticket = self._resolved_ticket()

        self.assertTrue(ticket.with_user(
            self.requester
        ).show_confirm_resolution_button)
        self.assertTrue(ticket.with_user(
            self.requester
        ).show_request_rework_button)
        self.assertFalse(ticket.with_user(
            self.support
        ).show_close_button)
        with self.assertRaises(UserError):
            ticket.with_user(self.support).action_close_ticket()

        ticket.with_user(self.requester).action_request_rework()

        self.assertEqual(
            ticket.stage_id,
            self.env.ref('buz_it_helpdesk.stage_in_progress'),
        )
        self.assertEqual(ticket.assigned_user_id, self.support)
        self.assertFalse(ticket.with_user(
            self.requester
        ).show_request_rework_button)
        self.assertTrue(ticket.with_user(
            self.support
        ).show_resolve_button)
        self.assertTrue(ticket.with_user(self.support).activity_ids.filtered(
            lambda activity: activity.user_id == self.support
            and activity.summary == 'Requester requested more work'
        ))

    def test_requester_confirmation_allows_assigned_it_to_close(self):
        ticket = self._resolved_ticket()

        ticket.with_user(self.requester).action_confirm_resolution()

        self.assertTrue(ticket.with_user(self.support).show_close_button)
        ticket.with_user(self.support).action_close_ticket()
        self.assertEqual(
            ticket.stage_id,
            self.env.ref('buz_it_helpdesk.stage_closed'),
        )

    def test_manager_can_override_resolution_confirmation(self):
        ticket = self._resolved_ticket()

        self.assertTrue(ticket.with_user(self.manager).show_close_button)
        ticket.with_user(self.manager).action_close_ticket()
        self.assertEqual(
            ticket.stage_id,
            self.env.ref('buz_it_helpdesk.stage_closed'),
        )
    def test_non_requester_cannot_request_rework(self):
        ticket = self._resolved_ticket()

        with self.assertRaises(UserError):
            with mute_logger('odoo.http'):
                ticket.with_user(self.support).action_request_rework()