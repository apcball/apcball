# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


class TestExchangeRateFeature(TransactionCase):
    
    def setUp(self):
        super(TestExchangeRateFeature, self).setUp()
        
        # Create test data
        self.company = self.env.company
        self.partner = self.env['res.partner'].create({
            'name': 'Test Vendor',
            'supplier_rank': 1,
        })
        
        # Create accounts
        self.expense_account = self.env['account.account'].search([
            ('company_id', '=', self.company.id),
            ('account_type', '=', 'expense')
        ], limit=1)
        
        self.accrual_account = self.env['account.account'].search([
            ('company_id', '=', self.company.id),
            ('account_type', '=', 'liability_current')
        ], limit=1)
        
        self.exchange_rate_diff_account = self.env['account.account'].search([
            ('company_id', '=', self.company.id),
            ('account_type', '=', 'expense')
        ], limit=1)
        
        # Create journal
        self.journal = self.env['account.journal'].create({
            'name': 'Test Journal',
            'type': 'general',
            'code': 'TEST',
            'company_id': self.company.id,
        })
        
        # Create currency (USD for testing)
        self.usd_currency = self.env.ref('base.USD')
        
        # Create product
        self.product = self.env['product.product'].create({
            'name': 'Test Product',
            'categ_id': self.env.ref('product.product_category_all').id,
            'property_account_expense_id': self.expense_account.id,
        })
        
        # Create purchase order
        self.purchase_order = self.env['purchase.order'].create({
            'partner_id': self.partner.id,
            'currency_id': self.usd_currency.id,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'product_qty': 1,
                'price_unit': 100,
                'name': 'Test Product Line',
            })],
        })
        
        # Configure advance accounting
        self.config = self.env['advance.accounting.config'].create({
            'company_id': self.company.id,
            'exchange_rate_diff_account_id': self.exchange_rate_diff_account.id,
        })
    
    def test_exchange_rate_fields_visible(self):
        """Test that exchange rate fields are visible in wizard"""
        wizard = self.env['purchase.advance.bill.wizard'].create({
            'purchase_id': self.purchase_order.id,
            'journal_id': self.journal.id,
            'accrual_account_id': self.accrual_account.id,
        })
        
        # Check that exchange rate fields are computed
        self.assertTrue(wizard.auto_exchange_rate > 0, "Auto exchange rate should be computed")
        self.assertEqual(wizard.manual_exchange_rate, wizard.auto_exchange_rate, 
                        "Manual rate should default to auto rate")
    
    def test_manual_exchange_rate_difference(self):
        """Test exchange rate difference calculation"""
        wizard = self.env['purchase.advance.bill.wizard'].create({
            'purchase_id': self.purchase_order.id,
            'journal_id': self.journal.id,
            'accrual_account_id': self.accrual_account.id,
            'use_manual_exchange_rate': True,
            'manual_exchange_rate': 35.0,  # Different from auto rate
        })
        
        # Check that exchange rate difference is calculated
        self.assertNotEqual(wizard.exchange_rate_diff_amount, 0, 
                           "Exchange rate difference should be calculated when using manual rate")
    
    def test_preview_includes_exchange_rate_diff(self):
        """Test that preview includes exchange rate difference line"""
        wizard = self.env['purchase.advance.bill.wizard'].create({
            'purchase_id': self.purchase_order.id,
            'journal_id': self.journal.id,
            'accrual_account_id': self.accrual_account.id,
            'use_manual_exchange_rate': True,
            'manual_exchange_rate': 35.0,
        })
        
        # Check preview lines
        preview_lines = wizard.preview_line_ids
        exchange_rate_diff_lines = preview_lines.filtered(
            lambda line: 'Exchange Rate Difference' in line.name
        )
        
        if wizard.exchange_rate_diff_amount != 0:
            self.assertTrue(len(exchange_rate_diff_lines) > 0, 
                           "Preview should include exchange rate difference line")
    
    def test_journal_entry_creation_with_exchange_rate_diff(self):
        """Test that journal entry includes exchange rate difference"""
        wizard = self.env['purchase.advance.bill.wizard'].create({
            'purchase_id': self.purchase_order.id,
            'journal_id': self.journal.id,
            'accrual_account_id': self.accrual_account.id,
            'use_manual_exchange_rate': True,
            'manual_exchange_rate': 35.0,
        })
        
        # Create journal entry
        action = wizard.action_create()
        move_id = action['res_id']
        move = self.env['account.move'].browse(move_id)
        
        # Check that exchange rate difference line exists if applicable
        if wizard.exchange_rate_diff_amount != 0:
            exchange_rate_diff_lines = move.line_ids.filtered(
                lambda line: 'Exchange Rate Difference' in line.name
            )
            self.assertTrue(len(exchange_rate_diff_lines) > 0, 
                           "Journal entry should include exchange rate difference line")
    
    def test_config_model_access(self):
        """Test that configuration model is accessible"""
        config = self.env['advance.accounting.config'].get_config()
        self.assertEqual(config.company_id, self.company, 
                        "Config should be for current company")
        self.assertEqual(config.exchange_rate_diff_account_id, self.exchange_rate_diff_account,
                        "Config should have correct exchange rate diff account")