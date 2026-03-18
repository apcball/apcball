#!/usr/bin/env python3
"""
Test script to validate logic consistency across all marketplace_settlement processes
This script tests the complete workflow to ensure all components work together properly.
"""

import sys
import logging

_logger = logging.getLogger(__name__)

def test_marketplace_settlement_logic():
    """Test complete marketplace settlement workflow"""
    
    print("\n" + "="*80)
    print("MARKETPLACE SETTLEMENT - LOGIC CONSISTENCY TEST")
    print("="*80 + "\n")
    
    try:
        import odoo
        from odoo import api, SUPERUSER_ID
        
        # Get environment
        env = api.Environment(odoo.registry(odoo.tools.config['db_name']), SUPERUSER_ID, {})
        
        # Test 1: Field definitions consistency
        print("\n[TEST 1] Checking field definitions consistency...")
        AccountMove = env['account.move']
        Settlement = env['marketplace.settlement']
        
        # Check x_settlement_id field exists and is not duplicated
        if 'x_settlement_id' not in AccountMove._fields:
            print("❌ FAIL: x_settlement_id field not found on account.move")
            return False
        else:
            print("✅ PASS: x_settlement_id field exists on account.move")
        
        # Test 2: Settlement amount calculations
        print("\n[TEST 2] Testing settlement amount calculations...")
        settlements = Settlement.search([('state', '=', 'posted')], limit=5)
        
        for settlement in settlements:
            # Verify total_vendor_bills calculation
            manual_total = 0.0
            for bill in settlement.vendor_bill_ids.filtered(lambda b: b.state == 'posted'):
                if bill.move_type == 'in_refund':
                    manual_total -= abs(bill.amount_residual if not settlement.is_netted else bill.amount_total)
                else:
                    manual_total += abs(bill.amount_residual if not settlement.is_netted else bill.amount_total)
            
            computed_total = settlement.total_vendor_bills
            
            if abs(manual_total - computed_total) > 0.01:
                print(f"❌ FAIL: Settlement {settlement.name} - vendor bill total mismatch")
                print(f"   Manual: {manual_total}, Computed: {computed_total}")
                return False
        
        print(f"✅ PASS: Amount calculations correct for {len(settlements)} settlements")
        
        # Test 3: State transitions
        print("\n[TEST 3] Testing state transitions...")
        draft_settlements = Settlement.search([('state', '=', 'draft')], limit=1)
        posted_settlements = Settlement.search([('state', '=', 'posted')], limit=1)
        
        for settlement in draft_settlements:
            if settlement.move_id:
                print(f"❌ FAIL: Draft settlement {settlement.name} has a move_id")
                return False
        
        for settlement in posted_settlements:
            if not settlement.move_id or settlement.move_id.state != 'posted':
                print(f"❌ FAIL: Posted settlement {settlement.name} has invalid move")
                return False
        
        print("✅ PASS: State transitions are consistent")
        
        # Test 4: Netting state consistency
        print("\n[TEST 4] Testing netting state consistency...")
        netted_settlements = Settlement.search([('is_netted', '=', True)], limit=5)
        
        for settlement in netted_settlements:
            # Verify netting move exists and is posted
            if not settlement.netting_move_id:
                print(f"❌ FAIL: Settlement {settlement.name} is marked as netted but has no netting_move_id")
                return False
            
            if settlement.netting_move_id.state != 'posted':
                print(f"❌ FAIL: Settlement {settlement.name} netting move is not posted")
                return False
            
            # Verify can_perform_netting is False when already netted
            if settlement.can_perform_netting:
                print(f"❌ FAIL: Settlement {settlement.name} is netted but can_perform_netting is True")
                return False
        
        print(f"✅ PASS: Netting state consistent for {len(netted_settlements)} settlements")
        
        # Test 5: Fee allocation calculations
        print("\n[TEST 5] Testing fee allocation calculations...")
        FeeAllocation = env['marketplace.fee.allocation']
        allocations = FeeAllocation.search([('allocation_method', '=', 'proportional')], limit=5)
        
        for allocation in allocations:
            # Verify allocation percentage
            if allocation.settlement_id.total_invoice_amount > 0:
                expected_pct = (allocation.allocation_base_amount / allocation.settlement_id.total_invoice_amount) * 100
                actual_pct = allocation.allocation_percentage
                
                if abs(expected_pct - actual_pct) > 0.01:
                    print(f"❌ FAIL: Allocation percentage mismatch for {allocation.display_name}")
                    print(f"   Expected: {expected_pct}%, Actual: {actual_pct}%")
                    return False
        
        print(f"✅ PASS: Fee allocation calculations correct for {len(allocations)} records")
        
        # Test 6: Vendor bill linking
        print("\n[TEST 6] Testing vendor bill linking...")
        vendor_bills = AccountMove.search([
            ('move_type', 'in', ['in_invoice', 'in_refund']),
            ('x_settlement_id', '!=', False),
            ('state', '=', 'posted')
        ], limit=5)
        
        for bill in vendor_bills:
            # Verify bill is in settlement's vendor_bill_ids
            if bill not in bill.x_settlement_id.vendor_bill_ids:
                print(f"❌ FAIL: Vendor bill {bill.name} has x_settlement_id but is not in settlement.vendor_bill_ids")
                return False
        
        print(f"✅ PASS: Vendor bill linking consistent for {len(vendor_bills)} bills")
        
        # Test 7: Reconciliation consistency
        print("\n[TEST 7] Testing reconciliation consistency...")
        reconciled_settlements = Settlement.search([
            ('state', '=', 'posted'),
            ('move_id', '!=', False)
        ], limit=5)
        
        for settlement in reconciled_settlements:
            # Check if settlement move has reconciled lines
            settlement_lines = settlement.move_id.line_ids.filtered(
                lambda l: l.account_id.account_type == 'asset_receivable'
            )
            
            # At least some lines should be reconciled if settlement was successful
            # (This is a soft check as some settlements might not be reconciled yet)
            if len(settlement_lines) > 0:
                reconciled_lines = settlement_lines.filtered(lambda l: l.reconciled)
                # Just log the status, don't fail
                if reconciled_lines:
                    print(f"   Settlement {settlement.name}: {len(reconciled_lines)}/{len(settlement_lines)} lines reconciled")
        
        print(f"✅ PASS: Reconciliation status checked for {len(reconciled_settlements)} settlements")
        
        # Test 8: Compute method dependencies
        print("\n[TEST 8] Validating compute method dependencies...")
        
        # Force recompute on a settlement to ensure no errors
        if settlements:
            test_settlement = settlements[0]
            try:
                test_settlement._compute_amounts()
                test_settlement._compute_netting_state()
                test_settlement._compute_state()
                test_settlement._compute_netted_amount()
                print("✅ PASS: All compute methods execute without errors")
            except Exception as e:
                print(f"❌ FAIL: Compute method error: {str(e)}")
                return False
        
        # Final Summary
        print("\n" + "="*80)
        print("✅ ALL TESTS PASSED - Module logic is consistent!")
        print("="*80 + "\n")
        
        return True
        
    except Exception as e:
        print(f"\n❌ TEST SUITE FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    success = test_marketplace_settlement_logic()
    sys.exit(0 if success else 1)
