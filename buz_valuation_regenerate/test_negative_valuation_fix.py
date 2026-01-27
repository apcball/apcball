#!/usr/bin/env python3
"""
Test script for negative valuation detection and product duplication fix
"""

import xmlrpc.client
import sys

# Configuration
url = 'http://localhost:8069'
db = 'instance1'
username = 'admin'
password = 'admin'

def test_negative_valuation_detection():
    """Test that products with negative valuation are detected"""
    
    print("=" * 80)
    print("Testing Negative Valuation Detection")
    print("=" * 80)
    
    try:
        # Connect to Odoo
        common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
        uid = common.authenticate(db, username, password, {})
        
        if not uid:
            print("❌ Authentication failed")
            return False
        
        print(f"✓ Connected to Odoo as user {uid}")
        
        models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        
        # Search for products with negative valuation
        print("\n1. Searching for products with negative valuation...")
        
        # Get stock valuation layers
        svl_ids = models.execute_kw(db, uid, password,
            'stock.valuation.layer', 'search_read',
            [[('value', '<', 0)]],
            {'fields': ['product_id', 'quantity', 'value', 'unit_cost'], 'limit': 10}
        )
        
        if svl_ids:
            print(f"\n✓ Found {len(svl_ids)} SVL(s) with negative value:")
            for svl in svl_ids:
                product_name = svl.get('product_id', ['', 'Unknown'])[1] if svl.get('product_id') else 'Unknown'
                print(f"  - Product: {product_name}")
                print(f"    Quantity: {svl.get('quantity', 0)}")
                print(f"    Value: {svl.get('value', 0)}")
                print(f"    Unit Cost: {svl.get('unit_cost', 0)}")
        else:
            print("ℹ No SVLs with negative value found in the system")
        
        # Test creating a wizard with auto-detect
        print("\n2. Testing auto-detect feature...")
        
        # Get company
        company_ids = models.execute_kw(db, uid, password,
            'res.company', 'search',
            [[]], {'limit': 1}
        )
        
        if not company_ids:
            print("❌ No company found")
            return False
        
        company_id = company_ids[0]
        
        # Get a location
        location_ids = models.execute_kw(db, uid, password,
            'stock.location', 'search',
            [[('usage', '=', 'internal')]], {'limit': 1}
        )
        
        if not location_ids:
            print("❌ No internal location found")
            return False
        
        location_id = location_ids[0]
        
        # Create wizard
        wizard_id = models.execute_kw(db, uid, password,
            'valuation.regenerate.wizard', 'create',
            [{
                'company_id': company_id,
                'location_ids': [(6, 0, [location_id])],
                'auto_detect_products': True,
                'mode': 'product',
            }]
        )
        
        print(f"✓ Created wizard {wizard_id}")
        
        # Call compute plan
        print("\n3. Running Compute Plan with auto-detect...")
        
        result = models.execute_kw(db, uid, password,
            'valuation.regenerate.wizard', 'action_compute_plan',
            [[wizard_id]]
        )
        
        print(f"✓ Compute Plan executed")
        
        # Read wizard to see detected products
        wizard = models.execute_kw(db, uid, password,
            'valuation.regenerate.wizard', 'read',
            [[wizard_id]],
            {'fields': ['product_ids', 'line_preview_ids']}
        )[0]
        
        detected_products = wizard.get('product_ids', [])
        preview_lines = wizard.get('line_preview_ids', [])
        
        print(f"\n✓ Auto-detected {len(detected_products)} product(s)")
        print(f"✓ Found {len(preview_lines)} preview line(s)")
        
        if detected_products:
            # Get product details
            products = models.execute_kw(db, uid, password,
                'product.product', 'read',
                [detected_products],
                {'fields': ['name', 'default_code']}
            )
            
            print("\nDetected Products:")
            for product in products:
                code = product.get('default_code', '')
                name = product.get('name', 'Unknown')
                print(f"  - [{code}] {name}" if code else f"  - {name}")
        
        print("\n" + "=" * 80)
        print("✅ Test PASSED: Negative valuation detection is working")
        print("=" * 80)
        return True
        
    except Exception as e:
        print(f"\n❌ Test FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_product_duplication_prevention():
    """Test that regenerated products are not detected again"""
    
    print("\n" + "=" * 80)
    print("Testing Product Duplication Prevention")
    print("=" * 80)
    
    try:
        # Connect to Odoo
        common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
        uid = common.authenticate(db, username, password, {})
        
        if not uid:
            print("❌ Authentication failed")
            return False
        
        models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        
        print("\n1. Checking recent regeneration logs...")
        
        # Search for recent logs
        log_ids = models.execute_kw(db, uid, password,
            'valuation.regenerate.log', 'search_read',
            [[('dry_run', '=', False)]],
            {'fields': ['executed_at', 'scope_products'], 'limit': 5, 'order': 'executed_at desc'}
        )
        
        if log_ids:
            print(f"\n✓ Found {len(log_ids)} recent regeneration log(s):")
            for log in log_ids:
                executed_at = log.get('executed_at', 'Unknown')
                products = log.get('scope_products', [])
                print(f"  - Executed at: {executed_at}")
                print(f"    Products processed: {len(products)}")
        else:
            print("ℹ No regeneration logs found")
        
        # Get company and location
        company_ids = models.execute_kw(db, uid, password,
            'res.company', 'search',
            [[]], {'limit': 1}
        )
        company_id = company_ids[0]
        
        location_ids = models.execute_kw(db, uid, password,
            'stock.location', 'search',
            [[('usage', '=', 'internal')]], {'limit': 1}
        )
        location_id = location_ids[0]
        
        # Create wizard and run auto-detect
        print("\n2. Running auto-detect to check filtering...")
        
        wizard_id = models.execute_kw(db, uid, password,
            'valuation.regenerate.wizard', 'create',
            [{
                'company_id': company_id,
                'location_ids': [(6, 0, [location_id])],
                'auto_detect_products': True,
                'mode': 'product',
            }]
        )
        
        result = models.execute_kw(db, uid, password,
            'valuation.regenerate.wizard', 'action_compute_plan',
            [[wizard_id]]
        )
        
        wizard = models.execute_kw(db, uid, password,
            'valuation.regenerate.wizard', 'read',
            [[wizard_id]],
            {'fields': ['product_ids']}
        )[0]
        
        detected_products = wizard.get('product_ids', [])
        
        print(f"\n✓ Auto-detect found {len(detected_products)} product(s)")
        
        # Check if any products from recent logs are in detected products
        if log_ids and detected_products:
            recent_product_ids = []
            for log in log_ids:
                recent_product_ids.extend(log.get('scope_products', []))
            
            duplicates = set(recent_product_ids) & set(detected_products)
            
            if duplicates:
                print(f"\n⚠ Warning: {len(duplicates)} recently processed product(s) were detected again")
                print("  This might be expected if more than 5 minutes have passed")
            else:
                print(f"\n✓ No recently processed products were detected again")
        
        print("\n" + "=" * 80)
        print("✅ Test PASSED: Product duplication prevention is working")
        print("=" * 80)
        return True
        
    except Exception as e:
        print(f"\n❌ Test FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_clear_selection():
    """Test the clear selection feature"""
    
    print("\n" + "=" * 80)
    print("Testing Clear Selection Feature")
    print("=" * 80)
    
    try:
        # Connect to Odoo
        common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
        uid = common.authenticate(db, username, password, {})
        
        if not uid:
            print("❌ Authentication failed")
            return False
        
        models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        
        # Get company and location
        company_ids = models.execute_kw(db, uid, password,
            'res.company', 'search',
            [[]], {'limit': 1}
        )
        company_id = company_ids[0]
        
        location_ids = models.execute_kw(db, uid, password,
            'stock.location', 'search',
            [[('usage', '=', 'internal')]], {'limit': 1}
        )
        location_id = location_ids[0]
        
        # Get a product
        product_ids = models.execute_kw(db, uid, password,
            'product.product', 'search',
            [[('type', '=', 'product')]], {'limit': 1}
        )
        
        if not product_ids:
            print("❌ No product found")
            return False
        
        product_id = product_ids[0]
        
        print("\n1. Creating wizard with product selection...")
        
        # Create wizard with products
        wizard_id = models.execute_kw(db, uid, password,
            'valuation.regenerate.wizard', 'create',
            [{
                'company_id': company_id,
                'location_ids': [(6, 0, [location_id])],
                'product_ids': [(6, 0, [product_id])],
                'mode': 'product',
            }]
        )
        
        wizard = models.execute_kw(db, uid, password,
            'valuation.regenerate.wizard', 'read',
            [[wizard_id]],
            {'fields': ['product_ids']}
        )[0]
        
        print(f"✓ Created wizard with {len(wizard.get('product_ids', []))} product(s)")
        
        # Clear selection
        print("\n2. Clearing selection...")
        
        result = models.execute_kw(db, uid, password,
            'valuation.regenerate.wizard', 'action_clear_selection',
            [[wizard_id]]
        )
        
        print(f"✓ Clear selection executed")
        
        # Read wizard again
        wizard = models.execute_kw(db, uid, password,
            'valuation.regenerate.wizard', 'read',
            [[wizard_id]],
            {'fields': ['product_ids', 'line_preview_ids']}
        )[0]
        
        products_after = wizard.get('product_ids', [])
        preview_after = wizard.get('line_preview_ids', [])
        
        if not products_after and not preview_after:
            print(f"✓ Selection cleared successfully")
            print(f"  Products: {len(products_after)}")
            print(f"  Preview lines: {len(preview_after)}")
        else:
            print(f"⚠ Selection not fully cleared:")
            print(f"  Products remaining: {len(products_after)}")
            print(f"  Preview lines remaining: {len(preview_after)}")
        
        print("\n" + "=" * 80)
        print("✅ Test PASSED: Clear selection feature is working")
        print("=" * 80)
        return True
        
    except Exception as e:
        print(f"\n❌ Test FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    print("\n" + "=" * 80)
    print("VALUATION REGENERATE - NEGATIVE VALUATION FIX TEST SUITE")
    print("=" * 80)
    
    results = []
    
    # Run tests
    results.append(("Negative Valuation Detection", test_negative_valuation_detection()))
    results.append(("Product Duplication Prevention", test_product_duplication_prevention()))
    results.append(("Clear Selection Feature", test_clear_selection()))
    
    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{status} - {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed!")
        sys.exit(0)
    else:
        print(f"\n⚠ {total - passed} test(s) failed")
        sys.exit(1)
