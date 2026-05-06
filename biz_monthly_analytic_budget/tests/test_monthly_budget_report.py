# -*- coding: utf-8 -*-
from unittest.mock import Mock, patch

from odoo.tests.common import TransactionCase


class TestMonthlyBudgetReport(TransactionCase):

    def test_dashboard_uses_commitment_ledger_for_used_amount(self):
        report = self.env['monthly.budget.report']
        fake_plans = Mock(ids=[99], filtered=lambda fn: fake_plans)

        captured_sql = {}

        def _capture_execute(query, params=None):
            captured_sql['query'] = query
            captured_sql['params'] = params
            return None

        with patch.object(type(report), 'refresh_materialized_view', return_value=None):
            with patch.object(type(report), '_get_trend', return_value=[{'month': 'Apr 2026', 'budget': 100.0, 'used': 30.0}]):
                with patch.object(type(report), '_get_alerts', return_value=[]):
                    with patch.object(type(self.env['monthly.budget.plan']), 'search', return_value=fake_plans):
                        with patch.object(type(self.env.cr), 'execute', side_effect=_capture_execute):
                            with patch.object(type(self.env.cr), 'dictfetchall', return_value=[{
                                'analytic_account_id': None,
                                'department_id': None,
                                'project_id': None,
                                'category': None,
                                'budget': 100.0,
                                'reserved': 20.0,
                                'used': 30.0,
                            }]):
                                data = report.get_dashboard_data({})

        self.assertIn('budget_commitment', captured_sql['query'])
        self.assertIn("bc.state = 'used'", captured_sql['query'])
        self.assertNotIn('account_move_line', captured_sql['query'])
        self.assertEqual(data['kpi']['used'], 30.0)
        self.assertEqual(data['waterfall'][2]['label'], 'Used')
        self.assertEqual(data['waterfall'][2]['value'], -30.0)
        self.assertEqual(data['trend'][0]['used'], 30.0)
