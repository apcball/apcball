# -*- coding: utf-8 -*-
"""
Tests for monthly budget plan lifecycle: confirm, close, reset, constraints.
"""
from odoo import fields
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError
from .common import BudgetTestMixin


class TestPlanLifecycle(TransactionCase, BudgetTestMixin):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_budget_test_data()

    # ── create & sequence ────────────────────────────────────────

    def test_create_plan_generates_name(self):
        plan = self.env['monthly.budget.plan'].create({
            'month': '1',
            'year': '2026',
            'company_id': self.env.company.id,
            'total_budget': 10000,
        })
        self.assertNotEqual(plan.name, 'New')

    # ── period dates compute ─────────────────────────────────────

    def test_compute_period_dates(self):
        plan = self.env['monthly.budget.plan'].create({
            'month': '2',
            'year': '2026',
            'company_id': self.env.company.id,
            'total_budget': 10000,
        })
        self.assertEqual(plan.date_from, fields.Date.to_date('2026-02-01'))
        self.assertEqual(plan.date_to, fields.Date.to_date('2026-02-28'))

    def test_compute_period_dates_leap_year(self):
        plan = self.env['monthly.budget.plan'].create({
            'month': '2',
            'year': '2024',
            'company_id': self.env.company.id,
            'total_budget': 10000,
        })
        self.assertEqual(plan.date_to, fields.Date.to_date('2024-02-29'))

    def test_compute_period_dates_december(self):
        plan = self.env['monthly.budget.plan'].create({
            'month': '12',
            'year': '2026',
            'company_id': self.env.company.id,
            'total_budget': 10000,
        })
        self.assertEqual(plan.date_from, fields.Date.to_date('2026-12-01'))
        self.assertEqual(plan.date_to, fields.Date.to_date('2026-12-31'))

    # ── confirm ──────────────────────────────────────────────────

    def test_confirm_draft_plan(self):
        plan = self.env['monthly.budget.plan'].create({
            'month': '1',
            'year': '2026',
            'company_id': self.env.company.id,
            'total_budget': 10000,
        })
        self.assertEqual(plan.state, 'draft')
        plan.action_confirm()
        self.assertEqual(plan.state, 'confirmed')

    def test_confirm_non_draft_raises(self):
        plan = self.env['monthly.budget.plan'].create({
            'month': '1',
            'year': '2026',
            'company_id': self.env.company.id,
            'total_budget': 10000,
        })
        plan.action_confirm()
        with self.assertRaises(ValidationError):
            plan.action_confirm()

    # ── close ────────────────────────────────────────────────────

    def test_close_confirmed_plan(self):
        plan = self.env['monthly.budget.plan'].create({
            'month': '1',
            'year': '2026',
            'company_id': self.env.company.id,
            'total_budget': 10000,
        })
        plan.action_confirm()
        plan.action_close()
        self.assertEqual(plan.state, 'closed')

    def test_close_draft_plan_raises(self):
        plan = self.env['monthly.budget.plan'].create({
            'month': '1',
            'year': '2026',
            'company_id': self.env.company.id,
            'total_budget': 10000,
        })
        with self.assertRaises(ValidationError):
            plan.action_close()

    # ── reset to draft ───────────────────────────────────────────

    def test_reset_draft(self):
        plan = self.env['monthly.budget.plan'].create({
            'month': '1',
            'year': '2026',
            'company_id': self.env.company.id,
            'total_budget': 10000,
        })
        plan.action_confirm()
        plan.action_reset_draft()
        self.assertEqual(plan.state, 'draft')

    # ── constraints ──────────────────────────────────────────────

    def test_year_validation_non_numeric(self):
        with self.assertRaises(ValidationError):
            self.env['monthly.budget.plan'].create({
                'month': '1',
                'year': 'abcd',
                'company_id': self.env.company.id,
                'total_budget': 10000,
            })

    def test_year_validation_before_2000(self):
        with self.assertRaises(ValidationError):
            self.env['monthly.budget.plan'].create({
                'month': '1',
                'year': '1999',
                'company_id': self.env.company.id,
                'total_budget': 10000,
            })

    # ── amendment tracking ───────────────────────────────────────

    def test_budget_change_creates_amendment_increase(self):
        plan = self.env['monthly.budget.plan'].create({
            'month': '1',
            'year': '2026',
            'company_id': self.env.company.id,
            'total_budget': 10000,
        })
        plan.write({'total_budget': 15000})
        amendments = self.env['monthly.budget.amendment'].search([
            ('plan_id', '=', plan.id),
        ])
        self.assertEqual(len(amendments), 1)
        self.assertEqual(amendments.amendment_type, 'increase')
        self.assertEqual(amendments.amount_before, 10000)
        self.assertEqual(amendments.amount_after, 15000)
        self.assertEqual(amendments.amount_change, 5000)

    def test_budget_change_creates_amendment_decrease(self):
        plan = self.env['monthly.budget.plan'].create({
            'month': '1',
            'year': '2026',
            'company_id': self.env.company.id,
            'total_budget': 10000,
        })
        plan.write({'total_budget': 7000})
        amendments = self.env['monthly.budget.amendment'].search([
            ('plan_id', '=', plan.id),
        ])
        self.assertEqual(len(amendments), 1)
        self.assertEqual(amendments.amendment_type, 'decrease')
        self.assertEqual(amendments.amount_change, -3000)

    def test_no_amendment_when_same_value(self):
        plan = self.env['monthly.budget.plan'].create({
            'month': '1',
            'year': '2026',
            'company_id': self.env.company.id,
            'total_budget': 10000,
        })
        plan.write({'total_budget': 10000})
        count = self.env['monthly.budget.amendment'].search_count([
            ('plan_id', '=', plan.id),
        ])
        self.assertEqual(count, 0)

    # ── budget line allocation ───────────────────────────────────

    def test_line_budget_amount_computed_from_percentage(self):
        plan = self.env['monthly.budget.plan'].create({
            'month': '1',
            'year': '2026',
            'company_id': self.env.company.id,
            'total_budget': 10000,
        })
        line = self.env['monthly.budget.line'].create({
            'plan_id': plan.id,
            'analytic_account_id': self.analytic_account.id,
            'percentage': 60.0,
        })
        self.assertAlmostEqual(line.budget_amount, 6000.0, places=2)

    def test_plan_totals_computed(self):
        plan = self.env['monthly.budget.plan'].create({
            'month': '1',
            'year': '2026',
            'company_id': self.env.company.id,
            'total_budget': 10000,
        })
        self.env['monthly.budget.line'].create({
            'plan_id': plan.id,
            'analytic_account_id': self.analytic_account.id,
            'percentage': 100.0,
        })
        plan.invalidate_recordset(['allocated_amount', 'allocated_percentage'])
        self.assertAlmostEqual(plan.allocated_amount, 10000.0, places=2)
        self.assertAlmostEqual(plan.allocated_percentage, 100.0, places=2)
