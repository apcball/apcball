from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestTicketCategoryPermissions(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        base_user = cls.env.ref('base.group_user')
        requester_group = cls.env.ref('buz_it_helpdesk.group_it_requester')
        support_group = cls.env.ref('buz_it_helpdesk.group_it_support_agent')
        manager_group = cls.env.ref('buz_it_helpdesk.group_it_helpdesk_manager')
        cls.requester = cls._create_user(
            'category_requester', 'Category Requester',
            [base_user, requester_group],
        )
        cls.other_requester = cls._create_user(
            'category_other_requester', 'Other Category Requester',
            [base_user, requester_group],
        )
        cls.support = cls._create_user(
            'category_support', 'Category Support',
            [base_user, support_group],
        )
        cls.manager = cls._create_user(
            'category_manager', 'Category Manager',
            [base_user, manager_group],
        )
        cls.category = cls.env['buz.helpdesk.category'].create({
            'name': 'Category Permission Original',
        })
        cls.other_category = cls.env['buz.helpdesk.category'].create({
            'name': 'Category Permission Updated',
        })
        cls.team = cls.env['buz.helpdesk.team'].create({
            'name': 'Category Permission Team',
            'user_ids': [fields.Command.set([cls.support.id, cls.manager.id])],
        })

    @classmethod
    def _create_user(cls, login, name, groups):
        return cls.env['res.users'].create({
            'name': name,
            'login': login,
            'email': '%s@example.com' % login,
            'groups_id': [fields.Command.set([group.id for group in groups])],
        })

    def _draft_ticket(self, requester=None):
        requester = requester or self.requester
        return self.env['buz.helpdesk.ticket'].with_user(requester).create({
            'subject': 'Category permission test',
            'category_id': self.category.id,
        })

    def _new_ticket(self, requester=None):
        ticket = self._draft_ticket(requester)
        ticket.with_user(requester or self.requester).action_create_ticket()
        return ticket

    def test_support_and_manager_can_edit_category_on_new_ticket(self):
        for user in (self.support, self.manager):
            ticket = self._new_ticket()

            self.assertFalse(ticket.assigned_user_id)
            self.assertTrue(ticket.with_user(user).can_edit_category)
            ticket.with_user(user).write({
                'category_id': self.other_category.id,
            })
            self.assertEqual(ticket.category_id, self.other_category)

    def test_support_can_edit_category_in_draft_without_editing_other_fields(self):
        ticket = self._draft_ticket()

        self.assertTrue(ticket.with_user(self.support).can_edit_category)
        ticket.with_user(self.support).write({
            'category_id': self.other_category.id,
        })
        self.assertEqual(ticket.category_id, self.other_category)

        new_ticket = self._new_ticket()
        with self.assertRaisesRegex(UserError, 'Only the assigned agent'):
            new_ticket.with_user(self.support).write({
                'category_id': self.other_category.id,
                'subject': 'Should not be changed',
            })
        self.assertEqual(new_ticket.category_id, self.category)

    def test_requester_can_edit_own_draft_but_not_another_requesters(self):
        own_ticket = self._draft_ticket()
        own_ticket.with_user(self.requester).write({
            'category_id': self.other_category.id,
        })
        self.assertEqual(own_ticket.category_id, self.other_category)

        other_ticket = self._draft_ticket(self.other_requester)
        self.assertFalse(other_ticket.with_user(self.requester).can_edit_category)
        with self.assertRaisesRegex(UserError, 'only edit their own Draft'):
            other_ticket.with_user(self.requester).write({
                'category_id': self.other_category.id,
            })

    def test_category_is_locked_after_ticket_is_received(self):
        for stage_xmlid in (
            'buz_it_helpdesk.stage_in_progress',
            'buz_it_helpdesk.stage_pending_user',
            'buz_it_helpdesk.stage_resolved',
            'buz_it_helpdesk.stage_closed',
        ):
            ticket = self._new_ticket()
            ticket._write_workflow_fields({
                'stage_id': self.env.ref(stage_xmlid).id,
            })
            for user in (self.support, self.manager):
                self.assertFalse(ticket.with_user(user).can_edit_category)
                with self.assertRaisesRegex(
                    UserError, 'Category cannot be changed after the ticket is received',
                ):
                    ticket.with_user(user).write({
                        'category_id': self.other_category.id,
                    })

    def test_manager_cannot_complete_missing_category_after_receive(self):
        ticket = self._new_ticket()
        ticket._write_workflow_fields({
            'stage_id': self.env.ref(
                'buz_it_helpdesk.stage_in_progress'
            ).id,
        })
        self.env.cr.execute(
            'UPDATE buz_helpdesk_ticket SET category_id = NULL WHERE id = %s',
            (ticket.id,),
        )
        ticket.invalidate_recordset(['category_id'])

        with self.assertRaisesRegex(
            UserError, 'Category cannot be changed after the ticket is received',
        ):
            ticket.with_user(self.manager).write({
                'category_id': self.category.id,
            })

    def test_priority_rules_remain_unchanged(self):
        ticket = self._new_ticket()

        with self.assertRaisesRegex(UserError, 'Priority cannot be changed'):
            ticket.with_user(self.manager).write({'priority': '2'})

        ticket.with_user(self.support).write({
            'category_id': self.other_category.id,
        })
        self.assertEqual(ticket.priority, '1')

    def test_category_change_clears_type_from_previous_category(self):
        category_with_type = self.env['buz.helpdesk.category'].create({
            'name': 'Category With Type',
        })
        category_type = self.env['buz.helpdesk.category.type'].create({
            'name': 'Category Type',
            'category_id': category_with_type.id,
        })
        ticket = self.env['buz.helpdesk.ticket'].new({
            'category_id': category_with_type.id,
            'category_type_id': category_type.id,
        })

        ticket.category_id = self.other_category
        ticket._onchange_category_id()

        self.assertFalse(ticket.category_type_id)

    def test_rpc_category_change_clears_incompatible_type(self):
        category_with_type = self.env['buz.helpdesk.category'].create({
            'name': 'Category With RPC Type',
        })
        category_type = self.env['buz.helpdesk.category.type'].create({
            'name': 'RPC Category Type',
            'category_id': category_with_type.id,
        })
        ticket = self.env['buz.helpdesk.ticket'].with_user(
            self.requester
        ).create({
            'subject': 'Category type RPC test',
            'category_id': category_with_type.id,
            'category_type_id': category_type.id,
        })
        ticket.with_user(self.requester).action_create_ticket()

        ticket.with_user(self.support).write({
            'category_id': self.other_category.id,
        })

        self.assertFalse(ticket.category_type_id)
