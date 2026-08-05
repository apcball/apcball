from odoo import Command
from odoo.exceptions import UserError
from odoo.tests.common import SavepointCase


class TestTicketKanbanStage(SavepointCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.group_user = cls.env.ref('base.group_user')
        cls.group_requester = cls.env.ref('buz_it_helpdesk.group_it_requester')
        cls.group_support = cls.env.ref('buz_it_helpdesk.group_it_support_agent')
        cls.group_manager = cls.env.ref('buz_it_helpdesk.group_it_helpdesk_manager')
        cls.stage_new = cls.env.ref('buz_it_helpdesk.stage_new')
        cls.stage_in_progress = cls.env.ref('buz_it_helpdesk.stage_in_progress')
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
        defaults = {
            'subject': 'Kanban stage test',
            'requester_id': self.requester.id,
            'stage_id': self.stage_new.id,
        }
        defaults.update(values)
        return self.env['buz.helpdesk.ticket'].with_user(self.manager).create(defaults)

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

    def test_drag_back_to_new_clears_assignment_and_team(self):
        team = self.env['buz.helpdesk.team'].with_user(self.manager).create({
            'name': 'Kanban Team',
            'user_ids': [Command.link(self.support.id)],
        })
        ticket = self._ticket(
            stage_id=self.stage_in_progress.id,
            assigned_user_id=self.support.id,
            team_id=team.id,
        )

        ticket.with_user(self.support).write({'stage_id': self.stage_new.id})

        self.assertEqual(ticket.stage_id, self.stage_new)
        self.assertFalse(ticket.assigned_user_id)
        self.assertFalse(ticket.team_id)

    def test_assigned_support_can_drag_to_closed(self):
        ticket = self._ticket(
            stage_id=self.stage_in_progress.id,
            assigned_user_id=self.support.id,
        )

        ticket.with_user(self.support).write({'stage_id': self.stage_closed.id})

        self.assertEqual(ticket.stage_id, self.stage_closed)
        self.assertTrue(ticket.closed_ticket_date)

    def test_unassigned_support_cannot_drag_to_closed(self):
        ticket = self._ticket(stage_id=self.stage_in_progress.id)

        with self.assertRaises(UserError):
            ticket.with_user(self.support).write({
                'stage_id': self.stage_closed.id,
            })

    def test_requester_cannot_drag_stage(self):
        ticket = self._ticket()

        with self.assertRaises(UserError):
            ticket.with_user(self.requester).write({
                'stage_id': self.stage_in_progress.id,
            })
