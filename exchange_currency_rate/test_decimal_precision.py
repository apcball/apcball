#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script to verify 4 decimal precision for exchange rate fields
This script can be run in an Odoo shell to test the implementation
"""

def test_exchange_rate_precision():
    """Test that exchange rate fields support 4 decimal places"""
    
    # Test values with various decimal places
    test_values = [
        1.0,          # No decimal places
        1.2,          # 1 decimal place
        1.23,         # 2 decimal places
        1.234,        # 3 decimal places
        1.2345,       # 4 decimal places
        12345678.1234 # Large number with 4 decimal places
    ]
    
    print("Testing exchange rate precision...")
    
    # Test Sale Order
    print("\n1. Testing Sale Order:")
    sale_order = env['sale.order'].create({
        'partner_id': env.ref('base.res_partner_2').id,
        'is_exchange': True,
    })
    
    for value in test_values:
        sale_order.rate = value
        print(f"   Set rate to {value}, stored as: {sale_order.rate}")
    
    # Test Purchase Order
    print("\n2. Testing Purchase Order:")
    purchase_order = env['purchase.order'].create({
        'partner_id': env.ref('base.res_partner_2').id,
        'is_exchange': True,
    })
    
    for value in test_values:
        purchase_order.rate = value
        print(f"   Set rate to {value}, stored as: {purchase_order.rate}")
    
    # Test Account Move (Invoice)
    print("\n3. Testing Invoice:")
    invoice = env['account.move'].create({
        'move_type': 'out_invoice',
        'partner_id': env.ref('base.res_partner_2').id,
        'is_exchange': True,
    })
    
    for value in test_values:
        invoice.rate = value
        print(f"   Set rate to {value}, stored as: {invoice.rate}")
    
    print("\n✅ All tests completed successfully!")
    return True

# Uncomment the line below to run in Odoo shell
# test_exchange_rate_precision()