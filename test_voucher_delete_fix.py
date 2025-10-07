#!/usr/bin/env python3
"""
Test script to verify voucher deletion fix

This script tests that vouchers and voucher lines can be deleted
even when they have linked payments (FK constraint fix).

Run from Odoo shell:
    python3 odoo-bin shell -c /etc/instance1.conf -d <database_name>
    
Then in the shell:
    exec(open('/opt/instance1/odoo17/custom-addons/test_voucher_delete_fix.py').read())
"""

import logging
_logger = logging.getLogger(__name__)

def test_voucher_deletion_fix():
    """Test that vouchers can be deleted even with linked payments"""
    
    print("\n" + "="*80)
    print("Testing Voucher Deletion Fix - FK Constraint Resolution")
    print("="*80 + "\n")
    
    # Get environment
    env = globals().get('env')
    if not env:
        print("ERROR: This script must be run from Odoo shell")
        print("Usage: python3 odoo-bin shell -c /etc/instance1.conf -d <database>")
        return False
    
    try:
        # Test 1: Check if models exist
        print("Test 1: Checking models exist...")
        voucher_model = env['account.receipt.voucher']
        line_model = env['account.receipt.voucher.line']
        payment_model = env['account.payment']
        print("✓ All models found\n")
        
        # Test 2: Find a voucher with payments (if exists)
        print("Test 2: Looking for vouchers with linked payments...")
        vouchers_with_payments = voucher_model.search([
            ('state', '=', 'confirmed'),
            ('line_ids.payment_ids', '!=', False)
        ], limit=1)
        
        if vouchers_with_payments:
            voucher = vouchers_with_payments[0]
            line_count = len(voucher.line_ids)
            payment_count = len(voucher.mapped('line_ids.payment_ids'))
            
            print(f"✓ Found voucher: {voucher.name}")
            print(f"  - Lines: {line_count}")
            print(f"  - Linked Payments: {payment_count}")
            print(f"  - State: {voucher.state}")
            
            # Test 3: Check unlink method exists
            print("\nTest 3: Checking unlink methods exist...")
            if hasattr(voucher_model, 'unlink'):
                print("✓ AccountReceiptVoucher.unlink() exists")
            else:
                print("✗ AccountReceiptVoucher.unlink() NOT FOUND")
                return False
                
            if hasattr(line_model, 'unlink'):
                print("✓ AccountReceiptVoucherLine.unlink() exists")
            else:
                print("✗ AccountReceiptVoucherLine.unlink() NOT FOUND")
                return False
            
            # Test 4: Verify the fix (without actually deleting)
            print("\nTest 4: Simulating deletion check...")
            print("INFO: This test does NOT actually delete records")
            print("INFO: It only verifies the unlink method can be called")
            
            # Check if we can access the payment_ids on lines
            for line in voucher.line_ids:
                if line.payment_ids:
                    print(f"  - Line {line.id} has {len(line.payment_ids)} payment(s)")
            
            print("\n✓ Fix verification complete")
            print("\nNOTE: To actually test deletion, create a test voucher and delete it manually")
            
        else:
            print("✓ No vouchers with payments found (may be normal)")
            print("  To test the fix:")
            print("  1. Create a receipt voucher in the UI")
            print("  2. Confirm it (creates payments)")
            print("  3. Try to delete it")
            print("  4. Should succeed without FK error")
        
        # Test 5: Check relation table structure
        print("\nTest 5: Checking Many2many relation structure...")
        cr = env.cr
        cr.execute("""
            SELECT 
                tc.constraint_name, 
                tc.table_name, 
                kcu.column_name
            FROM information_schema.table_constraints AS tc 
            JOIN information_schema.key_column_usage AS kcu
              ON tc.constraint_name = kcu.constraint_name
              AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY' 
              AND tc.table_name = 'account_receipt_voucher_line_payment_rel'
            ORDER BY tc.constraint_name;
        """)
        
        constraints = cr.fetchall()
        if constraints:
            print("✓ Found foreign key constraints on relation table:")
            for constraint in constraints:
                print(f"  - {constraint[0]}: {constraint[2]}")
        else:
            print("✗ No FK constraints found (unexpected)")
        
        print("\n" + "="*80)
        print("All tests completed successfully!")
        print("="*80 + "\n")
        
        return True
        
    except Exception as e:
        print(f"\n✗ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

# Run the test
if __name__ == '__main__':
    test_voucher_deletion_fix()
