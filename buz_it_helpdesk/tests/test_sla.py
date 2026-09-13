from datetime import datetime

import pytz

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
        cls.group_agent = cls.env.ref('buz_it_helpdesk.group_it_support_agent')
        cls.manager = cls.env['res.users'].create({
            'name': 'SLA Manager', 'login': 'sla-manager',
            'email': 'sla-manager@example.com',
            'groups_id': [Command.set([cls.group_user.id, cls.group_manager.id])],
        })
        cls.requester = cls.env['res.users'].create({
            'name': 'SLA Requester', 'login': 'sla-requester',
            'email': 'sla-requester@example.com',
            'groups_id': [Command.set([cls.group_user.id, cls.group_requester.id])],
        })
        cls.agent = cls.env['res.users'].create({
            'name': 'SLA Agent', 'login': 'sla-agent',
            'email': 'sla-agent@example.com',
            'groups_id': [Command.set([cls.group_user.id, cls.group_agent.id])],
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

    def test_business_time_skips_consecutive_holidays(self):
        self.config.holiday_ids = [
            Command.create({'date': '2026-09-14', 'name': 'Holiday 1'}),
            Command.create({'date': '2026-09-15', 'name': 'Holiday 2'}),
        ]
        start = datetime(2026, 9, 11, 3, 0)  # 10:00 Bangkok, Friday
        end = datetime(2026, 9, 16, 3, 0)  # 10:00 Bangkok, Wednesday
        self.assertEqual(self.config.business_minutes_between(start, end), 480)

    def test_timezone_must_be_supported(self):
        with self.assertRaises(ValidationError):
            self.config.write({'timezone': 'Mars/Olympus'})

    def test_working_hours_reject_invalid_format_and_allow_24(self):
        with self.assertRaises(ValidationError):
            self.config.write({'work_start': 8.999})
        self.config.write({
            'work_start': 20.0,
            'work_end': 24.0,
            'lunch_start': 21.0,
            'lunch_end': 22.0,
        })
        intervals = self.config._work_intervals(
            datetime(2026, 9, 11).date(),
            pytz.timezone('Asia/Bangkok'),
        )
        self.assertEqual(intervals[-1][1].date().isoformat(), '2026-09-12')
        self.assertEqual(intervals[-1][1].hour, 0)

    def test_only_one_sla_settings_record_per_company(self):
        self.assertIn(
            ('company_unique', 'unique(company_id)',
             'Only one SLA Settings record is allowed per company.'),
            self.env['buz.helpdesk.sla.config']._sql_constraints,
        )

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

    def test_no_matching_rule_shows_no_sla_without_deadlines(self):
        ticket = self.env['buz.helpdesk.ticket'].with_user(self.manager).create({
            'subject': 'No matching SLA rule', 'requester_id': self.requester.id,
            'category_id': self.category.id, 'priority': '3',
        })
        ticket.action_create_ticket()
        self.assertEqual(ticket.sla_status, 'no_sla')
        self.assertFalse(ticket.sla_rule_id)
        self.assertFalse(ticket.sla_response_deadline)
        self.assertFalse(ticket.sla_resolution_deadline)

    def test_incomplete_sla_settings_do_not_create_deadlines(self):
        self.env.cr.execute(
            "UPDATE buz_helpdesk_sla_config SET work_end = 25 WHERE id = %s",
            (self.config.id,),
        )
        ticket = self.env['buz.helpdesk.ticket'].with_user(self.manager).create({
            'subject': 'Incomplete SLA settings', 'requester_id': self.requester.id,
            'category_id': self.category.id,
        })
        self.env['buz.helpdesk.sla.rule'].with_user(self.manager).create({
            'config_id': self.config.id, 'name': 'Incomplete Config Rule',
        })
        ticket.action_create_ticket()
        self.assertEqual(ticket.sla_status, 'no_sla')
        self.assertFalse(ticket.sla_response_deadline)
        self.assertFalse(ticket.sla_resolution_deadline)

    def test_sla_starts_on_new_and_records_response_and_resolution(self):
        self.env['buz.helpdesk.sla.rule'].with_user(self.manager).create({
            'config_id': self.config.id, 'name': 'Workflow Rule',
        })
        team = self.env['buz.helpdesk.team'].with_user(self.manager).create({
            'name': 'SLA Team', 'user_ids': [Command.link(self.agent.id)],
        })
        ticket = self.env['buz.helpdesk.ticket'].with_user(self.manager).create({
            'subject': 'SLA workflow', 'requester_id': self.requester.id,
            'category_id': self.category.id,
        })
        ticket.action_create_ticket()
        self.assertTrue(ticket.sla_start_at)
        ticket.with_user(self.manager).write({
            'team_id': team.id, 'assigned_user_id': self.agent.id,
        })
        self.assertTrue(ticket.sla_response_at)
        ticket.with_user(self.agent).action_mark_resolved()
        self.assertTrue(ticket.sla_resolution_at)

    def test_paused_status_keeps_deadlines_unchanged(self):
        rule = self.env['buz.helpdesk.sla.rule'].with_user(self.manager).create({
            'config_id': self.config.id, 'name': 'Paused Rule',
        })
        ticket = self.env['buz.helpdesk.ticket'].with_user(self.manager).create({
            'subject': 'Paused SLA', 'requester_id': self.requester.id,
            'category_id': self.category.id,
        })
        ticket.action_create_ticket()
        before_response = ticket.sla_response_deadline
        before_resolution = ticket.sla_resolution_deadline
        ticket._write_workflow_fields({
            'stage_id': self.env.ref('buz_it_helpdesk.stage_pending_user').id,
        })
        self.assertEqual(ticket.sla_rule_id, rule)
        self.assertEqual(ticket.sla_status, 'paused')
        self.assertEqual(ticket.sla_response_deadline, before_response)
        self.assertEqual(ticket.sla_resolution_deadline, before_resolution)

    def test_legacy_category_priority_are_locked_for_agent(self):
        ticket = self._legacy_ticket(category_id=None)
        with self.assertRaises(UserError):
            ticket.with_user(self.requester).write({'category_id': self.category.id})

    def test_requester_cannot_read_sla_settings(self):
        with self.assertRaises(AccessError):
            self.env['buz.helpdesk.sla.config'].with_user(self.requester).search([])

    def test_support_agent_can_read_but_cannot_change_sla_settings(self):
        self.assertTrue(
            self.config.with_user(self.agent).search_count([
                ('id', '=', self.config.id),
            ])
        )
        with self.assertRaises(AccessError):
            self.config.with_user(self.agent).write({'name': 'Agent Edit'})

    def test_sla_settings_are_isolated_by_company(self):
        other_company = self.env['res.company'].create({'name': 'SLA Other Company'})
        self.manager.write({'company_ids': [Command.link(other_company.id)]})
        other_config = self.env['buz.helpdesk.sla.config'].with_user(
            self.manager,
        ).with_context(allowed_company_ids=[other_company.id]).create({
            'name': 'Other Company SLA',
            'company_id': other_company.id,
        })
        self.assertTrue(other_config)
        self.assertFalse(
            self.env['buz.helpdesk.sla.config'].with_user(self.manager).with_context(
                allowed_company_ids=[other_company.id],
            ).search([('id', '=', self.config.id)])
        )
