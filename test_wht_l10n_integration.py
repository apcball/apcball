#!/usr/bin/env python3
"""
Test script to verify WHT integration with l10n_th_account_tax module
"""

def test_wht_l10n_integration():
    import sys
    import os
    
    # Add Odoo path
    sys.path.append('/opt/instance1/odoo17')
    
    # Import Odoo
    import odoo
    from odoo import api, SUPERUSER_ID
    
    # Connect to database
    db_name = 'instance1'
    odoo.tools.config['db_name'] = db_name
    
    with odoo.registry(db_name).cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {})
        
        print("🔍 Testing WHT Integration with l10n_th_account_tax")
        print("=" * 60)
        
        # Test 1: Check if l10n_th_account_tax module is installed
        print("\n1. Checking l10n_th_account_tax module...")
        if 'account.withholding.tax' in env.registry:
            print("✅ l10n_th_account_tax module is installed")
            
            # Test 2: Check withholding tax configuration
            print("\n2. Checking withholding tax configuration...")
            withholding_taxes = env['account.withholding.tax'].search([])
            print(f"Found {len(withholding_taxes)} withholding tax configurations:")
            
            for wht in withholding_taxes:
                print(f"  • {wht.name} (Rate: {wht.amount}%, Company: {wht.company_id.name})")
                
                # Find matching account.tax records
                matching_taxes = env['account.tax'].search([
                    ('company_id', '=', wht.company_id.id),
                    ('name', 'ilike', wht.name),
                    ('amount', '<', 0),
                ])
                
                if matching_taxes:
                    for tax in matching_taxes:
                        print(f"    → Matches account.tax: {tax.name} (Rate: {tax.amount}%)")
                else:
                    print(f"    → ⚠️ No matching account.tax found")
            
            # Test 3: Test WHT wizard domain
            print("\n3. Testing WHT wizard domain...")
            try:
                wizard = env['wht.clear.advance.wizard']
                domain = wizard._get_wht_tax_domain()
                print(f"WHT tax domain: {domain}")
                
                # Apply domain to find available WHT taxes
                available_taxes = env['account.tax'].search(domain)
                print(f"Found {len(available_taxes)} available WHT taxes:")
                for tax in available_taxes:
                    print(f"  • {tax.name} (Rate: {tax.amount}%, Type: {tax.type_tax_use})")
                    
            except Exception as e:
                print(f"❌ Error testing wizard domain: {e}")
            
            # Test 4: Test validation method
            print("\n4. Testing WHT validation...")
            try:
                wizard_model = env['wht.clear.advance.wizard']
                all_taxes = env['account.tax'].search([('amount', '<', 0)])
                
                for tax in all_taxes[:5]:  # Test first 5 negative taxes
                    is_valid = wizard_model._validate_wht_tax(tax)
                    status = "✅ Valid" if is_valid else "❌ Invalid"
                    print(f"  • {tax.name} (Rate: {tax.amount}%): {status}")
                    
            except Exception as e:
                print(f"❌ Error testing validation: {e}")
                
        else:
            print("❌ l10n_th_account_tax module is NOT installed")
            print("   Please install the module for proper WHT functionality")
        
        print("\n" + "=" * 60)
        print("✅ WHT Integration test completed")

if __name__ == "__main__":
    test_wht_l10n_integration()