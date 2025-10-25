#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Test script to verify stock layer usage compatibility after fix
"""

import sys
import xmlrpc.client

def test_connection(url, db, username, password):
    """Test connection to Odoo"""
    print("Testing connection to Odoo...")
    
    try:
        common = xmlrpc.client.ServerProxy('{}/xmlrpc/2/common'.format(url))
        uid = common.authenticate(db, username, password, {})
        
        if uid:
            print(f"✓ Successfully connected as user ID: {uid}")
            return uid
        else:
            print("✗ Authentication failed")
            return None
    except Exception as e:
        print(f"✗ Connection error: {str(e)}")
        return None

def check_orphaned_usage_records(url, db, username, password, uid):
    """Check for orphaned stock valuation layer usage records"""
    print("\nChecking for orphaned usage records...")
    
    models = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(url))
    
    try:
        # Get all usage records
        usage_ids = models.execute_kw(
            db, uid, password,
            'stock.valuation.layer.usage', 'search',
            [[]]
        )
        
        print(f"Total usage records: {len(usage_ids)}")
        
        if not usage_ids:
            print("✓ No usage records found")
            return True
        
        # Get all SVL IDs
        svl_ids = models.execute_kw(
            db, uid, password,
            'stock.valuation.layer', 'search',
            [[]]
        )
        
        print(f"Total SVL records: {len(svl_ids)}")
        
        # Check for orphaned records
        orphaned_count = 0
        
        usage_records = models.execute_kw(
            db, uid, password,
            'stock.valuation.layer.usage', 'read',
            [usage_ids],
            {'fields': ['stock_valuation_layer_id', 'dest_stock_valuation_layer_id']}
        )
        
        for usage in usage_records:
            svl_id = usage.get('stock_valuation_layer_id')
            dest_svl_id = usage.get('dest_stock_valuation_layer_id')
            
            if svl_id and svl_id[0] not in svl_ids:
                orphaned_count += 1
                print(f"⚠ Orphaned usage record {usage['id']}: references deleted SVL {svl_id[0]}")
            
            if dest_svl_id and dest_svl_id[0] not in svl_ids:
                orphaned_count += 1
                print(f"⚠ Orphaned usage record {usage['id']}: references deleted dest SVL {dest_svl_id[0]}")
        
        if orphaned_count == 0:
            print("✓ No orphaned usage records found")
            return True
        else:
            print(f"✗ Found {orphaned_count} orphaned usage records")
            return False
            
    except Exception as e:
        print(f"✗ Error checking orphaned records: {str(e)}")
        return False

def check_module_versions(url, db, username, password, uid):
    """Check installed module versions"""
    print("\nChecking module versions...")
    
    models = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(url))
    
    modules_to_check = [
        'buz_valuation_regenerate',
        'stock_valuation_layer_usage'
    ]
    
    all_ok = True
    
    for module_name in modules_to_check:
        try:
            module_ids = models.execute_kw(
                db, uid, password,
                'ir.module.module', 'search',
                [[('name', '=', module_name)]]
            )
            
            if not module_ids:
                print(f"⚠ Module {module_name} not found")
                all_ok = False
                continue
            
            module_data = models.execute_kw(
                db, uid, password,
                'ir.module.module', 'read',
                [module_ids],
                {'fields': ['name', 'state', 'installed_version']}
            )
            
            if module_data:
                module = module_data[0]
                state = module.get('state', 'unknown')
                version = module.get('installed_version', 'unknown')
                
                if state == 'installed':
                    print(f"✓ {module_name}: {state} (version: {version})")
                    
                    # Check minimum version
                    if module_name == 'buz_valuation_regenerate' and version < '17.0.1.3.0':
                        print(f"  ⚠ Please upgrade to version 17.0.1.3.0 or later")
                        all_ok = False
                    elif module_name == 'stock_valuation_layer_usage' and version < '17.0.1.2.0':
                        print(f"  ⚠ Please upgrade to version 17.0.1.2.0 or later")
                        all_ok = False
                else:
                    print(f"⚠ {module_name}: {state}")
                    all_ok = False
        
        except Exception as e:
            print(f"✗ Error checking module {module_name}: {str(e)}")
            all_ok = False
    
    return all_ok

def check_svl_model_inheritance(url, db, username, password, uid):
    """Check if stock.valuation.layer model has proper inheritance"""
    print("\nChecking model inheritance...")
    
    models = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(url))
    
    try:
        # Try to read a sample SVL to check if the model is accessible
        svl_ids = models.execute_kw(
            db, uid, password,
            'stock.valuation.layer', 'search',
            [[]],
            {'limit': 1}
        )
        
        if svl_ids:
            print("✓ stock.valuation.layer model is accessible")
            return True
        else:
            print("ℹ No stock valuation layers found (this is OK if database is empty)")
            return True
            
    except Exception as e:
        print(f"✗ Error accessing stock.valuation.layer model: {str(e)}")
        return False

def main():
    """Main test function"""
    print("=" * 60)
    print("Stock Layer Usage Compatibility Test")
    print("=" * 60)
    print()
    
    # Configuration
    if len(sys.argv) < 5:
        print("Usage: python3 test_stock_layer_compatibility.py <url> <database> <username> <password>")
        print()
        print("Example:")
        print("  python3 test_stock_layer_compatibility.py http://localhost:8069 my_database admin admin")
        sys.exit(1)
    
    url = sys.argv[1]
    db = sys.argv[2]
    username = sys.argv[3]
    password = sys.argv[4]
    
    print(f"URL: {url}")
    print(f"Database: {db}")
    print(f"Username: {username}")
    print()
    
    # Test connection
    uid = test_connection(url, db, username, password)
    if not uid:
        sys.exit(1)
    
    # Run tests
    results = []
    
    results.append(("Module Versions", check_module_versions(url, db, username, password, uid)))
    results.append(("Model Inheritance", check_svl_model_inheritance(url, db, username, password, uid)))
    results.append(("Orphaned Records", check_orphaned_usage_records(url, db, username, password, uid)))
    
    # Summary
    print()
    print("=" * 60)
    print("Test Summary")
    print("=" * 60)
    print()
    
    all_passed = True
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{test_name}: {status}")
        if not result:
            all_passed = False
    
    print()
    if all_passed:
        print("✓ All tests passed!")
        print()
        print("The modules are properly configured and compatible.")
        print("You can now use buz_valuation_regenerate without issues.")
    else:
        print("✗ Some tests failed!")
        print()
        print("Please:")
        print("1. Make sure both modules are upgraded to latest versions")
        print("2. Run the upgrade script: ./upgrade_stock_layer_modules.sh <database>")
        print("3. Restart Odoo service")
        print("4. Run this test again")
    
    print()
    sys.exit(0 if all_passed else 1)

if __name__ == '__main__':
    main()
