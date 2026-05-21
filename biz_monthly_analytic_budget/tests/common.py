# -*- coding: utf-8 -*-
"""
Shared test helpers for biz_monthly_analytic_budget tests.
"""
from datetime import timedelta
from odoo import fields


class BudgetTestMixin:
    """Mixin providing common setup for budget tests."""

    @classmethod
    def _setup_budget_test_data(cls):
        """Create base test records: analytic plan, analytic accounts, partner, product, employee."""
        cls.analytic_plan = cls.env['account.analytic.plan'].create({
            'name': 'Test Plan',
        })
        cls.analytic_account = cls.env['account.analytic.account'].create({
            'name': 'Test Analytic',
            'plan_id': cls.analytic_plan.id,
        })
        cls.analytic_account_2 = cls.env['account.analytic.account'].create({
            'name': 'Test Analytic 2',
            'plan_id': cls.analytic_plan.id,
        })
        cls.partner = cls.env['res.partner'].create({
            'name': 'Test Vendor',
        })
        cls.product = cls.env['product.product'].create({
            'name': 'Test Product',
        })
        # Create employee for PR (employee_id is required)
        employee_user = cls.env['res.users'].create({
            'name': 'Test Employee User',
            'login': 'test_budget_employee_%s' % cls.env['ir.sequence'].next_by_code('ir.sequence'),
            'email': 'test_budget@test.com',
        })
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Test Employee',
            'user_id': employee_user.id,
        })

    @classmethod
    def _create_confirmed_plan(cls, target_date, budget_amount=10000):
        """Create and confirm a budget plan covering target_date."""
        plan = cls.env['monthly.budget.plan'].create({
            'month': str(target_date.month),
            'year': str(target_date.year),
            'company_id': cls.env.company.id,
            'total_budget': budget_amount,
        })
        cls.env['monthly.budget.line'].create({
            'plan_id': plan.id,
            'analytic_account_id': cls.analytic_account.id,
            'percentage': 100.0,
        })
        plan.action_confirm()
        return plan

    @classmethod
    def _create_pr(cls, lines=None, target=None, state='draft'):
        """Helper to create a PR with budget-linked lines."""
        if lines is None:
            lines = [(0, 0, {
                'product_id': cls.product.id,
                'quantity': 1,
                'unit_price': 100,
                'analytic_distribution': {str(cls.analytic_account.id): 100},
            })]
        pr = cls.env['employee.purchase.requisition'].create({
            'employee_id': cls.employee.id,
            'user_id': cls.employee.user_id.id,
            'vendor_id': cls.partner.id,
            'requisition_order_ids': lines,
        })
        if target:
            pr.write({'payment_date': target, 'payment_date_manual': target})
        if state != 'draft':
            pr.write({'state': state})
        return pr

    @classmethod
    def _create_po(cls, lines=None, target=None, pr_name=False):
        """Helper to create a PO with budget-linked lines."""
        if lines is None:
            lines = [(0, 0, {
                'product_id': cls.product.id,
                'product_qty': 1,
                'price_unit': 100,
                'analytic_distribution': {str(cls.analytic_account.id): 100},
            })]
        vals = {
            'partner_id': cls.partner.id,
            'order_line': lines,
        }
        if pr_name:
            vals['requisition_order'] = pr_name
        po = cls.env['purchase.order'].create(vals)
        if target:
            po.write({'payment_date': target, 'payment_date_manual': target})
        return po
