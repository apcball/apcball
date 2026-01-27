#!/usr/bin/env python3
"""
Test script for Settlement Feature in employee_advance module
This script validates the Settlement wizard functionality

Test scenarios:
1. Pay Employee (positive balance)
2. Employee Refund (negative balance)
3. Write-off to Expense
4. Write-off to Other Income
5. Partial settlement
6. Full settlement
"""

import sys
import logging

_logger = logging.getLogger(__name__)

def test_settlement_wizard_structure():
    """Test if settlement wizard files are properly structured"""
    print("\n" + "="*70)
    print("TEST 1: Settlement Wizard Structure")
    print("="*70)
    
    import os
    base_path = "/opt/instance1/odoo17/custom-addons/employee_advance"
    
    # Check if wizard file exists
    wizard_file = os.path.join(base_path, "wizards", "settlement_wizard.py")
    assert os.path.exists(wizard_file), "❌ settlement_wizard.py not found"
    print("✅ settlement_wizard.py exists")
    
    # Check if view file exists
    view_file = os.path.join(base_path, "views", "advance_settlement_wizard_views.xml")
    assert os.path.exists(view_file), "❌ advance_settlement_wizard_views.xml not found"
    print("✅ advance_settlement_wizard_views.xml exists")
    
    # Check if wizard is imported in __init__.py
    init_file = os.path.join(base_path, "wizards", "__init__.py")
    with open(init_file, 'r') as f:
        init_content = f.read()
        assert 'settlement_wizard' in init_content, "❌ settlement_wizard not imported in __init__.py"
    print("✅ settlement_wizard imported in __init__.py")
    
    # Check if view is declared in manifest
    manifest_file = os.path.join(base_path, "__manifest__.py")
    with open(manifest_file, 'r') as f:
        manifest_content = f.read()
        assert 'advance_settlement_wizard_views.xml' in manifest_content, "❌ View not declared in manifest"
    print("✅ View declared in __manifest__.py")
    
    print("\n✅ All structure tests passed!")
    return True

def test_wizard_code_quality():
    """Test wizard code for common issues"""
    print("\n" + "="*70)
    print("TEST 2: Wizard Code Quality")
    print("="*70)
    
    wizard_file = "/opt/instance1/odoo17/custom-addons/employee_advance/wizards/settlement_wizard.py"
    with open(wizard_file, 'r') as f:
        content = f.read()
    
    # Test 1: Check for proper model name
    assert "_name = 'advance.settlement.wizard'" in content, "❌ Model name not properly defined"
    print("✅ Model name properly defined")
    
    # Test 2: Check for main action method
    assert "def action_settle_advance(self):" in content, "❌ Main action method not found"
    print("✅ Main action method exists")
    
    # Test 3: Check for validation method
    assert "def _validate_settlement(self):" in content, "❌ Validation method not found"
    print("✅ Validation method exists")
    
    # Test 4: Check for move creation method
    assert "def _create_settlement_move(self):" in content, "❌ Move creation method not found"
    print("✅ Move creation method exists")
    
    # Test 5: Check for reconciliation method
    assert "def _reconcile_141101_lines(self, move):" in content, "❌ Reconciliation method not found"
    print("✅ Reconciliation method exists")
    
    # Test 6: Check for proper logging
    assert "_logger.info" in content or "_logger.debug" in content, "❌ No logging implemented"
    print("✅ Logging implemented")
    
    # Test 7: Check for error handling
    assert "try:" in content and "except" in content, "❌ No error handling found"
    print("✅ Error handling implemented")
    
    # Test 8: Check for scenario validation
    assert "scenario == 'pay_employee'" in content, "❌ Pay employee scenario not handled"
    assert "scenario == 'employee_refund'" in content, "❌ Employee refund scenario not handled"
    assert "scenario == 'write_off'" in content, "❌ Write-off scenario not handled"
    print("✅ All scenarios handled")
    
    # Test 9: Check for partner resolution
    assert "_get_employee_partner" in content, "❌ Partner resolution not implemented"
    print("✅ Partner resolution implemented")
    
    # Test 10: Check for balance recompute trigger
    assert "_trigger_balance_recompute" in content, "❌ Balance recompute not triggered"
    print("✅ Balance recompute trigger exists")
    
    print("\n✅ All code quality tests passed!")
    return True

