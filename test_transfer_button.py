#!/usr/bin/env python3
"""
Test script to verify the transfer button action works correctly
"""

import os
import sys
import django

# Setup Django/Odoo
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'odoo.settings')
sys.path.insert(0, '/opt/instance1/odoo17')

import odoo
from odoo import api

@api.model
def test_transfer_action():
    """Test the transfer action"""
    env = api.Environment(odoo.sql_db.get_db(), 1, {})
    
    # Get a stock report record
    report = env['stock.current.report'].search([], limit=1)
    
    if not report:
        print("No stock report records found")
        return False
    
    print(f"Testing with report: {report.product_id.name} in {report.location_id.name}")
    print(f"Quantity: {report.quantity}")
    
    # Test the action
    try:
        action = report.action_transfer_single_product()
        print(f"Action returned successfully: {action}")
        
        # Verify the action structure
        if action.get('res_model') == 'stock.current.transfer.wizard':
            print("✓ Transfer action is correct!")
            return True
        else:
            print(f"✗ Unexpected res_model: {action.get('res_model')}")
            return False
            
    except Exception as e:
        print(f"✗ Error calling action_transfer_single_product: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    if test_transfer_action():
        print("\n✓ Test passed!")
        sys.exit(0)
    else:
        print("\n✗ Test failed!")
        sys.exit(1)
