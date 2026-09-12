from datetime import datetime

from odoo import Command
from odoo.exceptions import AccessError, UserError
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

    def test_requester_cannot_read_sla_settings(self):
        with self.assertRaises(AccessError):
            self.env['buz.helpdesk.sla.config'].with_user(self.requester).search([])
