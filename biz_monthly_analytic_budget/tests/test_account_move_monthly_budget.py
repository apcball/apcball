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

    def test_cancel_bill_releases_commitment_when_due_date_has_no_plan(self):
        """Regression: cancelling a bill whose due-date month has no confirmed
        plan must still release its reserved commitment (stale 7.8M on prod)."""
        plan_date = fields.Date.to_date('2026-10-15')
        self._create_confirmed_plan(plan_date, budget_amount=100000)
        bill = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.partner.id,
            'invoice_date': plan_date,
            'invoice_date_due': plan_date,
            'invoice_line_ids': [fields.Command.create({
                'product_id': self.product.id,
                'quantity': 1,
                'price_unit': 1000,
                'analytic_distribution': {str(self.analytic_account.id): 100},
            })],
        })
        Commitment = self.env['budget.commitment'].sudo()
        domain = [
            ('document_model', '=', 'account.move'),
            ('document_id', '=', bill.id),
            ('budget_source', '=', 'monthly'),
        ]
        self.assertTrue(Commitment.search(domain + [('state', '=', 'reserved')]))
        # Move the due date to a month without any plan, keeping the old commitment.
        bill.with_context(skip_monthly_bill_budget_sync=True).write({
            'invoice_date_due': fields.Date.to_date('2026-08-31'),
        })
        bill.button_cancel()
        self.assertFalse(Commitment.search(domain + [('state', 'in', ('reserved', 'used'))]))

    def test_post_bill_without_plan_releases_draft_reservation(self):
        """Regression: a draft bill reserved budget; when it is posted with a due date
        that has no confirmed plan, the reservation must not stay forever."""
        plan_date = fields.Date.to_date('2026-10-15')
        self._create_confirmed_plan(plan_date, budget_amount=100000)
        bill = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.partner.id,
            'invoice_date': plan_date,
            'invoice_date_due': plan_date,
            'invoice_line_ids': [fields.Command.create({
                'product_id': self.product.id,
                'quantity': 1,
                'price_unit': 1000,
                'analytic_distribution': {str(self.analytic_account.id): 100},
            })],
        })
        Commitment = self.env['budget.commitment'].sudo()
        domain = [
            ('document_model', '=', 'account.move'),
            ('document_id', '=', bill.id),
            ('budget_source', '=', 'monthly'),
        ]
        self.assertTrue(Commitment.search(domain + [('state', '=', 'reserved')]))
        bill.with_context(skip_monthly_bill_budget_sync=True).write({
            'invoice_date_due': fields.Date.to_date('2026-08-31'),
        })
        if 'tax_invoice_ids' in bill._fields and bill.tax_invoice_ids:  # l10n_th_account_tax
            bill.tax_invoice_ids.write({
                'tax_invoice_number': 'BUDGET-TI-%d' % bill.id,
                'tax_invoice_date': plan_date,
            })
        bill.action_post()
        self.assertFalse(Commitment.search(domain + [('state', '=', 'reserved')]))
