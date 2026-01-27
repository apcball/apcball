#!/usr/bin/env python3
"""
Validation script for manual warranty creation implementation
This script validates file structure and content without requiring Odoo
"""

import os
import re

def check_file_exists(filepath):
    """Check if file exists"""
    if os.path.exists(filepath):
        print(f"✓ {filepath} exists")
        return True
    else:
        print(f"✗ {filepath} missing")
        return False

def check_file_content(filepath, patterns, description):
    """Check if file contains required patterns"""
    if not os.path.exists(filepath):
        print(f"✗ {filepath} missing")
        return False
        
    with open(filepath, 'r') as f:
        content = f.read()
    
    all_found = True
    for pattern in patterns:
        if re.search(pattern, content, re.MULTILINE | re.DOTALL):
            print(f"  ✓ Found: {pattern}")
        else:
            print(f"  ✗ Missing: {pattern}")
            all_found = False
    
    if all_found:
        print(f"✓ {description}")
    else:
        print(f"✗ {description} - some patterns missing")
    
    return all_found

def validate_new_files():
    """Validate that new files are created correctly"""
    print("=" * 60)
    print("Validating New Files")
    print("=" * 60)
    
    results = []
    
    # Check sale_order.py
    patterns = [
        r'class SaleOrder\(models\.Model\):',
        r'_inherit = \'sale\.order\'',
        r'def action_create_warranty_card\(self\):',
        r'def _create_warranty_cards_from_pickings\(self, pickings\):',
        r'def action_view_warranty_cards\(self\):'
    ]
    results.append(check_file_content('models/sale_order.py', patterns, "Sale Order Model"))
    
    # Check sale_order_views.xml
    patterns = [
        r'<record id="view_sale_order_form_inherit_warranty"',
        r'name="action_create_warranty_card"',
        r'string="Create Warranty Card"',
        r'name="action_view_warranty_cards"',
        r'string="Warranty Cards"'
    ]
    results.append(check_file_content('views/sale_order_views.xml', patterns, "Sale Order Views"))
    
    return all(results)

def validate_modified_files():
    """Validate that modified files are correct"""
    print("\n" + "=" * 60)
    print("Validating Modified Files")
    print("=" * 60)
    
    results = []
    
    # Check product_template.py
    with open('models/product_template.py', 'r') as f:
        content = f.read()
    
    if 'auto_warranty' not in content:
        print("✓ auto_warranty field removed from product_template.py")
        results.append(True)
    else:
        print("✗ auto_warranty field still present in product_template.py")
        results.append(False)
    
    # Check product_template_views.xml
    patterns = [
        r'<label for="warranty_duration" string="Warranty Period"/>',
        r'<field name="warranty_condition" nolabel="1"/>'
    ]
    results.append(check_file_content('views/product_template_views.xml', patterns, "Product Template Views"))
    
    # Check stock_picking.py
    with open('models/stock_picking.py', 'r') as f:
        content = f.read()
    
    if '# self._create_warranty_cards()' in content:
        print("✓ Automatic warranty creation disabled in stock_picking.py")
        results.append(True)
    else:
        print("✗ Automatic warranty creation not properly disabled")
        results.append(False)
    
    # Check __manifest__.py
    patterns = [
        r'Manual warranty card creation from Sale Order',
        r'\'views/sale_order_views\.xml\''
    ]
    results.append(check_file_content('__manifest__.py', patterns, "Manifest File"))
    
    # Check models/__init__.py
    with open('models/__init__.py', 'r') as f:
        content = f.read()
    
    if 'from . import sale_order' in content:
        print("✓ sale_order import added to models/__init__.py")
        results.append(True)
    else:
        print("✗ sale_order import missing from models/__init__.py")
        results.append(False)
    
    return all(results)

def validate_file_structure():
    """Validate overall file structure"""
    print("\n" + "=" * 60)
    print("Validating File Structure")
    print("=" * 60)
    
    required_files = [
        'models/sale_order.py',
        'views/sale_order_views.xml',
        'models/product_template.py',
        'views/product_template_views.xml',
        'models/stock_picking.py',
        '__manifest__.py',
        'models/__init__.py'
    ]
    
    results = []
    for file in required_files:
        results.append(check_file_exists(file))
    
    return all(results)

def main():
    """Run all validations"""
    print("Manual Warranty Creation Implementation Validation")
    print("=" * 60)
    
    # Change to module directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    validations = [
        validate_file_structure,
        validate_new_files,
        validate_modified_files,
    ]
    
    results = []
    for validation in validations:
        results.append(validation())
    
    print("\n" + "=" * 60)
    print("Validation Summary")
    print("=" * 60)
    
    passed = sum(results)
    total = len(results)
    
    print(f"Validations passed: {passed}/{total}")
    
    if passed == total:
        print("\n✓ All validations passed! Implementation is correct.")
        print("\nNext steps:")
        print("1. Install/upgrade the module in Odoo")
        print("2. Test the manual warranty creation workflow")
        print("3. Verify that warranty cards are created from Sale Order")
        print("4. Confirm that automatic creation is disabled")
        return 0
    else:
        print("\n✗ Some validations failed. Please review the implementation.")
        return 1

if __name__ == '__main__':
    exit(main())