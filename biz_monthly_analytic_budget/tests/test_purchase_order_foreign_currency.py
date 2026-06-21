# -*- coding: utf-8 -*-
from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase
from .common import BudgetTestMixin


class TestPurchaseOrderForeignCurrencyBudget(TransactionCase, BudgetTestMixin):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_budget_test_data()
        # Foreign currency with a fixed rate vs the company currency.
        cls.usd = cls.env['res.currency'].create({'name': 'USX', 'symbol': '$'})
        # rate meaning: 1 company-currency unit = 36 USX → 1 USX ≈ 36 company-currency
        cls.env['res.currency.rate'].create({
            'name': fields.Date.to_date('2026-01-01'),
            'rate': 1.0 / 36.0,
            'currency_id': cls.usd.id,
        })

    def test_usd_po_reserves_in_company_currency(self):
        """USD PO line subtotal is converted to company currency on reservation."""
        target = fields.Date.to_date('2026-01-15')
        self._create_confirmed_plan(target, budget_amount=5000)
        po = self.env['purchase.order'].create({
            'partner_id': self.partner.id,
            'currency_id': self.usd.id,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'product_qty': 1,
                'price_unit': 100.0,   # $100 → ฿3,600 at rate 36
                'analytic_distribution': {str(self.analytic_account.id): 100},
            })],
        })
        po.write({'payment_date': target, 'payment_date_manual': target})
        # create() → _reserve_monthly_budget_for_direct_rfq books the commitment
        commitment = self.env['budget.commitment'].sudo().search([
            ('document_model', '=', 'purchase.order'),
            ('document_id', '=', po.id),
            ('budget_source', '=', 'monthly'),
            ('state', '=', 'reserved'),
        ], limit=1)
        self.assertTrue(commitment,
                        'USD PO should reserve a monthly commitment')
        # 100 USX * 36 = 3600 company currency, NOT 100.
        self.assertAlmostEqual(commitment.amount, 3600.0, places=0,
                               msg='USD amount must be converted to company currency')

    def test_usd_po_triggers_warning_when_converted_over_budget(self):
        """USD PO exceeding budget (after currency conversion) shows warning."""
        target = fields.Date.to_date('2026-01-15')
        self._create_confirmed_plan(target, budget_amount=5000)
        # $200 = ฿7,200 > ฿5,000 budget → over
        po = self.env['purchase.order'].create({
            'partner_id': self.partner.id,
            'currency_id': self.usd.id,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'product_qty': 1,
                'price_unit': 200.0,
                'analytic_distribution': {str(self.analytic_account.id): 100},
            })],
        })
        po.write({'payment_date': target, 'payment_date_manual': target})
        self.assertTrue(po.budget_warning,
                        'USD PO converted over budget must set budget_warning=True')

    def test_usd_po_button_confirm_raises_when_converted_over_budget(self):
        """button_confirm raises UserError when converted USD exceeds budget."""
        target = fields.Date.to_date('2026-01-15')
        self._create_confirmed_plan(target, budget_amount=5000)
        po = self.env['purchase.order'].create({
            'partner_id': self.partner.id,
            'currency_id': self.usd.id,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'product_qty': 1,
                'price_unit': 200.0,  # $200 → ฿7,200 > ฿5,000 budget
                'analytic_distribution': {str(self.analytic_account.id): 100},
            })],
        })
        po.write({'payment_date': target, 'payment_date_manual': target})
        with self.assertRaises(UserError):
            po.button_confirm()
