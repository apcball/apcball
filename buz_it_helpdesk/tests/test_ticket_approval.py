from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestTicketApproval(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.group_user = cls.env.ref('base.group_user')
        cls.group_requester = cls.env.ref('buz_it_helpdesk.group_it_requester')
        cls.group_support = cls.env.ref('buz_it_helpdesk.group_it_support_agent')
        cls.group_manager = cls.env.ref('buz_it_helpdesk.group_it_helpdesk_manager')
        cls.stage_in_progress = cls.env.ref('buz_it_helpdesk.stage_in_progress')

        cls.requester = cls._user('approval-requester', cls.group_requester)
        cls.support = cls._user('approval-support', cls.group_support)
        cls.manager = cls._user('approval-manager', cls.group_manager)
        cls.other_manager = cls._user('approval-other-manager', cls.group_manager)

    @classmethod
    def _user(cls, login, group):
        return cls.env['res.users'].create({
            'name': login,
            'login': login,
            'email': '%s@example.com' % login,
            'groups_id': [Command.set([
                cls.group_user.id,
                group.id,
            ])],
        })

    def _ticket(self):
        team = self.env['buz.helpdesk.team'].with_user(self.manager).create({
            'name': 'Approval Team %s' % self.env.cr.dbname,
            'user_ids': [Command.link(self.support.id)],
        })
        ticket = self.env['buz.helpdesk.ticket'].with_user(self.manager).create({
            'subject': 'Approval test',
            'requester_id': self.requester.id,
        })
        ticket.with_user(self.manager).write({
            'team_id': team.id,
            'assigned_user_id': self.support.id,
        })
        ticket.with_context(buz_helpdesk_transition=True).write({
            'stage_id': self.stage_in_progress.id,
        })
        self.assertEqual(ticket.stage_id, self.stage_in_progress)
        return ticket

    def test_send_to_approve_requires_manager(self):
        ticket = self._ticket()
        with self.assertRaises(UserError):
            ticket.with_user(self.support).action_send_to_approve()

    def test_send_to_approve_creates_pending_activity_without_stage_change(self):
        ticket = self._ticket()
        ticket.with_user(self.support).write({
            'approval_manager_id': self.manager.id,
            'approval_request_note': 'Please approve the sensitive change.',
        })

        ticket.with_user(self.support).action_send_to_approve()

        self.assertEqual(ticket.approval_state, 'pending')
        self.assertEqual(ticket.approval_requested_by, self.support)
        self.assertTrue(ticket.approval_requested_at)
        self.assertEqual(ticket.stage_id, self.stage_in_progress)
        activity = self.env['mail.activity'].search([
            ('res_model', '=', ticket._name),
            ('res_id', '=', ticket.id),
            ('user_id', '=', self.manager.id),
            ('summary', '=', 'Helpdesk Approval Request'),
            ('date_done', '=', False),
        ])
        self.assertEqual(len(activity), 1)

        with self.assertRaises(UserError):
            ticket.with_user(self.support).write({
                'approval_manager_id': self.other_manager.id,
            })

    def test_only_selected_manager_can_approve(self):
        ticket = self._ticket()
        ticket.with_user(self.support).write({
            'approval_manager_id': self.manager.id,
        })
        ticket.with_user(self.support).action_send_to_approve()

        with self.assertRaises(UserError):
            ticket.with_user(self.other_manager).action_approve()

        ticket.with_user(self.manager).action_approve()
        self.assertEqual(ticket.approval_state, 'approved')
        self.assertEqual(ticket.approval_decided_by, self.manager)
        self.assertTrue(ticket.approval_decided_at)
        self.assertFalse(ticket._approval_activities())

    def test_reject_requires_reason_and_allows_resubmit(self):
        ticket = self._ticket()
        ticket.with_user(self.support).write({
            'approval_manager_id': self.manager.id,
        })
        ticket.with_user(self.support).action_send_to_approve()

        with self.assertRaises(UserError):
            ticket.with_user(self.manager)._reject_approval('')

        ticket.with_user(self.manager)._reject_approval('Please add a rollback plan.')
        self.assertEqual(ticket.approval_state, 'rejected')
        self.assertEqual(ticket.approval_rejection_reason, 'Please add a rollback plan.')

        ticket.with_user(self.support).write({
            'approval_request_note': 'Updated request with rollback plan.',
        })
        ticket.with_user(self.support).action_send_to_approve()
        self.assertEqual(ticket.approval_state, 'pending')

    def test_direct_approval_state_write_is_blocked(self):
        ticket = self._ticket()
        with self.assertRaises(UserError):
            ticket.with_user(self.support).write({'approval_state': 'approved'})

    def test_requester_cannot_read_approval_fields(self):
        ticket = self._ticket()
        with self.assertRaises(AccessError):
            ticket.with_user(self.requester).read(['approval_state'])

    def test_manager_must_be_helpdesk_manager(self):
        ticket = self._ticket()
        with self.assertRaises(ValidationError):
            ticket.with_user(self.support).write({
                'approval_manager_id': self.requester.id,
            })
