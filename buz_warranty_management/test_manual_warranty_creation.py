#!/usr/bin/env python3
"""
Test script for manual warranty creation functionality
This script tests the new manual warranty creation workflow
"""

import os
import sys

# Add the module path to sys.path for testing
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_module_imports():
    """Test that all new modules can be imported"""
    print("Testing module imports...")
    
    try:
        # Test sale_order model import
        from models import sale_order
        print("✓ sale_order model imported successfully")
        
        # Test that SaleOrder class has the new methods
        assert hasattr(sale_order.SaleOrder, 'action_create_warranty_card')
        print("✓ action_create_warranty_card method exists")
        
        assert hasattr(sale_order.SaleOrder, 'action_view_warranty_cards')
        print("✓ action_view_warranty_cards method exists")
        
        assert hasattr(sale_order.SaleOrder, '_create_warranty_cards_from_pickings')
        print("✓ _create_warranty_cards_from_pickings method exists")
        
        return True
    except Exception as e:
        print(f"✗ Import test failed: {e}")
        return False

def test_product_template_changes():
    """Test that product template model changes are correct"""
    print("\nTesting product template changes...")
    
    try:
        from models import product_template
        
        # Check that auto_warranty field is removed
        ProductTemplate = product_template.ProductTemplate
        fields = ProductTemplate._fields
        
        assert 'auto_warranty' not in fields, "auto_warranty field should be removed"
        print("✓ auto_warranty field successfully removed")
        
        # Check that warranty_duration field still exists
        assert 'warranty_duration' in fields, "warranty_duration field should exist"
        print("✓ warranty_duration field exists")
        
        return True
    except Exception as e:
        print(f"✗ Product template test failed: {e}")
        return False

def test_stock_picking_changes():
    """Test that stock picking model changes are correct"""
    print("\nTesting stock picking changes...")
    
    try:
        from models import stock_picking
        
        # Read the file to check that automatic creation is disabled
        with open('models/stock_picking.py', 'r') as f:
            content = f.read()
            
        # Check that automatic creation is commented out
        assert '# self._create_warranty_cards()' in content, "Automatic warranty creation should be commented out"
        print("✓ Automatic warranty creation disabled in stock_picking")
        
        return True
    except Exception as e:
        print(f"✗ Stock picking test failed: {e}")
        return False

def test_manifest_changes():
    """Test that manifest file changes are correct"""
    print("\nTesting manifest changes...")
    
    try:
        import json
        
        # Read and parse manifest
        with open('__manifest__.py', 'r') as f:
            content = f.read()
            
        # Check that description is updated
        assert 'Manual warranty card creation from Sale Order' in content, "Description should mention manual creation"
        print("✓ Manifest description updated")
        
        # Check that sale_order_views.xml is included
        assert "'views/sale_order_views.xml'" in content, "sale_order_views.xml should be in data list"
        print("✓ sale_order_views.xml added to manifest")
        
        return True
    except Exception as e:
        print(f"✗ Manifest test failed: {e}")
        return False

def test_view_files():
    """Test that view files are correctly structured"""
    print("\nTesting view files...")
    
    try:
        # Test sale_order_views.xml
        with open('views/sale_order_views.xml', 'r') as f:
            content = f.read()
            
        assert 'action_create_warranty_card' in content, "Create warranty card button should be present"
        print("✓ Create warranty card button present in view")
        
        assert 'action_view_warranty_cards' in content, "View warranty cards button should be present"
        print("✓ View warranty cards button present in view")
        
        # Test product_template_views.xml
        with open('views/product_template_views.xml', 'r') as f:
            content = f.read()
            
        assert 'auto_warranty' not in content, "auto_warranty should not be in view"
        print("✓ auto_warranty removed from product template view")
        
        assert 'invisible="auto_warranty' not in content.replace(' ', ''), "invisible conditions should be removed"
        print("✓ Invisible conditions removed from warranty fields")
        
        return True
    except Exception as e:
        print(f"✗ View files test failed: {e}")
        return False

def main():
    """Run all tests"""
    print("=" * 60)
    print("Testing Manual Warranty Creation Implementation")
    print("=" * 60)
    
    tests = [
        test_module_imports,
        test_product_template_changes,
        test_stock_picking_changes,
        test_manifest_changes,
        test_view_files,
    ]
    
    results = []
    for test in tests:
        results.append(test())
    
    print("\n" + "=" * 60)
    print("Test Results Summary")
    print("=" * 60)
    
    passed = sum(results)
    total = len(results)
    
    print(f"Tests passed: {passed}/{total}")
    
    if passed == total:
        print("\n✓ All tests passed! Implementation is ready.")
        return 0
    else:
        print("\n✗ Some tests failed. Please review the implementation.")
        return 1

if __name__ == '__main__':
    sys.exit(main())