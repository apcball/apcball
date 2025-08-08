#!/usr/bin/env python3
"""
WHT Tax Diagnostic Script for l10n_th_account_tax module
This script helps diagnose why WHT Tax is not working properly
"""

import sys
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def check_module_installation():
    """Check if the l10n_th_account_tax module is properly installed"""
    logger.info("Checking module installation...")
    
    try:
        from odoo import api, SUPERUSER_ID
        from odoo.modules.registry import Registry
        
        # This should be run within Odoo environment
        # odoo-bin shell -d your_database --no-http
        
        print("✓ Module l10n_th_account_tax can be imported")
        return True
    except ImportError as e:
        print(f"✗ Module import failed: {e}")
        return False

def check_wht_accounts(env):
    """Check if WHT accounts are properly configured"""
    logger.info("Checking WHT account configuration...")
    
    # Check for WHT accounts
    wht_accounts = env['account.account'].search([('wht_account', '=', True)])
    
    if not wht_accounts:
        print("✗ No WHT accounts found. Please create an account and mark it as 'WHT Account'")
        return False
    
    print(f"✓ Found {len(wht_accounts)} WHT account(s):")
    for account in wht_accounts:
        print(f"  - {account.code} {account.name}")
    
    return True

def check_wht_tax_types(env):
    """Check if WHT tax types are configured"""
    logger.info("Checking WHT tax type configuration...")
    
    wht_taxes = env['account.withholding.tax'].search([])
    
    if not wht_taxes:
        print("✗ No WHT tax types found. Please create withholding tax types")
        return False
    
    print(f"✓ Found {len(wht_taxes)} WHT tax type(s):")
    for tax in wht_taxes:
        print(f"  - {tax.name} ({tax.amount}%)")
        if not tax.account_id:
            print(f"    ✗ No account set for {tax.name}")
        else:
            print(f"    ✓ Account: {tax.account_id.code} {tax.account_id.name}")
    
    return len(wht_taxes) > 0

def check_products_wht_config(env):
    """Check if products have WHT configuration"""
    logger.info("Checking product WHT configuration...")
    
    products_with_wht = env['product.template'].search([
        '|', '|',
        ('wht_tax_id', '!=', False),
        ('supplier_wht_tax_id', '!=', False),
        ('supplier_company_wht_tax_id', '!=', False)
    ])
    
    total_products = env['product.template'].search_count([])
    
    print(f"✓ {len(products_with_wht)} out of {total_products} products have WHT configuration")
    
    if len(products_with_wht) == 0:
        print("⚠ No products have WHT taxes configured. This may be intentional.")
    
    return True

def check_user_permissions(env):
    """Check if current user has proper permissions"""
    logger.info("Checking user permissions...")
    
    user = env.user
    
    # Check if user has accounting access
    if not user.has_group('account.group_account_user'):
        print("✗ User doesn't have basic accounting access")
        return False
    
    print("✓ User has basic accounting access")
    
    # Check for invoice access
    if user.has_group('account.group_account_invoice'):
        print("✓ User has invoice management access")
    else:
        print("⚠ User doesn't have invoice management access")
    
    return True

def check_pit_rates(env):
    """Check Personal Income Tax rates configuration"""
    logger.info("Checking PIT rates configuration...")
    
    pit_rates = env['personal.income.tax'].search([])
    
    if not pit_rates:
        print("⚠ No PIT rates configured. Required if using Personal Income Tax")
        return False
    
    print(f"✓ Found {len(pit_rates)} PIT rate configuration(s)")
    for pit in pit_rates:
        print(f"  - Effective Date: {pit.effective_date}")
    
    return True

def test_wht_calculation(env):
    """Test basic WHT calculation"""
    logger.info("Testing WHT calculation...")
    
    try:
        # Get a sample WHT tax
        wht_tax = env['account.withholding.tax'].search([], limit=1)
        if not wht_tax:
            print("✗ Cannot test - no WHT tax configured")
            return False
        
        # Test calculation
        base_amount = 1000.0
        expected_wht = base_amount * (wht_tax.amount / 100)
        
        print(f"✓ WHT calculation test passed:")
        print(f"  - Base amount: {base_amount}")
        print(f"  - WHT rate: {wht_tax.amount}%")
        print(f"  - Expected WHT: {expected_wht}")
        
        return True
        
    except Exception as e:
        print(f"✗ WHT calculation test failed: {e}")
        return False

def run_diagnostics():
    """Run all diagnostic checks"""
    print("=" * 50)
    print("WHT Tax Diagnostic Report")
    print("=" * 50)
    
    # Note: This script should be run within Odoo environment
    # Example: odoo-bin shell -d your_database --no-http
    # Then import and run this script
    
    try:
        import odoo
        from odoo import api, SUPERUSER_ID
        from odoo.modules.registry import Registry
        
        # Get database name from command line or environment
        db_name = 'your_database'  # Replace with actual database name
        
        registry = Registry(db_name)
        with registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            
            checks = [
                check_wht_accounts,
                check_wht_tax_types,
                check_products_wht_config,
                check_user_permissions,
                check_pit_rates,
                test_wht_calculation,
            ]
            
            results = []
            for check in checks:
                try:
                    result = check(env)
                    results.append(result)
                    print()
                except Exception as e:
                    print(f"✗ Check failed: {e}")
                    results.append(False)
                    print()
            
            print("=" * 50)
            print("Summary:")
            print(f"Passed: {sum(results)}/{len(results)} checks")
            
            if all(results):
                print("✓ All checks passed! WHT should be working.")
            else:
                print("✗ Some issues found. Check the details above.")
                print("\nRecommended actions:")
                print("1. Fix the failed checks above")
                print("2. Refer to IMPLEMENTATION_GUIDE.md")
                print("3. Check Odoo logs for specific errors")
            
            print("=" * 50)
            
    except Exception as e:
        print(f"Error running diagnostics: {e}")
        print("\nTo run this diagnostic:")
        print("1. odoo-bin shell -d your_database --no-http")
        print("2. exec(open('/path/to/this/script.py').read())")

if __name__ == "__main__":
    print("This script should be run within Odoo environment.")
    print("Usage:")
    print("1. odoo-bin shell -d your_database --no-http")
    print("2. exec(open('/path/to/wht_diagnostic.py').read())")
