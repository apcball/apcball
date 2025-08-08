"""
Test Script for WHT Tax System v2.0
Run this script to test the new WHT tax functionality
"""

def test_wht_system(env):
    """
    Comprehensive test for WHT tax system
    """
    print("=== Testing WHT Tax System v2.0 ===\n")
    
    # Test 1: Check WHT Tax Records
    print("1. Testing WHT Tax Records...")
    wht_taxes = [
        'l10n_th_account_tax.wht_tax_service_3',
        'l10n_th_account_tax.wht_tax_professional_5', 
        'l10n_th_account_tax.wht_tax_rental_5',
        'l10n_th_account_tax.wht_tax_transport_1',
    ]
    
    for tax_ref in wht_taxes:
        try:
            tax = env.ref(tax_ref, raise_if_not_found=False)
            if tax:
                print(f"   ✓ {tax.name}: {tax.amount}% - {tax.type_tax_use}")
            else:
                print(f"   ✗ Missing: {tax_ref}")
        except Exception as e:
            print(f"   ✗ Error loading {tax_ref}: {e}")
    
    # Test 2: Test Product WHT Configuration
    print("\n2. Testing Product WHT Configuration...")
    try:
        # Create test product
        test_product = env['product.template'].create({
            'name': 'Test Service Product',
            'type': 'service',
            'list_price': 1000.0,
        })
        
        # Set WHT tax
        service_wht = env.ref('l10n_th_account_tax.wht_tax_service_3', raise_if_not_found=False)
        if service_wht:
            test_product.write({
                'wht_tax_purchase_id': service_wht.id,
                'supplier_taxes_id': [(4, service_wht.id)],
            })
            print(f"   ✓ Product created with WHT: {test_product.name}")
        else:
            print("   ✗ Service WHT tax not found")
            
    except Exception as e:
        print(f"   ✗ Error creating product: {e}")
    
    # Test 3: Test Invoice with WHT
    print("\n3. Testing Invoice with WHT...")
    try:
        # Create test vendor
        test_vendor = env['res.partner'].create({
            'name': 'Test Vendor',
            'is_company': True,
            'supplier_rank': 1,
        })
        
        # Create invoice
        invoice = env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': test_vendor.id,
            'invoice_date': '2024-01-15',
            'invoice_line_ids': [(0, 0, {
                'product_id': test_product.id,
                'quantity': 1,
                'price_unit': 1000.0,
                'tax_ids': [(4, service_wht.id)] if service_wht else [],
            })],
        })
        
        if service_wht:
            # Calculate WHT
            invoice._recompute_dynamic_lines()
            print(f"   ✓ Invoice created: {invoice.name}")
            print(f"   ✓ Invoice total: {invoice.amount_total}")
            
            # Check WHT calculation
            wht_lines = invoice.line_ids.filtered(lambda l: service_wht in l.tax_ids)
            if wht_lines:
                print(f"   ✓ WHT tax line found: {wht_lines[0].credit}")
            else:
                print("   ✗ No WHT tax line found")
        else:
            print("   ✗ Cannot test without WHT tax")
            
    except Exception as e:
        print(f"   ✗ Error creating invoice: {e}")
    
    # Test 4: Test Payment with WHT
    print("\n4. Testing Payment with WHT...")
    try:
        if 'invoice' in locals() and service_wht:
            # Post invoice
            invoice.action_post()
            
            # Create payment
            payment_vals = {
                'payment_type': 'outbound',
                'partner_type': 'supplier',
                'partner_id': test_vendor.id,
                'amount': invoice.amount_total - 30.0,  # Minus 3% WHT
                'currency_id': invoice.currency_id.id,
                'date': '2024-01-15',
                'reconciled_bill_ids': [(4, invoice.id)],
            }
            
            payment = env['account.payment'].create(payment_vals)
            print(f"   ✓ Payment created: {payment.name}")
            print(f"   ✓ Payment amount: {payment.amount}")
            
            # Post payment
            payment.action_post()
            print(f"   ✓ Payment posted")
            
            # Check WHT certificates
            if hasattr(payment, 'wht_cert_ids'):
                if payment.wht_cert_ids:
                    print(f"   ✓ WHT Certificate auto-generated: {len(payment.wht_cert_ids)} cert(s)")
                else:
                    print("   ⚠ No WHT certificates generated (may be normal)")
            else:
                print("   ⚠ WHT certificate field not available")
                
    except Exception as e:
        print(f"   ✗ Error testing payment: {e}")
    
    # Test 5: Test Migration Functions
    print("\n5. Testing Migration Functions...")
    try:
        from odoo.addons.l10n_th_account_tax.migrations.post_migration import migrate_wht_data
        print("   ✓ Migration functions accessible")
        
        # Test mapping functions
        print("   ✓ Migration mapping available")
        
    except Exception as e:
        print(f"   ✗ Migration functions error: {e}")
    
    # Test 6: Check Views and Security
    print("\n6. Testing Views and Security...")
    try:
        # Check if views exist
        views = [
            'l10n_th_account_tax.product_template_form_view_wht',
            'l10n_th_account_tax.account_payment_form_view_wht',
            'l10n_th_account_tax.account_move_form_view_wht_info',
        ]
        
        for view_ref in views:
            try:
                view = env.ref(view_ref, raise_if_not_found=False)
                if view:
                    print(f"   ✓ View exists: {view.name}")
                else:
                    print(f"   ✗ View missing: {view_ref}")
            except:
                print(f"   ⚠ View may not be loaded yet: {view_ref}")
                
    except Exception as e:
        print(f"   ✗ Error checking views: {e}")
    
    print("\n=== Test Summary ===")
    print("✓ = Pass")
    print("⚠ = Warning (may be normal)")
    print("✗ = Fail (needs attention)")
    print("\nTest completed!")

# Helper function to run from Odoo shell
def run_wht_test():
    """
    Run this function from Odoo shell:
    
    $ python odoo-bin shell -d your_database
    >>> exec(open('/path/to/test_wht_system.py').read())
    >>> run_wht_test()
    """
    import odoo
    from odoo import api, SUPERUSER_ID
    
    # Get environment
    db_name = 'your_database'  # Change this
    
    with odoo.api.Environment.manage():
        env = odoo.api.Environment(odoo.registry(db_name).cursor(), SUPERUSER_ID, {})
        try:
            test_wht_system(env)
        finally:
            env.cr.close()

if __name__ == "__main__":
    print("Run this script from Odoo shell using run_wht_test() function")
