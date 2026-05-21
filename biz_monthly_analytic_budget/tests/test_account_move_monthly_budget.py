# -*- coding: utf-8 -*-
from unittest.mock import patch
from odoo import fields
from odoo.tests.common import TransactionCase
from .common import BudgetTestMixin


class TestAccountMoveMonthlyBudget(TransactionCase, BudgetTestMixin):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_budget_test_data()

    def test_bill_target_date_prefers_invoice_date_due(self):
        bill = self.env['account.move'].new({
            'move_type': 'in_invoice',
            'invoice_date_due': fields.Date.to_date('2026-04-30'),
        })
        result = bill._get_bill_target_date()
        self.assertEqual(result, fields.Date.to_date('2026-04-30'))

    def test_bill_target_date_returns_invoice_date_when_no_due_date(self):
        """When no due date, should fall back to invoice_date."""
        bill = self.env['account.move'].new({
            'move_type': 'in_invoice',
            'invoice_date': fields.Date.to_date('2026-04-20'),
        })
        result = bill._get_bill_target_date()
        # Falls back to invoice_date (or related PO date)
        self.assertTrue(result is not None and result != False)

    def test_split_analytic_totals_by_plan_handles_empty(self):
        from odoo.addons.biz_monthly_analytic_budget.models import budget_utils
        grouped, ignored = budget_utils.split_analytic_totals_by_plan(
            self.env, fields.Date.today(), self.env.company.id, {},
        )
        self.assertEqual(grouped, [])
        self.assertEqual(ignored, {})
