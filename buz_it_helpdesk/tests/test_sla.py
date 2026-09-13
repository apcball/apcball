from datetime import datetime

from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestHelpdeskSla(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.group_user = cls.env.ref('base.group_user')
        cls.group_agent = cls.env.ref('buz_it_helpdesk.group_it_support_agent')
        cls.group_manager = cls.env.ref('buz_it_helpdesk.group_it_helpdesk_manager')
        cls.group_requester = cls.env.ref('buz_it_helpdesk.group_it_requester')
        cls.manager = cls.env['res.users'].create({
            'name': 'SLA Manager', 'login': 'sla-manager',
            'groups_id': [Command.set([cls.group_user.id, cls.group_manager.id])],
        })
        cls.requester = cls.env['res.users'].create({
            'name': 'SLA Requester', 'login': 'sla-requester',
            'groups_id': [Command.set([cls.group_user.id, cls.group_requester.id])],
        })
        cls.category = cls.env['buz.helpdesk.category'].create({'name': 'SLA Category'})
        cls.other_category = cls.env['buz.helpdesk.category'].create({'name': 'Other SLA Category'})
        cls.config = cls.env['buz.helpdesk.sla.config'].with_user(cls.manager).create({
            'name': 'SLA Test Settings', 'timezone': 'Asia/Bangkok',
        })
        # จำลองข้อมูลเก่าก่อน field required ถูกบังคับใช้ใน isolated test DB
        cls.env.cr.execute(
            'ALTER TABLE buz_helpdesk_ticket '
            'ALTER COLUMN category_id DROP NOT NULL'
        )
        cls.env.cr.execute(
            'ALTER TABLE buz_helpdesk_ticket '
            'ALTER COLUMN priority DROP NOT NULL'
        )

    def _legacy_ticket(self, **updates):
        """สร้างข้อมูล legacy ผ่าน SQL เพื่อจำลอง Ticket เก่าที่ไม่ครบข้อมูล"""
        ticket = self.env['buz.helpdesk.ticket'].with_user(self.manager).create({
            'subject': 'Legacy SLA ticket', 'requester_id': self.requester.id,
            'category_id': self.category.id,
        })
        values = {
            'stage_id': self.env.ref('buz_it_helpdesk.stage_new').id,
            'priority': None,
            'category_id': self.category.id,
            'sla_start_at': None,
            'sla_response_at': None,
            'sla_resolution_at': None,
        }
        values.update(updates)
        assignments = ', '.join('%s = %%s' % key for key in values)
        self.env.cr.execute(
            'UPDATE buz_helpdesk_ticket SET %s WHERE id = %%s' % assignments,
            tuple(values.values()) + (ticket.id,),
        )
        ticket.invalidate_recordset()
        return ticket

    def test_rule_specificity_prefers_exact_match(self):
        rules = self.env['buz.helpdesk.sla.rule'].with_user(self.manager)
        rules.create([
            {'config_id': self.config.id, 'name': 'Generic', 'sequence': 1},
            {'config_id': self.config.id, 'name': 'Category', 'sequence': 2,
             'category_id': self.category.id},
            {'config_id': self.config.id, 'name': 'Exact', 'sequence': 99,
             'category_id': self.category.id, 'priority': '2'},
        ])
        ticket = self.env['buz.helpdesk.ticket'].with_user(self.manager).create({
            'subject': 'SLA selection', 'requester_id': self.requester.id,
            'category_id': self.category.id, 'priority': '2',
        })
        self.assertEqual(ticket._get_sla_rule().name, 'Exact')

    def test_new_ticket_requires_category_and_defaults_priority_to_normal(self):
        ticket_model = self.env['buz.helpdesk.ticket'].with_user(self.manager)
        with self.assertRaises(ValidationError):
            ticket_model.create({
                'subject': 'Missing category', 'requester_id': self.requester.id,
            })
        ticket = ticket_model.create({
            'subject': 'New ticket defaults', 'requester_id': self.requester.id,
            'category_id': self.category.id,
        })
        self.assertEqual(ticket.priority, '1')

    def test_business_time_skips_lunch_weekend_and_holiday(self):
        self.config.holiday_ids = [Command.create({
            'date': '2026-09-14', 'name': 'Holiday',
        })]
        start = datetime(2026, 9, 11, 3, 0)  # 10:00 Bangkok
        end = datetime(2026, 9, 15, 3, 0)  # 10:00 Bangkok
        self.assertEqual(self.config.business_minutes_between(start, end), 480)

    def test_category_and_priority_lock_after_new(self):
        ticket = self.env['buz.helpdesk.ticket'].with_user(self.manager).create({
            'subject': 'SLA lock', 'requester_id': self.requester.id,
            'category_id': self.category.id,
        })
        ticket.action_create_ticket()
        with self.assertRaises(UserError):
            ticket.write({'priority': '3'})
        with self.assertRaises(UserError):
            ticket.write({'category_id': self.other_category.id})

    def test_legacy_missing_category_manager_starts_sla_now(self):
        ticket = self._legacy_ticket(category_id=None)
        with self.assertRaises(UserError):
            ticket.with_user(self.requester).write({
                'category_id': self.category.id,
            })

        before = datetime.utcnow()
        ticket.with_user(self.manager).write({'category_id': self.other_category.id})
        after = datetime.utcnow()
        self.assertEqual(ticket.priority, '1')
        self.assertTrue(ticket.sla_start_at)
        self.assertGreaterEqual(ticket.sla_start_at, before.replace(microsecond=0))
        self.assertLessEqual(ticket.sla_start_at, after)
        self.assertFalse(ticket.sla_response_at)

    def test_legacy_missing_priority_manager_uses_normal_and_starts_sla(self):
        ticket = self._legacy_ticket()
        before = datetime.utcnow()
        ticket.with_user(self.manager).write({'category_id': self.other_category.id})
        after = datetime.utcnow()
        self.assertEqual(ticket.priority, '1')
        self.assertTrue(ticket.sla_start_at)
        self.assertGreaterEqual(ticket.sla_start_at, before.replace(microsecond=0))
        self.assertLessEqual(ticket.sla_start_at, after)

    def test_legacy_received_ticket_marks_response_at_sla_start(self):
        in_progress = self.env.ref('buz_it_helpdesk.stage_in_progress')
        ticket = self._legacy_ticket(
            stage_id=in_progress.id,
            assigned_user_id=self.manager.id,
        )
        ticket.with_user(self.manager).write({'priority': '2'})
        self.assertEqual(ticket.sla_response_at, ticket.sla_start_at)

    def test_complete_legacy_ticket_without_sla_does_not_start_automatically(self):
        ticket = self._legacy_ticket(priority='1')
        ticket.with_user(self.manager).write({'subject': 'Still no SLA'})
        self.assertFalse(ticket.sla_start_at)
        self.assertEqual(ticket.sla_status, 'no_sla')

    def test_legacy_category_priority_are_locked_for_agent(self):
        ticket = self._legacy_ticket(category_id=None)
        with self.assertRaises(UserError):
            ticket.with_user(self.requester).write({'category_id': self.category.id})

    def test_requester_cannot_read_sla_settings(self):
        with self.assertRaises(AccessError):
            self.env['buz.helpdesk.sla.config'].with_user(self.requester).search([])