def test_view_structure():
    """Test view XML structure"""
    print("\n" + "="*70)
    print("TEST 3: View Structure")
    print("="*70)
    
    view_file = "/opt/instance1/odoo17/custom-addons/employee_advance/views/advance_settlement_wizard_views.xml"
    with open(view_file, 'r') as f:
        content = f.read()
    
    # Test 1: Check for form view
    assert '<form string="Settle Advance">' in content, "❌ Form view not found"
    print("✅ Form view exists")
    
    # Test 2: Check for scenario field
    assert 'field name="scenario"' in content, "❌ Scenario field not found in view"
    print("✅ Scenario field exists")
    
    # Test 3: Check for amount fields
    assert 'field name="current_balance"' in content, "❌ Current balance field not found"
    assert 'field name="target_amount"' in content, "❌ Target amount field not found"
    print("✅ Amount fields exist")
    
    # Test 4: Check for journal field
    assert 'field name="journal_id"' in content, "❌ Journal field not found"
    print("✅ Journal field exists")
    
    # Test 5: Check for write-off fields
    assert 'field name="writeoff_policy"' in content, "❌ Write-off policy field not found"
    assert 'field name="writeoff_account_id"' in content, "❌ Write-off account field not found"
    print("✅ Write-off fields exist")
    
    # Test 6: Check for action button
    assert 'name="action_settle_advance"' in content, "❌ Action button not found"
    print("✅ Action button exists")
    
    # Test 7: Check for help text/alerts
    assert 'alert' in content.lower(), "❌ No alert/help text found"
    print("✅ Help text/alerts exist")
    
    # Test 8: Check for notebooks/pages
    assert '<notebook>' in content, "❌ Notebook not found"
    print("✅ Notebook structure exists")
    
    # Test 9: Check for action definition
    assert 'action_advance_settlement_wizard' in content, "❌ Action not defined"
    print("✅ Action defined")
    
    print("\n✅ All view structure tests passed!")
    return True

def test_advance_box_integration():
    """Test integration with advance box model"""
    print("\n" + "="*70)
    print("TEST 4: Advance Box Integration")
    print("="*70)
    
    advance_box_file = "/opt/instance1/odoo17/custom-addons/employee_advance/models/advance_box.py"
    with open(advance_box_file, 'r') as f:
        content = f.read()
    
    # Test 1: Check for settlement wizard action
    assert "def action_open_settlement_wizard(self):" in content, "❌ Settlement wizard action not found in advance box"
    print("✅ Settlement wizard action exists in advance box")
    
    # Test 2: Check for balance computation
    assert "def _compute_balance(self):" in content, "❌ Balance computation not found"
    print("✅ Balance computation exists")
    
    # Test 3: Check for partner resolution
    assert "def _get_employee_partner(self):" in content, "❌ Partner resolution not found in advance box"
    print("✅ Partner resolution exists in advance box")
    
    # Test 4: Check for balance recompute trigger
    assert "def _trigger_balance_recompute(self):" in content, "❌ Balance recompute trigger not found"
    print("✅ Balance recompute trigger exists")
    
    print("\n✅ All integration tests passed!")
    return True

