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

    def test_pr_payment_date_change_moves_commitment_to_new_plan_month(self):
        target_month1 = fields.Date.today() + timedelta(days=15)
        target_month2 = target_month1 + timedelta(days=31)
        plan1 = self._create_confirmed_plan(target_month1)
        plan2 = self._create_confirmed_plan(target_month2)
        pr = self._create_pr(target=target_month1, state='waiting_purchase_approval')

        commitment = self.env['budget.commitment'].sudo().search([
            ('document_model', '=', 'employee.purchase.requisition'),
            ('document_id', '=', pr.id),
            ('budget_source', '=', 'monthly'),
            ('state', '=', 'reserved'),
        ])
        self.assertTrue(commitment)
        self.assertEqual(commitment.date, target_month1)

        pr.write({'payment_date': target_month2, 'payment_date_manual': target_month2})
        commitment.invalidate_recordset()
        self.assertEqual(commitment.date, target_month2)

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

    # ------------------------------------------------------------------
    # PR commitment of a PR whose PO(s) are confirmed = their UNBILLED amount
    # ------------------------------------------------------------------
    def _pr_line(self, qty, price):
        return (0, 0, {
            'product_id': self.product.id,
            'quantity': qty,
            'unit_price': price,
            'analytic_distribution': {str(self.analytic_account.id): 100},
        })

    def _po_line(self, qty, price):
        return (0, 0, {
            'product_id': self.product.id,
            'product_qty': qty,
            'price_unit': price,
            'analytic_distribution': {str(self.analytic_account.id): 100},
        })

    def _pr_commitments(self, pr):
        return self.env['budget.commitment'].sudo().search([
            ('document_model', '=', 'employee.purchase.requisition'),
            ('document_id', '=', pr.id),
            ('analytic_account_id', '=', self.analytic_account.id),
            ('budget_source', '=', 'monthly'),
            ('state', '=', 'reserved'),
        ])

    def _confirmed_po(self, pr, qty, price, target):
        po = self._create_po(lines=[self._po_line(qty, price)], target=target, pr_name=pr.name)
        po.write({'approval_state': 'approved'})
        po.with_context(bypass_budget_check=True).button_confirm()
        return po

    def _draft_bill(self, po, qty, price):
        return self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.partner.id,
            'invoice_date': po.payment_date,
            'invoice_date_due': po.payment_date,
            'invoice_line_ids': [(0, 0, {
                'product_id': self.product.id,
                'quantity': qty,
                'price_unit': price,
                'purchase_line_id': po.order_line[0].id,
                'analytic_distribution': {str(self.analytic_account.id): 100},
            })],
        })

    def test_pr_reserve_after_po_confirm_keeps_unbilled_amount(self):
        """Regression: re-reserving the PR (edit / payment_date sync) after its PO is
        confirmed must not push the commitment back to the full PR amount."""
        target = fields.Date.today() + timedelta(days=15)
        self._create_confirmed_plan(target, budget_amount=1000000)
        pr = self._create_pr(lines=[self._pr_line(10, 100)], target=target,
                             state='waiting_purchase_approval')
        po = self._confirmed_po(pr, 10, 100, target)
        self._draft_bill(po, 4, 100)
        commitment = self._pr_commitments(pr)
        self.assertEqual(len(commitment), 1)
        self.assertAlmostEqual(commitment.amount, 600.0, places=2)

        # checked right after the re-reserve: a payment_date write would also sync to the
        # POs and recompute the commitment, hiding the overwrite
        pr._reserve_monthly_analytic_budget()
        commitment.invalidate_recordset()
        self.assertAlmostEqual(self._pr_commitments(pr).amount, 600.0, places=2)

    def test_pr_with_two_confirmed_pos_books_sum_of_unbilled(self):
        """Two POs of one PR share the PR commitment: it holds the SUM of their unbilled
        amounts, not the amount of the last PO written."""
        target = fields.Date.today() + timedelta(days=15)
        self._create_confirmed_plan(target, budget_amount=1000000)
        pr = self._create_pr(lines=[self._pr_line(10, 100)], target=target,
                             state='waiting_purchase_approval')
        po1 = self._confirmed_po(pr, 6, 100, target)
        self._confirmed_po(pr, 4, 100, target)
        self.assertAlmostEqual(self._pr_commitments(pr).amount, 1000.0, places=2)

        self._draft_bill(po1, 2, 100)
        self.assertAlmostEqual(self._pr_commitments(pr).amount, 800.0, places=2)
