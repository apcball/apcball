# -*- coding: utf-8 -*-
from datetime import timedelta
from odoo import fields
from odoo.tests.common import TransactionCase
from .common import BudgetTestMixin


class TestBudgetApprovalRequestAmounts(TransactionCase, BudgetTestMixin):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_budget_test_data()

    def test_pr_approval_request_shows_document_amount(self):
        target = fields.Date.today() + timedelta(days=15)
        self._create_confirmed_plan(target, budget_amount=100000)

        pr = self._create_pr(lines=[(0, 0, {
            'product_id': self.product.id,
            'quantity': 10,
            'unit_price': 100,
            'analytic_distribution': {str(self.analytic_account.id): 100},
        })], target=target)

        wizard_ctx = pr.action_request_monthly_budget_approval()['context']
        wizard = self.env['monthly.budget.request.reason.wizard'].with_context(**wizard_ctx).create({
            'reason': 'Test budget overage',
        })
        wizard.action_submit_request()

        request = self.env['buz.monthly.budget.approval.request'].search([
            ('document_type', '=', 'pr'),
            ('ref_pr_id', '=', pr.id),
        ], limit=1)
        self.assertTrue(request)
        self.assertAlmostEqual(request.amount_requested, 1000.0, places=2)

    def test_pr_approval_request_recomputes_on_line_change(self):
        target = fields.Date.today() + timedelta(days=15)
        self._create_confirmed_plan(target, budget_amount=100000)

        pr = self._create_pr(lines=[(0, 0, {
            'product_id': self.product.id,
            'quantity': 10,
            'unit_price': 100,
            'analytic_distribution': {str(self.analytic_account.id): 100},
        })], target=target)

        wizard_ctx = pr.action_request_monthly_budget_approval()['context']
        wizard = self.env['monthly.budget.request.reason.wizard'].with_context(**wizard_ctx).create({
            'reason': 'Test recompute',
        })
        wizard.action_submit_request()

        request = self.env['buz.monthly.budget.approval.request'].search([
            ('document_type', '=', 'pr'),
            ('ref_pr_id', '=', pr.id),
            ('state', '=', 'pending'),
        ], limit=1)
        self.assertTrue(request)
        self.assertAlmostEqual(request.amount_requested, 1000.0, places=2)

        pr.requisition_order_ids[0].write({'quantity': 20})
        pr.with_context(skip_approval_recompute=False)._recompute_budget_approval_request()

        request.invalidate_recordset(['amount_requested'])
        self.assertAlmostEqual(request.amount_requested, 2000.0, places=2)

    def test_po_approval_request_uses_amount_untaxed(self):
        target = fields.Date.today() + timedelta(days=15)
        self._create_confirmed_plan(target, budget_amount=100000)

        po = self._create_po(lines=[(0, 0, {
            'product_id': self.product.id,
            'product_qty': 5,
            'price_unit': 100,
            'analytic_distribution': {str(self.analytic_account.id): 100},
        })], target=target)

        wizard_ctx = po.action_request_monthly_budget_approval()['context']
        wizard = self.env['monthly.budget.request.reason.wizard'].with_context(**wizard_ctx).create({
            'reason': 'Test PO budget overage',
        })
        wizard.action_submit_request()

        request = self.env['buz.monthly.budget.approval.request'].search([
            ('document_type', '=', 'po'),
            ('ref_po_id', '=', po.id),
        ], limit=1)
        self.assertTrue(request)
        self.assertAlmostEqual(request.amount_requested, 500.0, places=2)

    def test_po_recompute_keeps_linked_pr_request_amount_from_pr(self):
        target = fields.Date.today() + timedelta(days=15)
        self._create_confirmed_plan(target, budget_amount=100000)

        pr = self._create_pr(lines=[(0, 0, {
            'product_id': self.product.id,
            'quantity': 10,
            'unit_price': 100,
            'analytic_distribution': {str(self.analytic_account.id): 100},
        })], target=target)
        pr_wizard_ctx = pr.action_request_monthly_budget_approval()['context']
        pr_wizard = self.env['monthly.budget.request.reason.wizard'].with_context(**pr_wizard_ctx).create({
            'reason': 'PR request',
        })
        pr_wizard.action_submit_request()

        pr_request = self.env['buz.monthly.budget.approval.request'].search([
            ('document_type', '=', 'pr'),
            ('ref_pr_id', '=', pr.id),
        ], limit=1)
        self.assertAlmostEqual(pr_request.amount_requested, 1000.0, places=2)

        po = self._create_po(lines=[(0, 0, {
            'product_id': self.product.id,
            'product_qty': 5,
            'price_unit': 100,
            'analytic_distribution': {str(self.analytic_account.id): 100},
        })], target=target, pr_name=pr.name)

        po._recompute_budget_approval_request()
        pr_request.invalidate_recordset(['amount_requested'])
        self.assertAlmostEqual(pr_request.amount_requested, 1000.0, places=2)

    def test_existing_pending_request_named_new_gets_sequence(self):
        target = fields.Date.today() + timedelta(days=15)
        self._create_confirmed_plan(target, budget_amount=100000)

        pr = self._create_pr(lines=[(0, 0, {
            'product_id': self.product.id,
            'quantity': 10,
            'unit_price': 100,
            'analytic_distribution': {str(self.analytic_account.id): 100},
        })], target=target)

        request = self.env['buz.monthly.budget.approval.request'].create({
            'name': 'New',
            'document_type': 'pr',
            'ref_pr_id': pr.id,
            'amount_requested': 1000.0,
            'amount_analytic': 1000.0,
            'amount_used': 0.0,
            'amount_reserved': 0.0,
            'amount_limit': 100000.0,
            'amount_overage': 0.0,
        })
        request.name = 'New'

        wizard_ctx = pr.action_request_monthly_budget_approval()['context']
        wizard = self.env['monthly.budget.request.reason.wizard'].with_context(**wizard_ctx).create({
            'reason': 'Refresh pending request',
        })
        wizard.action_submit_request()

        request.invalidate_recordset(['name'])
        self.assertNotEqual(request.name, 'New')
        self.assertTrue(request.name.startswith('AR/'))
