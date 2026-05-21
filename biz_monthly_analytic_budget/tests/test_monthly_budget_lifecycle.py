# -*- coding: utf-8 -*-
from datetime import timedelta
from odoo import fields
from odoo.tests.common import TransactionCase
from .common import BudgetTestMixin


class TestMonthlyBudgetLifecycle(TransactionCase, BudgetTestMixin):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_budget_test_data()

    def test_pr_reserve_creates_commitment(self):
        target = fields.Date.today() + timedelta(days=15)
        plan = self._create_confirmed_plan(target)
        pr = self._create_pr(target=target, state='waiting_purchase_approval')
        commitment = self.env['budget.commitment'].sudo().search([
            ('document_model', '=', 'employee.purchase.requisition'),
            ('document_id', '=', pr.id),
            ('budget_source', '=', 'monthly'),
            ('state', '=', 'reserved'),
        ])
        self.assertTrue(commitment)

    def test_pr_cancel_releases_commitment(self):
        target = fields.Date.today() + timedelta(days=15)
        plan = self._create_confirmed_plan(target)
        pr = self._create_pr(target=target, state='waiting_purchase_approval')
        pr.action_purchase_cancel()
        active = self.env['budget.commitment'].sudo().search([
            ('document_model', '=', 'employee.purchase.requisition'),
            ('document_id', '=', pr.id),
            ('budget_source', '=', 'monthly'),
            ('state', 'in', ('reserved', 'used')),
        ])
        self.assertFalse(active)

    def test_direct_rfq_reserves_budget(self):
        target = fields.Date.today() + timedelta(days=15)
        plan = self._create_confirmed_plan(target)
        po = self._create_po(target=target)
        commitment = self.env['budget.commitment'].sudo().search([
            ('document_model', '=', 'purchase.order'),
            ('document_id', '=', po.id),
            ('budget_source', '=', 'monthly'),
            ('state', '=', 'reserved'),
        ])
        self.assertTrue(commitment)

    def test_confirmed_po_preserves_reservation_for_unbilled(self):
        target = fields.Date.today() + timedelta(days=15)
        plan = self._create_confirmed_plan(target, budget_amount=100000)
        po = self._create_po(target=target)
        po.write({'approval_state': 'approved'})
        po.with_context(bypass_budget_check=True).button_confirm()
        reserved = self.env['budget.commitment'].sudo().search([
            ('document_model', '=', 'purchase.order'),
            ('document_id', '=', po.id),
            ('budget_source', '=', 'monthly'),
            ('state', '=', 'reserved'),
        ])
        self.assertTrue(reserved)

    def test_cancel_confirmed_po_releases_budget(self):
        target = fields.Date.today() + timedelta(days=15)
        plan = self._create_confirmed_plan(target, budget_amount=100000)
        po = self._create_po(target=target)
        po.write({'approval_state': 'approved'})
        po.with_context(bypass_budget_check=True).button_confirm()
        po.button_cancel()
        active = self.env['budget.commitment'].sudo().search([
            ('document_model', '=', 'purchase.order'),
            ('document_id', '=', po.id),
            ('budget_source', '=', 'monthly'),
            ('state', 'in', ('reserved', 'used')),
        ])
        self.assertFalse(active)
