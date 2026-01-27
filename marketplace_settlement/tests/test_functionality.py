#!/usr/bin/env python3
"""
Test script for marketplace settlement module functionality
This script demonstrates how the module works and can be used for testing
"""

import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def test_marketplace_settlement(env):
    """Test the marketplace settlement functionality"""
    
    # Test 1: Create a sale order with trade channel
    _logger.info("=== Test 1: Creating sale order with trade channel ===")
    
    # Find or create a customer
    partner = env['res.partner'].search([('name', 'ilike', 'shopee')], limit=1)
    if not partner:
        partner = env['res.partner'].create({
            'name': 'Test Customer (Shopee)',
            'customer_rank': 1,
        })
    
    # Find or create a product
    product = env['product.product'].search([('sale_ok', '=', True)], limit=1)
    if not product:
        product = env['product.product'].create({
            'name': 'Test Product',
            'type': 'consu',
            'list_price': 100.0,
        })
    
    # Create sale order
    sale_order = env['sale.order'].create({
        'partner_id': partner.id,
        'trade_channel': 'shopee',
        'order_line': [(0, 0, {
            'product_id': product.id,
            'product_uom_qty': 2,
            'price_unit': 100.0,
        })],
    })
    
    _logger.info(f"Created sale order: {sale_order.name} with trade channel: {sale_order.trade_channel}")
    
    # Confirm the sale order
    sale_order.action_confirm()
    _logger.info(f"Confirmed sale order: {sale_order.name}")
    
    # Test 2: Create invoice and verify trade channel inheritance
    _logger.info("=== Test 2: Creating invoice from sale order ===")
    
    # Create invoice
    invoice = sale_order._create_invoices()
    _logger.info(f"Created invoice: {invoice.name} with trade channel: {invoice.trade_channel}")
    
    # Post the invoice
    invoice.action_post()
    _logger.info(f"Posted invoice: {invoice.name}")
    
    # Test 3: Test wizard functionality
    _logger.info("=== Test 3: Testing settlement wizard ===")
    
    # Find or create marketplace partner
    marketplace_partner = env['res.partner'].search([('name', 'ilike', 'shopee marketplace')], limit=1)
    if not marketplace_partner:
        marketplace_partner = env['res.partner'].create({
            'name': 'Shopee Marketplace',
            'customer_rank': 1,
            'is_company': True,
        })
    
    # Find a journal
    journal = env['account.journal'].search([('type', '=', 'general')], limit=1)
    if not journal:
        journal = env['account.journal'].search([('type', '=', 'sale')], limit=1)
    
    # Create wizard
    wizard = env['marketplace.settlement.wizard'].create({
        'name': 'TEST-SHOPEE-001',
        'trade_channel': 'shopee',
        'marketplace_partner_id': marketplace_partner.id,
        'journal_id': journal.id,
        'date': env.context.get('today', '2024-01-01'),
        'auto_filter': True,
    })
    
    _logger.info(f"Created wizard with trade channel: {wizard.trade_channel}")
    _logger.info(f"Auto-filtered invoices count: {wizard.invoice_count}")
    _logger.info(f"Total amount: {wizard.total_amount}")
    
    # Test the onchange method
    wizard._onchange_trade_channel()
    _logger.info(f"After onchange - Invoice count: {wizard.invoice_count}")
    
    # List the invoices found
    for invoice in wizard.invoice_ids:
        _logger.info(f"Found invoice: {invoice.name}, Amount: {invoice.amount_residual}, Trade Channel: {invoice.trade_channel}")
    
    # Test 4: Create settlement if invoices found
    if wizard.invoice_ids:
        _logger.info("=== Test 4: Creating settlement ===")
        
        try:
            result = wizard.action_create()
            _logger.info(f"Settlement creation result: {result}")
            
            # Find the created settlement
            settlement = env['marketplace.settlement'].search([('name', '=', wizard.name)], limit=1)
            if settlement:
                _logger.info(f"Created settlement: {settlement.name}")
                _logger.info(f"Settlement state: {settlement.state}")
                _logger.info(f"Settlement move: {settlement.move_id.name if settlement.move_id else 'None'}")
            
        except Exception as e:
            _logger.error(f"Error creating settlement: {e}")
    else:
        _logger.info("No invoices found for settlement")
    
    _logger.info("=== Test completed ===")


def run_tests():
    """Run all tests"""
    _logger.info("Starting marketplace settlement tests...")
    
    # Get database registry and cursor
    import odoo
    from odoo.modules.registry import Registry
    
    db_name = 'your_database_name'  # Replace with your database name
    
    registry = Registry(db_name)
    with registry.cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {})
        try:
            test_marketplace_settlement(env)
            cr.commit()
        except Exception as e:
            _logger.error(f"Test failed: {e}")
            cr.rollback()
            raise


if __name__ == '__main__':
    # This script should be run within Odoo environment
    # You can also run tests manually through Odoo shell:
    # $ odoo-bin shell -d your_database --addons-path=/path/to/addons
    # >>> exec(open('/path/to/this/script.py').read())
    
    print("This script should be run within Odoo environment")
    print("Example usage in Odoo shell:")
    print("exec(open('/path/to/marketplace_settlement/tests/test_functionality.py').read())")
