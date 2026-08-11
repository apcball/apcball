from odoo import Command
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestTicketKanbanStage(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.group_user = cls.env.ref('base.group_user')
        cls.group_requester = cls.env.ref('buz_it_helpdesk.group_it_requester')
        cls.group_support = cls.env.ref('buz_it_helpdesk.group_it_support_agent')
        cls.group_manager = cls.env.ref('buz_it_helpdesk.group_it_helpdesk_manager')
        cls.stage_new = cls.env.ref('buz_it_helpdesk.stage_new')
        cls.stage_in_progress = cls.env.ref('buz_it_helpdesk.stage_in_progress')
        cls.stage_pending_user = cls.env.ref('buz_it_helpdesk.stage_pending_user')
        cls.stage_resolved = cls.env.ref('buz_it_helpdesk.stage_resolved')
        cls.stage_closed = cls.env.ref('buz_it_helpdesk.stage_closed')

        cls.requester = cls.env['res.users'].create({
            'name': 'Kanban Requester',
            'login': 'kanban-requester',
            'email': 'kanban-requester@example.com',
            'groups_id': [Command.set([
                cls.group_user.id,
                cls.group_requester.id,
            ])],
        })
        cls.support = cls.env['res.users'].create({
            'name': 'Kanban Support',
            'login': 'kanban-support',
            'email': 'kanban-support@example.com',
            'groups_id': [Command.set([
                cls.group_user.id,
                cls.group_support.id,
            ])],
        })
        cls.manager = cls.env['res.users'].create({
            'name': 'Kanban Manager',
            'login': 'kanban-manager',
            'email': 'kanban-manager@example.com',
            'groups_id': [Command.set([
                cls.group_user.id,
                cls.group_manager.id,
            ])],
        })

    def _ticket(self, **values):
        requested_stage = values.pop('stage_id', self.stage_new.id)
        requested_team = values.get('team_id')
        requested_assignee = values.get('assigned_user_id')
        defaults = {
            'subject': 'Kanban stage test',
            'requester_id': self.requester.id,
        }
        defaults.update(values)
        ticket = self.env['buz.helpdesk.ticket'].with_user(self.manager).create(defaults)
        restore_values = {
            field: value for field, value in {
                'team_id': requested_team,
                'assigned_user_id': requested_assignee,
            }.items() if value
        }
        if restore_values:
            ticket.with_context(buz_helpdesk_transition=True).write(restore_values)
        if requested_stage != self.env.ref('buz_it_helpdesk.stage_draft').id:
            ticket.with_context(buz_helpdesk_transition=True).write({
                'stage_id': requested_stage,
            })
        return ticket

    def test_support_drag_to_in_progress_assigns_dragger(self):
        team = self.env['buz.helpdesk.team'].with_user(self.manager).create({
            'name': 'Receiving Team',
            'user_ids': [Command.link(self.support.id)],
        })
        ticket = self._ticket(team_id=team.id)

        ticket.with_user(self.support).write({
            'stage_id': self.stage_in_progress.id,
        })

        self.assertEqual(ticket.stage_id, self.stage_in_progress)
        self.assertEqual(ticket.assigned_user_id, self.support)
        self.assertEqual(ticket.team_id, team)

    def test_manager_assignment_starts_new_ticket(self):
        team = self.env['buz.helpdesk.team'].with_user(self.manager).create({
            'name': 'Manager Assignment Team',
            'user_ids': [Command.link(self.support.id)],
        })
        ticket = self._ticket()

        ticket.with_user(self.manager).write({
            'team_id': team.id,
            'assigned_user_id': self.support.id,
        })

        self.assertEqual(ticket.stage_id, self.stage_in_progress)
        self.assertEqual(ticket.team_id, team)
        self.assertEqual(ticket.assigned_user_id, self.support)

    def test_in_progress_can_be_returned_to_new_and_received_again(self):
        team = self.env['buz.helpdesk.team'].with_user(self.manager).create({
            'name': 'Rollback Team',
            'user_ids': [Command.link(self.support.id)],
        })
        ticket = self._ticket(
            stage_id=self.stage_in_progress.id,
            team_id=team.id,
            assigned_user_id=self.support.id,
        )

        ticket.with_user(self.support).write({
            'stage_id': self.stage_new.id,
        })

        self.assertEqual(ticket.stage_id, self.stage_new)
        self.assertFalse(ticket.team_id)
        self.assertFalse(ticket.assigned_user_id)

        ticket.with_user(self.support).write({
            'stage_id': self.stage_in_progress.id,
        })
        self.assertEqual(ticket.stage_id, self.stage_in_progress)
        self.assertEqual(ticket.team_id, team)
        self.assertEqual(ticket.assigned_user_id, self.support)

    def test_only_in_progress_can_be_returned_to_new(self):
        for stage in (self.stage_pending_user, self.stage_resolved, self.stage_closed):
            ticket = self._ticket(
                stage_id=stage.id,
                assigned_user_id=self.support.id,
            )
            with self.assertRaises(UserError):
                ticket.with_user(self.support).write({
                    'stage_id': self.stage_new.id,
                })

    def test_cannot_return_to_new_after_pending_user(self):
        ticket = self._ticket(
            stage_id=self.stage_pending_user.id,
            assigned_user_id=self.support.id,
        )

        with self.assertRaises(UserError):
            ticket.with_user(self.support).write({'stage_id': self.stage_new.id})

    def test_assigned_support_can_drag_to_closed(self):
        ticket = self._ticket(
            stage_id=self.stage_in_progress.id,
            assigned_user_id=self.support.id,
        )
        ticket.with_user(self.support).write({
            'stage_id': self.stage_resolved.id,
        })
        ticket.with_user(self.support).write({'stage_id': self.stage_closed.id})

        self.assertEqual(ticket.stage_id, self.stage_closed)
        self.assertTrue(ticket.closed_ticket_date)

    def test_unassigned_support_cannot_drag_to_closed(self):
        ticket = self._ticket(stage_id=self.stage_in_progress.id)

        with self.assertRaises(UserError):
            ticket.with_user(self.support).write({
                'stage_id': self.stage_closed.id,
            })

    def test_workflow_pending_user_keeps_assignment_and_resumes(self):
        ticket = self._ticket(
            stage_id=self.stage_in_progress.id,
            assigned_user_id=self.support.id,
        )

        ticket.with_user(self.support).write({
            'stage_id': self.stage_pending_user.id,
        })
        self.assertEqual(ticket.stage_id, self.stage_pending_user)
        self.assertEqual(ticket.assigned_user_id, self.support)

        ticket.with_user(self.support).write({
            'stage_id': self.stage_in_progress.id,
        })
        self.assertEqual(ticket.stage_id, self.stage_in_progress)
        self.assertEqual(ticket.assigned_user_id, self.support)

    def test_assigned_support_can_mark_resolved_but_not_skip_to_closed(self):
        ticket = self._ticket(
            stage_id=self.stage_in_progress.id,
            assigned_user_id=self.support.id,
        )

        with self.assertRaises(UserError):
            ticket.with_user(self.support).write({
                'stage_id': self.stage_closed.id,
            })

        ticket.with_user(self.support).write({
            'stage_id': self.stage_resolved.id,
        })
        self.assertEqual(ticket.stage_id, self.stage_resolved)

    def test_workflow_rejects_skipping_to_resolved(self):
        ticket = self._ticket(stage_id=self.stage_new.id)

        with self.assertRaises(UserError):
            ticket.with_user(self.support).write({
                'stage_id': self.stage_resolved.id,
            })

    def test_requester_cannot_drag_stage(self):
        ticket = self._ticket()

        with self.assertRaises(UserError):
            ticket.with_user(self.requester).write({
                'stage_id': self.stage_in_progress.id,
            })

    def test_kanban_stage_visibility_defaults_to_true(self):
        self.assertTrue(self.stage_new.show_in_kanban)

        custom_stage = self.env['buz.helpdesk.stage'].with_user(self.manager).create({
            'name': 'Kanban Visibility Test',
            'sequence': 100,
        })
        self.assertTrue(custom_stage.show_in_kanban)

    def test_kanban_group_expansion_excludes_hidden_and_archived_stages(self):
        hidden_stage = self.stage_pending_user.with_user(self.manager)
        hidden_stage.write({'show_in_kanban': False})

        archived_stage = self.env['buz.helpdesk.stage'].with_user(self.manager).create({
            'name': 'Archived Kanban Stage',
            'sequence': 110,
        })
        archived_stage.write({'active': False})

        expanded_stages = self.env['buz.helpdesk.ticket']._read_group_stage_ids(
            self.env['buz.helpdesk.stage'], [], 'sequence, name'
        )

        self.assertIn(self.stage_new, expanded_stages)
        self.assertNotIn(hidden_stage, expanded_stages)
        self.assertNotIn(archived_stage, expanded_stages)

    def test_hidden_stage_keeps_existing_ticket(self):
        ticket = self._ticket(stage_id=self.stage_pending_user.id)
        self.stage_pending_user.with_user(self.manager).write({
            'show_in_kanban': False,
        })

        ticket.invalidate_recordset()
        self.assertEqual(ticket.stage_id, self.stage_pending_user)

    def _activity_domain(self, ticket):
        return [
            ('res_model', '=', ticket._name),
            ('res_id', '=', ticket.id),
            ('activity_type_id', '=', self.env.ref(
                'mail.mail_activity_data_todo'
            ).id),
            ('date_done', '=', False),
        ]

    def test_new_ticket_activity_targets_active_support_in_ticket_company(self):
        other_company = self.env['res.company'].create({
            'name': 'Notification Other Company',
        })
        cross_company_support = self.env['res.users'].create({
            'name': 'Cross Company Support',
            'login': 'cross-company-support',
            'company_id': other_company.id,
            'company_ids': [Command.set([other_company.id])],
            'groups_id': [Command.set([
                self.group_user.id,
                self.group_support.id,
            ])],
        })
        inactive_support = self.env['res.users'].create({
            'name': 'Inactive Support',
            'login': 'inactive-support',
            'groups_id': [Command.set([
                self.group_user.id,
                self.group_support.id,
            ])],
            'active': False,
        })
        ticket = self._ticket(
            stage_id=self.env.ref('buz_it_helpdesk.stage_draft').id,
        )

        ticket.with_user(self.requester).action_create_ticket()

        activities = self.env['mail.activity'].search(
            self._activity_domain(ticket)
        )
        self.assertSetEqual(
            set(activities.mapped('user_id').ids),
            {self.support.id, self.manager.id},
        )
        self.assertNotIn(cross_company_support, activities.mapped('user_id'))
        self.assertNotIn(inactive_support, activities.mapped('user_id'))
        self.assertNotIn(self.requester, activities.mapped('user_id'))

    def test_new_ticket_activity_does_not_duplicate_existing_intake_activity(self):
        ticket = self._ticket(
            stage_id=self.env.ref('buz_it_helpdesk.stage_draft').id,
        )
        ticket.activity_schedule(
            'mail.mail_activity_data_todo',
            user_id=self.support.id,
            summary='New IT Helpdesk Ticket',
            note='Existing intake activity',
        )

        ticket.with_user(self.requester).action_create_ticket()

        support_activities = self.env['mail.activity'].search(
            self._activity_domain(ticket) + [
                ('user_id', '=', self.support.id),
                ('summary', '=', 'New IT Helpdesk Ticket'),
            ]
        )
        self.assertEqual(len(support_activities), 1)

    def test_receive_completes_only_system_intake_activities(self):
        team = self.env['buz.helpdesk.team'].create({
            'name': 'Notification Receive Team',
            'user_ids': [Command.set([self.support.id])],
        })
        ticket = self._ticket(stage_id=self.stage_new.id)
        ticket.activity_schedule(
            'mail.mail_activity_data_todo',
            user_id=self.support.id,
            summary='New IT Helpdesk Ticket',
        )
        unrelated = ticket.activity_schedule(
            'mail.mail_activity_data_todo',
            user_id=self.support.id,
            summary='Unrelated follow-up',
        )

        ticket.with_user(self.support).action_receive_ticket()

        self.assertEqual(ticket.team_id, team)
        self.assertTrue(self.env['mail.activity'].browse(unrelated.id).exists())
        self.assertFalse(
            self.env['mail.activity'].search(
                self._activity_domain(ticket) + [
                    ('summary', '=', 'New IT Helpdesk Ticket'),
                ]
            )
        )
