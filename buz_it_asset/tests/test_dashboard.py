from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestITManagementDashboard(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group_user = cls.env.ref('base.group_user')
        cls.group_agent = cls.env.ref('buz_it_helpdesk.group_it_support_agent')
        cls.group_requester = cls.env.ref('buz_it_helpdesk.group_it_requester')
        cls.agent = cls.env['res.users'].create({
            'name': 'Dashboard Agent',
            'login': 'dashboard-agent',
            'email': 'dashboard-agent@example.com',
            'groups_id': [Command.set([group_user.id, cls.group_agent.id])],
        })
        cls.requester = cls.env['res.users'].create({
            'name': 'Dashboard Requester',
            'login': 'dashboard-requester',
            'email': 'dashboard-requester@example.com',
            'groups_id': [Command.set([group_user.id, cls.group_requester.id])],
        })

    def test_requester_cannot_access_dashboard(self):
        dashboard = self.env['buz.it.management.dashboard'].with_user(
            self.requester
        )
        with self.assertRaises(AccessError):
            dashboard.get_dashboard_data()

    def test_dashboard_payload_contains_new_metrics(self):
        dashboard = self.env['buz.it.management.dashboard'].with_user(self.agent)
        data = dashboard.get_dashboard_data()
        self.assertIn('overdue_sla', data['kpis'])
        self.assertIn('unassigned_tickets', data['kpis'])
        self.assertIn('licenses_expired', data['kpis'])
        self.assertIn('overallocated', data['license_seats'])
        self.assertIn('sla', data['needs_attention'])
        self.assertIn('unassigned_tickets', data['needs_attention'])

    def test_needs_attention_drilldown_combines_urgent_and_sla(self):
        dashboard = self.env['buz.it.management.dashboard'].with_user(self.agent)
        action = dashboard.get_drilldown_action('needs_attention')
        self.assertEqual(action['name'], 'Needs Attention')
        self.assertEqual(action['res_model'], 'buz.helpdesk.ticket')
        self.assertIn('|', action['domain'])

    def test_dashboard_ticket_domain_excludes_archived_and_draft(self):
        dashboard = self.env['buz.it.management.dashboard'].with_user(self.agent)
        normalized = dashboard._normalize_filters()
        domain = dashboard._ticket_base_domain(normalized)
        self.assertIn(('active', '=', True), domain)
        self.assertIn(('stage_id', '!=', self.env.ref(
            'buz_it_helpdesk.stage_draft'
        ).id), domain)

    def test_human_duration_is_readable(self):
        dashboard = self.env['buz.it.management.dashboard'].with_user(self.agent)
        self.assertEqual(dashboard._human_duration(5 * 60), 'เกิน 5 นาที')
        self.assertEqual(
            dashboard._human_duration((2 * 24 + 3) * 60 * 60),
            'เกิน 2 วัน 3 ชั่วโมง',
        )
