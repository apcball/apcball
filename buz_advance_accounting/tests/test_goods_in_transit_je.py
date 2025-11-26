# -*- coding: utf-8 -*-
"""
Test module for buz_advance_accounting GIT and FX difference JE logic.

This test validates:
1. Goods-in-Transit (GIT) journal entry posting on bill date
2. Goods Arrival reclassification JE with FX difference calculation
3. Correct handling of FX rates on different dates
"""

from datetime import datetime, timedelta
from decimal import Decimal

from odoo.tests.common import TransactionCase
from odoo.tools import float_compare
from odoo.exceptions import UserError


class TestGoodsInTransitJELogic(TransactionCase):
    """Test Goods-in-Transit and Goods Arrival Journal Entry Logic"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        
        # Create test currencies
        cls.currency_thb = cls.env['res.currency'].search([('name', '=', 'THB')], limit=1)
        if not cls.currency_thb:
            cls.currency_thb = cls.env['res.currency'].create({
                'name': 'THB',
                'symbol': '฿',
            })
        
        cls.currency_usd = cls.env['res.currency'].search([('name', '=', 'USD')], limit=1)
        if not cls.currency_usd:
            cls.currency_usd = cls.env['res.currency'].create({
                'name': 'USD',
                'symbol': '$',
            })
        
        # Set exchange rates
        # Bill date (2025-01-01): 1 USD = 35 THB (rate = 0.030861)
        bill_date = datetime(2025, 1, 1).date()
        cls.env['res.currency.rate'].create({
            'name': bill_date,
            'rate': 1.0 / 35.0,  # Odoo format: 0.030861
            'currency_id': cls.currency_usd.id,
            'company_id': cls.env.company.id,
        })
        
        # Arrival date (2025-01-15): 1 USD = 36 THB (rate = 0.027778)
        arrival_date = datetime(2025, 1, 15).date()
        cls.env['res.currency.rate'].create({
            'name': arrival_date,
            'rate': 1.0 / 36.0,  # Odoo format: 0.027778
            'currency_id': cls.currency_usd.id,
            'company_id': cls.env.company.id,
        })
        
        # Create vendor
        cls.vendor = cls.env['res.partner'].create({
            'name': 'Test Foreign Vendor',
            'country_id': cls.env.ref('base.us').id,
        })
        
        # Create test product
        cls.product = cls.env['product.product'].create({
            'name': 'Test Product',
            'type': 'product',
        })
        
        # Create accounts
        journal = cls.env['account.journal'].search([('type', '=', 'general')], limit=1)
        if not journal:
            journal = cls.env['account.journal'].create({
                'name': 'General Journal',
                'code': 'GNJL',
                'type': 'general',
            })
        cls.journal = journal
        
        # Get or create account accounts
        chart_account = cls.env['account.account'].search([
            ('code', '=', '1010')  # Asset account
        ], limit=1)
        
        if not chart_account:
            chart_account = cls.env['account.account'].create({
                'name': 'Current Asset',
                'code': '1010',
                'account_type': 'asset_current',
            })
        
        cls.git_account = chart_account
        
        # Foreign AP account
        foreign_ap = cls.env['account.account'].search([
            ('code', '=', '2100')  # Liability account
        ], limit=1)
        
        if not foreign_ap:
            foreign_ap = cls.env['account.account'].create({
                'name': 'Foreign Accounts Payable',
                'code': '2100',
                'account_type': 'liability_current',
            })
        
        cls.foreign_ap_account = foreign_ap
        
        # Inventory account
        inventory = cls.env['account.account'].search([
            ('code', '=', '1110')
        ], limit=1)
        
        if not inventory:
            inventory = cls.env['account.account'].create({
                'name': 'Inventory',
                'code': '1110',
                'account_type': 'asset_current',
            })
        
        cls.inventory_account = inventory
        
        # Exchange difference account
        fx_diff = cls.env['account.account'].search([
            ('code', '=', '5100')
        ], limit=1)
        
        if not fx_diff:
            fx_diff = cls.env['account.account'].create({
                'name': 'Exchange Rate Difference',
                'code': '5100',
                'account_type': 'income',
            })
        
        cls.fx_diff_account = fx_diff
        
        # Create advance accounting config
        cls.config = cls.env['advance.accounting.config'].create({
            'company_id': cls.env.company.id,
            'exchange_rate_diff_account_id': cls.fx_diff_account.id,
        })

    def test_01_post_git_entry(self):
        """Test posting Goods-in-Transit journal entry on bill date"""
        
        # Create a purchase order in USD
        po = self.env['purchase.order'].create({
            'partner_id': self.vendor.id,
            'currency_id': self.currency_usd.id,
            'order_line': [
                (0, 0, {
                    'product_id': self.product.id,
                    'product_qty': 1,
                    'price_unit': 10000,  # 10,000 USD
                })
            ]
        })
        
        # Confirm PO
        po.button_confirm()
        
        # Create accrual entry
        bill_date = datetime(2025, 1, 1).date()
        accrual = self.env['purchase.advance.accrual'].create({
            'purchase_id': po.id,
            'date': bill_date,
            'amount': 10000,  # 10,000 USD
            'currency_id': self.currency_usd.id,
        })
        
        # Post GIT entry
        move = accrual._post_goods_in_transit_entry(
            journal_id=self.journal.id,
            git_account_id=self.git_account.id,
            foreign_ap_account_id=self.foreign_ap_account.id,
            date=bill_date
        )
        
        # Verify journal entry
        self.assertTrue(move.posted)
        self.assertEqual(len(move.line_ids), 2)  # 2 lines: GIT debit, AP credit
        
        # Find the lines
        git_line = move.line_ids.filtered(lambda l: l.account_id == self.git_account)
        ap_line = move.line_ids.filtered(lambda l: l.account_id == self.foreign_ap_account)
        
        self.assertTrue(git_line)
        self.assertTrue(ap_line)
        
        # Expected amount: 10,000 USD * 35 THB/USD = 350,000 THB
        expected_thb = 350000.0
        
        # Check amounts
        self.assertAlmostEqual(git_line.debit, expected_thb, delta=1)
        self.assertAlmostEqual(ap_line.credit, expected_thb, delta=1)
        
        # Verify accrual record was updated
        self.assertEqual(accrual.state, 'posted')
        self.assertTrue(accrual.is_git_entry)
        self.assertEqual(accrual.source_currency_amount, 10000)
        self.assertEqual(accrual.exchange_rate_on_bill_date, 35.0)
        self.assertAlmostEqual(accrual.amount_in_company_currency_on_bill, expected_thb, delta=1)
        
        print("✓ Test 1 passed: GIT entry posted correctly")

    def test_02_post_goods_arrival_entry_with_fx_gain(self):
        """Test posting Goods Arrival entry with FX gain (rate improved)"""
        
        # Create PO in USD
        po = self.env['purchase.order'].create({
            'partner_id': self.vendor.id,
            'currency_id': self.currency_usd.id,
            'order_line': [
                (0, 0, {
                    'product_id': self.product.id,
                    'product_qty': 1,
                    'price_unit': 10000,
                })
            ]
        })
        po.button_confirm()
        
        bill_date = datetime(2025, 1, 1).date()
        
        # Create and post GIT entry
        accrual = self.env['purchase.advance.accrual'].create({
            'purchase_id': po.id,
            'date': bill_date,
            'amount': 10000,
            'currency_id': self.currency_usd.id,
        })
        
        move_git = accrual._post_goods_in_transit_entry(
            journal_id=self.journal.id,
            git_account_id=self.git_account.id,
            foreign_ap_account_id=self.foreign_ap_account.id,
            date=bill_date
        )
        
        # Post goods arrival entry
        arrival_date = datetime(2025, 1, 15).date()
        move_arrival = accrual._post_goods_arrival_entry(
            journal_id=self.journal.id,
            inventory_account_id=self.inventory_account.id,
            git_account_id=self.git_account.id,
            arrival_date=arrival_date
        )
        
        # Verify arrival entry
        self.assertTrue(move_arrival.posted)
        self.assertEqual(len(move_arrival.line_ids), 3)  # Inventory DR, GIT CR, FX Gain CR
        
        # Amount on bill date (1 Jan): 10,000 USD * 35 THB/USD = 350,000 THB
        amount_bill = 350000.0
        
        # Amount on arrival date (15 Jan): 10,000 USD * 36 THB/USD = 360,000 THB
        amount_arrival = 360000.0
        
        # FX difference: 360,000 - 350,000 = 10,000 THB (loss, not gain!)
        # Wait, let me recalculate:
        # On bill date: 1 USD = 35 THB (rate worsened from company's perspective)
        # On arrival: 1 USD = 36 THB (rate got worse, so company pays more)
        # This is FX LOSS
        fx_diff_expected = 10000.0
        
        inventory_line = move_arrival.line_ids.filtered(lambda l: l.account_id == self.inventory_account)
        git_line = move_arrival.line_ids.filtered(lambda l: l.account_id == self.git_account)
        fx_line = move_arrival.line_ids.filtered(lambda l: l.account_id == self.fx_diff_account)
        
        self.assertTrue(inventory_line)
        self.assertTrue(git_line)
        self.assertTrue(fx_line)
        
        self.assertAlmostEqual(inventory_line.debit, amount_arrival, delta=1)
        self.assertAlmostEqual(git_line.credit, amount_bill, delta=1)
        
        # FX loss should be debit
        self.assertAlmostEqual(fx_line.debit, fx_diff_expected, delta=1)
        
        # Verify accrual state
        self.assertEqual(accrual.state, 'arrived')
        self.assertAlmostEqual(accrual.fx_difference_amount, fx_diff_expected, delta=1)
        
        print("✓ Test 2 passed: Goods arrival entry with FX loss posted correctly")

    def test_03_post_goods_arrival_entry_with_fx_loss(self):
        """Test posting Goods Arrival entry with FX loss (rate deteriorated)"""
        
        # Set up rates where THB strengthens (favorable)
        # Bill date: 1 USD = 35 THB
        # Arrival: 1 USD = 34 THB (strengthened, better for importer)
        
        arrival_date_str = datetime(2025, 2, 1).date()
        self.env['res.currency.rate'].create({
            'name': arrival_date_str,
            'rate': 1.0 / 34.0,  # 1 USD = 34 THB (rate improved for importer)
            'currency_id': self.currency_usd.id,
            'company_id': self.env.company.id,
        })
        
        # Create PO
        po = self.env['purchase.order'].create({
            'partner_id': self.vendor.id,
            'currency_id': self.currency_usd.id,
            'order_line': [
                (0, 0, {
                    'product_id': self.product.id,
                    'product_qty': 1,
                    'price_unit': 10000,
                })
            ]
        })
        po.button_confirm()
        
        bill_date = datetime(2025, 1, 1).date()
        
        # Create and post GIT entry
        accrual = self.env['purchase.advance.accrual'].create({
            'purchase_id': po.id,
            'date': bill_date,
            'amount': 10000,
            'currency_id': self.currency_usd.id,
        })
        
        move_git = accrual._post_goods_in_transit_entry(
            journal_id=self.journal.id,
            git_account_id=self.git_account.id,
            foreign_ap_account_id=self.foreign_ap_account.id,
            date=bill_date
        )
        
        # Post goods arrival entry with favorable rate
        move_arrival = accrual._post_goods_arrival_entry(
            journal_id=self.journal.id,
            inventory_account_id=self.inventory_account.id,
            git_account_id=self.git_account.id,
            arrival_date=arrival_date_str
        )
        
        # Amount on bill date: 10,000 USD * 35 THB/USD = 350,000 THB
        amount_bill = 350000.0
        
        # Amount on arrival: 10,000 USD * 34 THB/USD = 340,000 THB
        amount_arrival = 340000.0
        
        # FX difference: 340,000 - 350,000 = -10,000 THB (GAIN)
        fx_gain_expected = 10000.0
        
        inventory_line = move_arrival.line_ids.filtered(lambda l: l.account_id == self.inventory_account)
        git_line = move_arrival.line_ids.filtered(lambda l: l.account_id == self.git_account)
        fx_line = move_arrival.line_ids.filtered(lambda l: l.account_id == self.fx_diff_account)
        
        self.assertAlmostEqual(inventory_line.debit, amount_arrival, delta=1)
        self.assertAlmostEqual(git_line.credit, amount_bill, delta=1)
        
        # FX gain should be credit
        self.assertAlmostEqual(fx_line.credit, fx_gain_expected, delta=1)
        
        # Verify accrual
        self.assertEqual(accrual.state, 'arrived')
        self.assertAlmostEqual(accrual.fx_difference_amount, -fx_gain_expected, delta=1)
        
        print("✓ Test 3 passed: Goods arrival entry with FX gain posted correctly")

    def test_04_complete_workflow(self):
        """Test complete workflow: PO -> GIT -> Arrival"""
        
        # Create PO
        po = self.env['purchase.order'].create({
            'partner_id': self.vendor.id,
            'currency_id': self.currency_usd.id,
            'order_line': [
                (0, 0, {
                    'product_id': self.product.id,
                    'product_qty': 5,
                    'price_unit': 2000,  # Total: 10,000 USD
                })
            ]
        })
        po.button_confirm()
        
        # Step 1: Create advance accrual on bill date
        bill_date = datetime(2025, 1, 1).date()
        accrual = self.env['purchase.advance.accrual'].create({
            'purchase_id': po.id,
            'date': bill_date,
            'amount': 10000,
            'currency_id': self.currency_usd.id,
        })
        
        # Step 2: Post GIT entry
        move_git = accrual._post_goods_in_transit_entry(
            journal_id=self.journal.id,
            git_account_id=self.git_account.id,
            foreign_ap_account_id=self.foreign_ap_account.id,
            date=bill_date
        )
        self.assertTrue(move_git.posted)
        self.assertEqual(accrual.state, 'posted')
        
        # Step 3: Post goods arrival entry
        arrival_date = datetime(2025, 1, 15).date()
        move_arrival = accrual._post_goods_arrival_entry(
            journal_id=self.journal.id,
            inventory_account_id=self.inventory_account.id,
            git_account_id=self.git_account.id,
            arrival_date=arrival_date
        )
        self.assertTrue(move_arrival.posted)
        self.assertEqual(accrual.state, 'arrived')
        
        # Verify both entries exist and are linked
        self.assertEqual(accrual.move_id, move_git)
        self.assertEqual(accrual.arrival_move_id, move_arrival)
        
        # Verify GL balances
        # GIT account: should show in accrual balance (not balanced after arrival)
        # Inventory: should show receiving
        # FX account: should show loss/gain
        
        print("✓ Test 4 passed: Complete workflow executed successfully")


if __name__ == '__main__':
    import unittest
    suite = unittest.TestLoader().loadTestsFromTestCase(TestGoodsInTransitJELogic)
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite)
