# -*- coding: utf-8 -*-
"""
Tests for budget line constraints: allocation > 100%, percentage bounds, unique dimensions.
"""
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError
from .common import BudgetTestMixin


class TestBudgetLineConstraints(TransactionCase, BudgetTestMixin):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_budget_test_data()

    def _create_plan(self):
        return self.env['monthly.budget.plan'].create({
            'month': '1',
            'year': '2026',
            'company_id': self.env.company.id,
            'total_budget': 10000,
        })

    def test_allocation_over_100_percent_raises(self):
        plan = self._create_plan()
        self.env['monthly.budget.line'].create({
            'plan_id': plan.id,
            'analytic_account_id': self.analytic_account.id,
            'percentage': 80.0,
        })
        self.env['monthly.budget.line'].create({
            'plan_id': plan.id,
            'analytic_account_id': self.analytic_account_2.id,
            'percentage': 30.0,
        })
        with self.assertRaises(ValidationError):
            plan._check_allocation()

    def test_allocation_exactly_100_percent_passes(self):
        plan = self._create_plan()
        self.env['monthly.budget.line'].create({
            'plan_id': plan.id,
            'analytic_account_id': self.analytic_account.id,
            'percentage': 60.0,
        })
        self.env['monthly.budget.line'].create({
            'plan_id': plan.id,
            'analytic_account_id': self.analytic_account_2.id,
            'percentage': 40.0,
        })
        # Should not raise
        plan._check_allocation()

    def test_percentage_negative_raises(self):
        plan = self._create_plan()
        with self.assertRaises(ValidationError):
            self.env['monthly.budget.line'].create({
                'plan_id': plan.id,
                'analytic_account_id': self.analytic_account.id,
                'percentage': -10.0,
            })

    def test_percentage_over_100_raises(self):
        plan = self._create_plan()
        with self.assertRaises(ValidationError):
            self.env['monthly.budget.line'].create({
                'plan_id': plan.id,
                'analytic_account_id': self.analytic_account.id,
                'percentage': 150.0,
            })

    def test_duplicate_dimension_key_raises(self):
        plan = self._create_plan()
        self.env['monthly.budget.line'].create({
            'plan_id': plan.id,
            'analytic_account_id': self.analytic_account.id,
            'percentage': 50.0,
        })
        with self.assertRaises(Exception):
            self.env['monthly.budget.line'].create({
                'plan_id': plan.id,
                'analytic_account_id': self.analytic_account.id,
                'percentage': 50.0,
            })

    def test_same_analytic_different_plan_ok(self):
        plan1 = self._create_plan()
        plan2 = self.env['monthly.budget.plan'].create({
            'month': '2',
            'year': '2026',
            'company_id': self.env.company.id,
            'total_budget': 5000,
        })
        self.env['monthly.budget.line'].create({
            'plan_id': plan1.id,
            'analytic_account_id': self.analytic_account.id,
            'percentage': 100.0,
        })
        # Same analytic on different plan is fine
        line2 = self.env['monthly.budget.line'].create({
            'plan_id': plan2.id,
            'analytic_account_id': self.analytic_account.id,
            'percentage': 100.0,
        })
        self.assertTrue(line2.id)
