#!/usr/bin/env python3
"""
Check if the module changes are active by examining the current loaded module
"""

import sys
import os

# Add the Odoo path
sys.path.append('/opt/instance1/odoo17')

try:
    # Try to check if we can access the warranty card model
    # This will help us understand if the module is properly loaded
    
    print("=== Module Status Check ===")
    print("Checking if buz_warranty_management module is properly installed...")
    
    # Check if the module directory exists
    module_path = '/opt/instance1/odoo17/custom-addons/buz_warranty_management'
    if os.path.exists(module_path):
        print(f"✓ Module directory exists: {module_path}")
    else:
        print(f"✗ Module directory not found: {module_path}")
    
    # Check if the warranty_card.py file exists
    warranty_card_path = os.path.join(module_path, 'models', 'warranty_card.py')
    if os.path.exists(warranty_card_path):
        print(f"✓ warranty_card.py exists: {warranty_card_path}")
        
        # Read the file and check for @api.model decorators
        with open(warranty_card_path, 'r') as f:
            content = f.read()
        
        api_model_count = content.count('@api.model')
        print(f"✓ Found {api_model_count} @api.model decorators in file")
        
        # Check for the specific search methods
        search_methods = ['_search_claim_count', '_search_days_remaining', '_search_days_since_expiry', '_search_last_claim_date']
        for method in search_methods:
            if f'@api.model\n    def {method}' in content:
                print(f"✓ {method}: Has @api.model decorator")
            elif f'def {method}' in content:
                print(f"⚠ {method}: Method exists but may be missing @api.model decorator")
            else:
                print(f"✗ {method}: Method not found")
    else:
        print(f"✗ warranty_card.py not found: {warranty_card_path}")
    
    print("\n=== Recommendation ===")
    print("If the @api.model decorators are present but error still occurs:")
    print("1. The Odoo server needs to be restarted")
    print("2. Or the module needs to be upgraded through Odoo interface")
    print("3. Check if there are any cached .pyc files that need to be cleared")
    
except Exception as e:
    print(f"Error during check: {e}")
    import traceback
    traceback.print_exc()