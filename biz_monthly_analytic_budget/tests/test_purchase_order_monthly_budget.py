# -*- coding: utf-8 -*-
from datetime import timedelta
from odoo import fields
from odoo.tests.common import TransactionCase
from .common import BudgetTestMixin


class TestPurchaseOrderMonthlyBudget(TransactionCase, BudgetTestMixin):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_budget_test_data()

    def test_direct_rfq_reservation_skips_after_confirmation(self):
        target = fields.Date.today() + timedelta(days=15)
        plan = self._create_confirmed_plan(target, budget_amount=100000)
        po = self._create_po(target=target)
        po.write({'approval_state': 'approved'})
        po.with_context(bypass_budget_check=True).button_confirm()

        reserved_before = self.env['budget.commitment'].sudo().search_count([
            ('document_model', '=', 'purchase.order'),
            ('document_id', '=', po.id),
            ('budget_source', '=', 'monthly'),
            ('state', '=', 'reserved'),
        ])
        po._reserve_monthly_budget_for_direct_rfq()
        reserved_after = self.env['budget.commitment'].sudo().search_count([
            ('document_model', '=', 'purchase.order'),
            ('document_id', '=', po.id),
            ('budget_source', '=', 'monthly'),
            ('state', '=', 'reserved'),
        ])
        self.assertEqual(reserved_after, reserved_before)

    def test_direct_rfq_reservation_creates_commitment_before_confirmation(self):
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

    def test_po_without_analytic_skips_reservation(self):
        target = fields.Date.today() + timedelta(days=15)
        plan = self._create_confirmed_plan(target)
        product2 = self.env['product.product'].create({'name': 'No Analytic Product'})
        po = self.env['purchase.order'].create({
            'partner_id': self.partner.id,
            'order_line': [(0, 0, {
                'product_id': product2.id,
                'product_qty': 3,
                'price_unit': 100,
            })],
        })
        po.write({'payment_date': target, 'payment_date_manual': target})
        commitment = self.env['budget.commitment'].sudo().search([
            ('document_model', '=', 'purchase.order'),
            ('document_id', '=', po.id),
            ('budget_source', '=', 'monthly'),
        ])
        self.assertFalse(commitment)

    def test_confirm_with_source_pr_releases_po_own_reservation(self):
        """PO booked under its source PR identity must not keep its RFQ reservation."""
        from unittest.mock import patch
        target = fields.Date.today() + timedelta(days=15)
        self._create_confirmed_plan(target, budget_amount=100000)
        po = self._create_po(target=target)
        Commitment = self.env['budget.commitment'].sudo()
        own_domain = [
            ('document_model', '=', 'purchase.order'),
            ('document_id', '=', po.id),
            ('budget_source', '=', 'monthly'),
            ('state', '=', 'reserved'),
        ]
        self.assertTrue(Commitment.search(own_domain))
        pr_identity = ('employee.purchase.requisition', 987654)
        with patch.object(type(po), '_get_budget_document_identity', return_value=pr_identity):
            po._consume_monthly_analytic_budget()
        self.assertFalse(Commitment.search(own_domain))
        self.assertTrue(Commitment.search([
            ('document_model', '=', pr_identity[0]),
            ('document_id', '=', pr_identity[1]),
            ('state', '=', 'reserved'),
        ]))