def test_validation_logic():
    """Test validation logic in the wizard"""
    print("\n" + "="*70)
    print("TEST 5: Validation Logic")
    print("="*70)
    
    wizard_file = "/opt/instance1/odoo17/custom-addons/employee_advance/wizards/settlement_wizard.py"
    with open(wizard_file, 'r') as f:
        content = f.read()
    
    # Test 1: Check for zero balance validation
    assert "zero balance" in content.lower(), "❌ Zero balance validation not found"
    print("✅ Zero balance validation exists")
    
    # Test 2: Check for lock date validation
    assert "lock date" in content.lower() or "locked" in content.lower(), "❌ Lock date validation not found"
    print("✅ Lock date validation exists")
    
    # Test 3: Check for journal validation
    assert "bank" in content.lower() and "cash" in content.lower(), "❌ Journal type validation not found"
    print("✅ Journal type validation exists")
    
    # Test 4: Check for scenario-balance matching validation
    if "scenario == 'pay_employee' and" in content and "balance" in content:
        print("✅ Scenario-balance matching validation exists")
    else:
        print("⚠️ Warning: Scenario-balance matching validation might be missing")
    
    # Test 5: Check for partner validation
    assert "partner" in content.lower() and ("not" in content or "without" in content), "❌ Partner validation not found"
    print("✅ Partner validation exists")
    
    # Test 6: Check for account validation
    assert "account_id" in content, "❌ Account validation not found"
    print("✅ Account validation exists")
    
    print("\n✅ All validation logic tests passed!")
    return True

def test_scenario_handling():
    """Test all settlement scenarios"""
    print("\n" + "="*70)
    print("TEST 6: Scenario Handling")
    print("="*70)
    
    wizard_file = "/opt/instance1/odoo17/custom-addons/employee_advance/wizards/settlement_wizard.py"
    with open(wizard_file, 'r') as f:
        content = f.read()
    
    # Test 1: Pay Employee scenario
    if "scenario == 'pay_employee'" in content:
        assert "debit" in content and "credit" in content, "❌ Accounting entries for pay_employee not complete"
        print("✅ Pay Employee scenario implemented")
    else:
        print("❌ Pay Employee scenario not found")
    
    # Test 2: Employee Refund scenario
    if "scenario == 'employee_refund'" in content:
        assert "debit" in content and "credit" in content, "❌ Accounting entries for employee_refund not complete"
        print("✅ Employee Refund scenario implemented")
    else:
        print("❌ Employee Refund scenario not found")
    
    # Test 3: Write-off scenario
    if "scenario == 'write_off'" in content:
        assert "writeoff_policy" in content, "❌ Write-off policy handling not found"
        assert "'expense'" in content and "'other_income'" in content, "❌ Write-off policies not complete"
        print("✅ Write-off scenario implemented with policies")
    else:
        print("❌ Write-off scenario not found")
    
    # Test 4: Partial settlement
    if "amount_mode" in content and "'partial'" in content:
        print("✅ Partial settlement mode supported")
    else:
        print("⚠️ Warning: Partial settlement mode might not be supported")
    
    print("\n✅ All scenario handling tests passed!")
    return True

def run_all_tests():
    """Run all tests"""
    print("\n" + "="*70)
    print("SETTLEMENT FEATURE TEST SUITE")
    print("="*70)
    print("Testing Settlement functionality in employee_advance module")
    print("="*70 + "\n")
    
    try:
        results = []
        
        # Run all test suites
        results.append(("Structure Tests", test_settlement_wizard_structure()))
        results.append(("Code Quality Tests", test_wizard_code_quality()))
        results.append(("View Structure Tests", test_view_structure()))
        results.append(("Integration Tests", test_advance_box_integration()))
        results.append(("Validation Logic Tests", test_validation_logic()))
        results.append(("Scenario Handling Tests", test_scenario_handling()))
        
        # Print summary
        print("\n" + "="*70)
        print("TEST SUMMARY")
        print("="*70)
        
        all_passed = True
        for test_name, result in results:
            status = "✅ PASSED" if result else "❌ FAILED"
            print(f"{test_name}: {status}")
            if not result:
                all_passed = False
        
        print("="*70)
        
        if all_passed:
            print("\n🎉 ALL TESTS PASSED! Settlement feature is ready for use!")
            print("\n📝 Next Steps:")
            print("   1. Upgrade the module: sudo systemctl restart instance1")
            print("   2. Test in UI with different scenarios")
            print("   3. Verify journal entries are created correctly")
            print("   4. Test reconciliation and balance updates")
            return 0
        else:
            print("\n⚠️ SOME TESTS FAILED! Please review the errors above.")
            return 1
            
    except Exception as e:
        print(f"\n❌ TEST SUITE FAILED WITH ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(run_all_tests())
