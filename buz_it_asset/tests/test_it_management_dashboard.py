from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestITManagementDashboard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.category = cls.env['buz.it.asset.category'].create({
            'name': 'Dashboard Test Category',
        })
        cls.asset_type = cls.env['buz.it.asset.type'].create({
            'name': 'Dashboard Laptop',
            'category_id': cls.category.id,
        })
        cls.support_user = cls.env['res.users'].create({
            'name': 'Dashboard Support User',
            'login': 'dashboard_support_user',
            'company_id': cls.company.id,
            'company_ids': [fields.Command.set([cls.company.id])],
            'groups_id': [fields.Command.set([
                cls.env.ref('buz_it_helpdesk.group_it_support_agent').id,
            ])],
        })
        cls.dashboard = cls.env['buz.it.management.dashboard'].with_user(
            cls.support_user
        )

    def test_dashboard_returns_live_kpis_and_statuses(self):
        asset = self.env['buz.it.asset'].create({
            'name': 'Dashboard Laptop',
            'type_id': self.asset_type.id,
            'serial_number': 'DASHBOARD-001',
        })
        ticket = self.env['buz.helpdesk.ticket'].create({
            'subject': 'Dashboard Ticket',
        })
        ticket.with_context(buz_helpdesk_transition=True).write({
            'stage_id': self.env.ref('buz_it_helpdesk.stage_new').id,
            'create_ticket_date': fields.Date.context_today(ticket),
        })
        product = self.env['buz.it.software.product'].create({
            'name': 'Dashboard Software',
            'company_id': self.company.id,
        })
        self.env['buz.it.software.license'].create({
            'name': 'Dashboard License',
            'product_id': product.id,
            'expiration_date': fields.Date.context_today(self.env['res.company']) + timedelta(days=10),
            'company_id': self.company.id,
        })

        data = self.dashboard.get_dashboard_data({
            'period': 'this_month',
            'company_ids': [self.company.id],
        })

        self.assertEqual(data['kpis']['open_tickets'], 1)
        self.assertEqual(data['kpis']['assets_available'], 1)
        self.assertEqual(data['kpis']['licenses_expiring'], 1)
        self.assertEqual(
            sum(row['value'] for row in data['ticket_status']),
            1,
        )
        self.assertIn(
            {'label': 'Available', 'state': 'available', 'value': 1},
            data['asset_status'],
        )
        self.assertEqual(data['recent_tickets'][0]['id'], ticket.id)
        self.assertEqual(asset.company_id, self.company)

    def test_dashboard_drilldown_preserves_company_domain(self):
        action = self.dashboard.get_drilldown_action(
            'open_tickets',
            {
                'period': 'this_month',
                'company_ids': [self.company.id],
            },
        )

        self.assertEqual(action['res_model'], 'buz.helpdesk.ticket')
        self.assertIn(
            ('company_id', 'in', [self.company.id]),
            action['domain'],
        )

    def test_dashboard_rejects_unknown_company(self):
        other_company = self.env['res.company'].create({
            'name': 'Dashboard Other Company',
        })
        with self.assertRaises(UserError):
            self.dashboard.get_dashboard_data({
                'period': 'this_month',
                'company_ids': [other_company.id],
            })
