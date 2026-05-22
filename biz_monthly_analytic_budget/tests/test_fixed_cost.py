# -*- coding: utf-8 -*-
"""
Tests for monthly fixed cost model: confirm, cancel, unlink, budget check.
"""
from odoo import fields
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError
from .common import BudgetTestMixin


class TestFixedCost(TransactionCase, BudgetTestMixin):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_budget_test_data()

    def _create_plan_with_budget(self, budget_amount=100000):
        """Create a confirmed plan with a budget line."""
        target = fields.Date.today().replace(day=1)
        plan = self.env['monthly.budget.plan'].create({
            'month': str(target.month),
            'year': str(target.year),
            'company_id': self.env.company.id,
            'total_budget': budget_amount,
        })
        self.env['monthly.budget.line'].create({
            'plan_id': plan.id,
            'analytic_account_id': self.analytic_account.id,
            'percentage': 100.0,
        })
        plan.action_confirm()
        return plan

    def test_confirm_fixed_cost_reserves_budget(self):
        plan = self._create_plan_with_budget()
        fc = self.env['monthly.budget.fixed.cost'].create({
            'name': 'Rent',
            'plan_id': plan.id,
            'analytic_account_id': self.analytic_account.id,
            'amount': 5000.0,
        })
        fc.action_confirm()
        self.assertEqual(fc.state, 'confirmed')

        commitment = self.env['budget.commitment'].sudo().search([
            ('document_model', '=', 'monthly.budget.fixed.cost'),
            ('document_id', '=', fc.id),
            ('state', '=', 'reserved'),
        ])
        self.assertTrue(commitment)
        self.assertAlmostEqual(commitment.amount, 5000.0, places=2)

    def test_confirm_fixed_cost_insufficient_budget_raises(self):
        plan = self._create_plan_with_budget(budget_amount=1000)
        fc = self.env['monthly.budget.fixed.cost'].create({
            'name': 'Big Expense',
            'plan_id': plan.id,
            'analytic_account_id': self.analytic_account.id,
            'amount': 5000.0,
        })
        with self.assertRaises(UserError):
            fc.action_confirm()

    def test_cancel_fixed_cost_releases_budget(self):
        plan = self._create_plan_with_budget()
        fc = self.env['monthly.budget.fixed.cost'].create({
            'name': 'Rent',
            'plan_id': plan.id,
            'analytic_account_id': self.analytic_account.id,
            'amount': 5000.0,
        })
        fc.action_confirm()
        fc.action_cancel()
        self.assertEqual(fc.state, 'cancelled')

        active = self.env['budget.commitment'].sudo().search([
            ('document_model', '=', 'monthly.budget.fixed.cost'),
            ('document_id', '=', fc.id),
            ('state', 'in', ('reserved', 'used')),
        ])
        self.assertFalse(active)

    def test_unlink_confirmed_fixed_cost_raises(self):
        plan = self._create_plan_with_budget()
        fc = self.env['monthly.budget.fixed.cost'].create({
            'name': 'Rent',
            'plan_id': plan.id,
            'analytic_account_id': self.analytic_account.id,
            'amount': 5000.0,
        })
        fc.action_confirm()
        with self.assertRaises(UserError):
            fc.unlink()

    def test_unlink_draft_fixed_cost_ok(self):
        plan = self._create_plan_with_budget()
        fc = self.env['monthly.budget.fixed.cost'].create({
            'name': 'Rent',
            'plan_id': plan.id,
            'analytic_account_id': self.analytic_account.id,
            'amount': 5000.0,
        })
        fc.unlink()
        self.assertFalse(fc.exists())

    def test_confirm_already_confirmed_skips(self):
        plan = self._create_plan_with_budget()
        fc = self.env['monthly.budget.fixed.cost'].create({
            'name': 'Rent',
            'plan_id': plan.id,
            'analytic_account_id': self.analytic_account.id,
            'amount': 5000.0,
        })
        fc.action_confirm()
        # Confirm again should not raise, just skip
        fc.action_confirm()
        self.assertEqual(fc.state, 'confirmed')

    def test_cancel_draft_skips(self):
        plan = self._create_plan_with_budget()
        fc = self.env['monthly.budget.fixed.cost'].create({
            'name': 'Rent',
            'plan_id': plan.id,
            'analytic_account_id': self.analytic_account.id,
            'amount': 5000.0,
        })
        fc.action_cancel()
        # Still draft — cancel only affects confirmed
        self.assertEqual(fc.state, 'draft')
