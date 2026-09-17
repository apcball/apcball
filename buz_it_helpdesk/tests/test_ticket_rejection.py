from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestTicketRejection(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.requester_group = cls.env.ref('buz_it_helpdesk.group_it_requester')
        cls.support_group = cls.env.ref('buz_it_helpdesk.group_it_support_agent')
        cls.manager_group = cls.env.ref('buz_it_helpdesk.group_it_helpdesk_manager')
        cls.base_user_group = cls.env.ref('base.group_user')
        cls.requester = cls.env['res.users'].create({
            'name': 'Reject Workflow Requester',
            'login': 'reject_workflow_requester',
            'email': 'reject_workflow_requester@example.com',
            'groups_id': [fields.Command.set([
                cls.base_user_group.id,
                cls.requester_group.id,
            ])],
        })
        cls.support = cls.env['res.users'].create({
            'name': 'Reject Workflow Support',
            'login': 'reject_workflow_support',
            'email': 'reject_workflow_support@example.com',
            'groups_id': [fields.Command.set([
                cls.base_user_group.id,
                cls.support_group.id,
            ])],
        })
        cls.manager = cls.env['res.users'].create({
            'name': 'Reject Workflow Manager',
            'login': 'reject_workflow_manager',
            'email': 'reject_workflow_manager@example.com',
            'groups_id': [fields.Command.set([
                cls.base_user_group.id,
                cls.manager_group.id,
            ])],
        })
        cls.category = cls.env['buz.helpdesk.category'].create({
            'name': 'Reject Workflow Test',
        })
        cls.team = cls.env['buz.helpdesk.team'].create({
            'name': 'Reject Workflow Team',
            'user_ids': [fields.Command.set([
                cls.support.id,
                cls.manager.id,
            ])],
        })

    def _new_ticket(self):
        ticket = self.env['buz.helpdesk.ticket'].with_user(
            self.requester
        ).create({
            'subject': 'Reject workflow test',
            'category_id': self.category.id,
        })
        ticket.with_user(self.requester).action_create_ticket()
        return ticket

    def test_agent_rejects_new_ticket_and_notifies_requester(self):
        ticket = self._new_ticket()

        self.assertTrue(ticket.with_user(
            self.support
        ).show_reject_ticket_button)
        wizard = self.env['buz.helpdesk.ticket.reject.wizard'].with_user(
            self.support
        ).create({
            'ticket_id': ticket.id,
            'reason_type': 'duplicate',
            'reason': 'This request is already tracked in another ticket.',
        })
        wizard.action_confirm()

        self.assertEqual(
            ticket.stage_id,
            self.env.ref('buz_it_helpdesk.stage_rejected'),
        )
        self.assertEqual(ticket.ticket_rejection_reason_type, 'duplicate')
        self.assertEqual(
            ticket.ticket_rejection_reason,
            'This request is already tracked in another ticket.',
        )
        self.assertTrue(ticket.message_ids.filtered(
            lambda message: self.requester.partner_id in message.partner_ids
            and 'This ticket was rejected before work started.'
            in (message.body or '')
        ))
        self.assertFalse(ticket.with_user(
            self.support
        ).show_reject_ticket_button)

    def test_manager_can_reject_and_reopen_with_history(self):
        ticket = self._new_ticket()
        ticket.with_user(self.manager)._reject_ticket(
            'invalid', 'The request does not describe an IT issue.',
        )

        self.assertTrue(ticket.with_user(
            self.manager
        ).show_reopen_rejected_ticket_button)
        ticket.with_user(self.manager).action_reopen_rejected_ticket()

        self.assertEqual(
            ticket.stage_id,
            self.env.ref('buz_it_helpdesk.stage_new'),
        )
        self.assertFalse(ticket.ticket_rejection_reason_type)
        self.assertFalse(ticket.ticket_rejection_reason)
        self.assertTrue(ticket.message_ids.filtered(
            lambda message: 'This ticket was rejected before work started.'
            in (message.body or '')
            and 'The request does not describe an IT issue.'
            in (message.body or '')
        ))
        self.assertTrue(ticket.message_ids.filtered(
            lambda message: 'This rejected ticket was reopened by'
            in (message.body or '')
        ))

    def test_requester_cannot_reject_or_reopen_ticket(self):
        ticket = self._new_ticket()

        with self.assertRaisesRegex(UserError, 'Only IT Support Agents'):
            ticket.with_user(self.requester)._reject_ticket(
                'other', 'Not a valid rejection.',
            )
        ticket.with_user(self.support)._reject_ticket(
            'other', 'Not a valid rejection.',
        )
        with self.assertRaisesRegex(UserError, 'Only Helpdesk Managers'):
            ticket.with_user(self.support).action_reopen_rejected_ticket()

    def test_reject_requires_valid_type_and_nonempty_details(self):
        ticket = self._new_ticket()

        with self.assertRaisesRegex(ValidationError, 'valid rejection type'):
            ticket.with_user(self.support)._reject_ticket(
                'not_a_type', 'Reason',
            )
        with self.assertRaisesRegex(ValidationError, 'details are required'):
            ticket.with_user(self.support)._reject_ticket('other', '  ')

    def test_assigned_new_ticket_cannot_be_rejected(self):
        ticket = self._new_ticket()
        ticket.with_user(self.manager)._write_workflow_fields({
            'assigned_user_id': self.support.id,
        })

        with self.assertRaisesRegex(UserError, 'not been received'):
            ticket.with_user(self.support)._reject_ticket(
                'other', 'Already assigned.',
            )

    def test_reject_and_receive_are_mutually_exclusive(self):
        rejected_ticket = self._new_ticket()
        rejected_ticket.with_user(self.support)._reject_ticket(
            'duplicate', 'Duplicate request.',
        )
        with self.assertRaisesRegex(UserError, 'already been received'):
            rejected_ticket.with_user(self.support).action_receive_ticket()

        received_ticket = self._new_ticket()
        received_ticket.with_user(self.support).action_receive_ticket()
        with self.assertRaisesRegex(UserError, 'not been received'):
            received_ticket.with_user(self.support)._reject_ticket(
                'invalid', 'Invalid request.',
            )

    def test_rejection_fields_cannot_be_written_directly(self):
        ticket = self._new_ticket()

        with self.assertRaisesRegex(UserError, 'only be changed through'):
            ticket.with_user(self.manager).write({
                'ticket_rejection_reason_type': 'other',
            })
