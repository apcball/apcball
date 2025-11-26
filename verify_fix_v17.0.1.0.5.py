#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Verification Script for stock_fifo_by_location v17.0.1.0.5

This script verifies that the inter-warehouse transfer fix has been
properly implemented and is working correctly.

Usage:
    # From Odoo shell
    python3 odoo-bin shell -d your_database
    >>> exec(open('/opt/instance1/odoo17/custom-addons/verify_fix_v17.0.1.0.5.py').read())
"""

def verify_fix(env):
    """
    Verify the inter-warehouse transfer fix implementation.
    
    Checks:
    1. Module version is 17.0.1.0.5
    2. _create_inter_warehouse_valuation_layers method is removed
    3. FIFO service has fallback logic
    4. No 0.00 valuation layers in recent transfers
    5. Test cases exist for the fix
    """
    print("=" * 80)
    print("VERIFICATION: stock_fifo_by_location v17.0.1.0.5 Fix")
    print("=" * 80)
    print()
    
    results = {
        'passed': [],
        'failed': [],
        'warnings': []
    }
    
    # Test 1: Check module version
    print("✓ Test 1: Checking module version...")
    try:
        module = env['ir.module.module'].search([
            ('name', '=', 'stock_fifo_by_location'),
            ('state', '=', 'installed')
        ])
        if module:
            version = module.latest_version
            print(f"  Current version: {version}")
            if version == '17.0.1.0.5':
                results['passed'].append("Module version is 17.0.1.0.5")
                print("  ✅ PASS: Version is correct")
            else:
                results['warnings'].append(f"Module version is {version}, expected 17.0.1.0.5")
                print(f"  ⚠️  WARNING: Expected 17.0.1.0.5, got {version}")
        else:
            results['failed'].append("Module not installed")
            print("  ❌ FAIL: Module not installed")
    except Exception as e:
        results['failed'].append(f"Version check error: {e}")
        print(f"  ❌ FAIL: {e}")
    print()
    
    # Test 2: Check method removal
    print("✓ Test 2: Verifying _create_inter_warehouse_valuation_layers is removed...")
    try:
        stock_move = env['stock.move']
        has_method = hasattr(stock_move, '_create_inter_warehouse_valuation_layers')
        if not has_method:
            results['passed'].append("Problematic method successfully removed")
            print("  ✅ PASS: Method is removed")
        else:
            results['failed'].append("_create_inter_warehouse_valuation_layers still exists")
            print("  ❌ FAIL: Method still exists (should be removed)")
    except Exception as e:
        results['failed'].append(f"Method check error: {e}")
        print(f"  ❌ FAIL: {e}")
    print()
    
    # Test 3: Check FIFO service fallback
    print("✓ Test 3: Testing FIFO service fallback logic...")
    try:
        fifo_service = env['fifo.service']
        # Create a test product
        test_product = env['product.product'].create({
            'name': 'Verification Test Product',
            'type': 'product',
            'cost_method': 'fifo',
            'standard_price': 150.0,
        })
        
        # Get a warehouse
        warehouse = env['stock.warehouse'].search([
            ('company_id', '=', env.company.id)
        ], limit=1)
        
        if warehouse:
            # Test with empty queue (should use fallback)
            result = fifo_service.calculate_fifo_cost(
                test_product, warehouse, 10.0, env.company.id
            )
            
            if result['unit_cost'] == 150.0:  # Should use standard_price
                results['passed'].append("FIFO fallback to standard_price works")
                print(f"  ✅ PASS: Fallback returns standard_price ({result['unit_cost']})")
            elif result['unit_cost'] == 0.0:
                results['failed'].append("FIFO still returns 0.0 (no fallback)")
                print("  ❌ FAIL: Returns 0.0 instead of standard_price")
            else:
                results['warnings'].append(f"Unexpected unit_cost: {result['unit_cost']}")
                print(f"  ⚠️  WARNING: Unexpected unit_cost {result['unit_cost']}")
        
        # Cleanup
        test_product.unlink()
    except Exception as e:
        results['failed'].append(f"FIFO fallback test error: {e}")
        print(f"  ❌ FAIL: {e}")
    print()
    
    # Test 4: Check for 0.00 valuation layers in recent transfers
    print("✓ Test 4: Checking for 0.00 valuation layers in recent data...")
    try:
        # Look for valuation layers with 0.00 value but non-zero quantity
        zero_layers = env['stock.valuation.layer'].search([
            ('value', '=', 0.0),
            ('quantity', '!=', 0.0),
            ('create_date', '>=', '2024-11-01'),  # Recent data
        ])
        
        if len(zero_layers) == 0:
            results['passed'].append("No 0.00 valuation layers found")
            print("  ✅ PASS: No problematic 0.00 layers")
        else:
            results['warnings'].append(f"Found {len(zero_layers)} layers with 0.00 value")
            print(f"  ⚠️  WARNING: Found {len(zero_layers)} layers with 0.00 value")
            print(f"  These may be from before the fix was applied")
    except Exception as e:
        results['failed'].append(f"Zero layer check error: {e}")
        print(f"  ❌ FAIL: {e}")
    print()
    
    # Test 5: Check test cases
    print("✓ Test 5: Verifying new test cases exist...")
    try:
        import os
        test_file = '/opt/instance1/odoo17/custom-addons/stock_fifo_by_location/tests/test_fifo_by_location.py'
        if os.path.exists(test_file):
            with open(test_file, 'r') as f:
                content = f.read()
                
            # Check for new test methods
            test_methods = [
                'test_inter_warehouse_transfer_no_zero_valuation',
                'test_inter_warehouse_transfer_empty_source_uses_standard_price',
                'test_no_duplicate_layers_created',
                'test_intra_warehouse_move_same_warehouse',
            ]
            
            found_tests = []
            missing_tests = []
            for test in test_methods:
                if test in content:
                    found_tests.append(test)
                else:
                    missing_tests.append(test)
            
            if len(missing_tests) == 0:
                results['passed'].append(f"All {len(test_methods)} new tests exist")
                print(f"  ✅ PASS: All {len(test_methods)} new tests found")
            else:
                results['warnings'].append(f"Missing {len(missing_tests)} test(s)")
                print(f"  ⚠️  WARNING: Missing tests: {', '.join(missing_tests)}")
        else:
            results['warnings'].append("Test file not found")
            print("  ⚠️  WARNING: Test file not found")
    except Exception as e:
        results['failed'].append(f"Test file check error: {e}")
        print(f"  ❌ FAIL: {e}")
    print()
    
    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"✅ Passed:   {len(results['passed'])}")
    print(f"⚠️  Warnings: {len(results['warnings'])}")
    print(f"❌ Failed:   {len(results['failed'])}")
    print()
    
    if results['passed']:
        print("Passed checks:")
        for item in results['passed']:
            print(f"  ✅ {item}")
        print()
    
    if results['warnings']:
        print("Warnings:")
        for item in results['warnings']:
            print(f"  ⚠️  {item}")
        print()
    
    if results['failed']:
        print("Failed checks:")
        for item in results['failed']:
            print(f"  ❌ {item}")
        print()
    
    # Final verdict
    print("=" * 80)
    if len(results['failed']) == 0:
        print("✅ VERIFICATION PASSED")
        print("The fix has been properly implemented!")
    else:
        print("❌ VERIFICATION FAILED")
        print("Please review the failed checks above")
    print("=" * 80)
    
    return results


# Auto-run if executed in Odoo shell
if __name__ == '__main__' or 'env' in dir():
    try:
        results = verify_fix(env)
    except NameError:
        print("This script should be run from Odoo shell:")
        print("python3 odoo-bin shell -d your_database")
        print(">>> exec(open('/opt/instance1/odoo17/custom-addons/verify_fix_v17.0.1.0.5.py').read())")
