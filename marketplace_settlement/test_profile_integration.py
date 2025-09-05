#!/usr/bin/env python3
"""
Test Profile Integration with Settlement Wizard
"""

def test_profile_integration():
    """Test that profile properly links with settlement wizard"""
    
    print("Testing Profile Integration with Settlement Wizard...")
    print("=" * 60)
    
    # Test cases to verify
    test_cases = [
        {
            'name': 'Profile onchange method exists',
            'check': 'Check if _onchange_profile method exists in wizard',
            'file': 'wizards/marketplace_settlement_wizard.py'
        },
        {
            'name': 'Profile field in wizard',
            'check': 'Check if profile_id field exists in wizard model',
            'file': 'wizards/marketplace_settlement_wizard.py'
        },
        {
            'name': 'Profile field in settlement',
            'check': 'Check if profile_id field exists in settlement model', 
            'file': 'models/settlement.py'
        },
        {
            'name': 'Profile field in wizard view',
            'check': 'Check if profile field is in wizard view',
            'file': 'views/marketplace_settlement_wizard_views.xml'
        },
        {
            'name': 'Profile field in settlement view',
            'check': 'Check if profile field is in settlement form view',
            'file': 'views/marketplace_settlement_wizard_views.xml'
        },
        {
            'name': 'Create settlement button in profile',
            'check': 'Check if profile has create settlement button',
            'file': 'views/profile_views.xml'
        },
        {
            'name': 'Profile action method',
            'check': 'Check if profile has action method to create settlement',
            'file': 'models/profile.py'
        }
    ]
    
    passed = 0
    total = len(test_cases)
    
    for i, test in enumerate(test_cases, 1):
        print(f"{i}. {test['name']}")
        
        try:
            with open(test['file'], 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Force print for first test
            if i == 1:
                print("   Checking onchange method...")
            
            # Test specific checks
            if 'onchange method' in test['check']:
                has_onchange = "@api.onchange('profile_id')" in content
                has_method = 'def _onchange_profile' in content
                print(f"   Decorator found: {has_onchange}")
                print(f"   Method found: {has_method}")
                if has_onchange and has_method:
                    print("   ✅ PASS: Profile onchange method found")
                    passed += 1
                else:
                    print("   ❌ FAIL: Profile onchange method not complete")
                    
            elif 'profile_id field exists in wizard' in test['check']:
                if 'profile_id = fields.Many2one' in content and 'marketplace.settlement.profile' in content:
                    print("   ✅ PASS: Profile field found in wizard")
                    passed += 1
                else:
                    print("   ❌ FAIL: Profile field not found in wizard")
                    
            elif 'profile_id field exists in settlement' in test['check']:
                if 'profile_id = fields.Many2one' in content and 'marketplace.settlement.profile' in content:
                    print("   ✅ PASS: Profile field found in settlement model")
                    passed += 1
                else:
                    print("   ❌ FAIL: Profile field not found in settlement model")
                    
            elif 'profile field is in wizard view' in test['check']:
                if 'field name="profile_id"' in content:
                    print("   ✅ PASS: Profile field found in wizard view")
                    passed += 1
                else:
                    print("   ❌ FAIL: Profile field not found in wizard view")
                    
            elif 'profile field is in settlement form view' in test['check']:
                if 'field name="profile_id"' in content:
                    print("   ✅ PASS: Profile field found in settlement view")
                    passed += 1
                else:
                    print("   ❌ FAIL: Profile field not found in settlement view")
                    
            elif 'create settlement button' in test['check']:
                if 'action_create_settlement_with_profile' in content:
                    print("   ✅ PASS: Create settlement button found")
                    passed += 1
                else:
                    print("   ❌ FAIL: Create settlement button not found")
                    
            elif 'action method to create settlement' in test['check']:
                if 'def action_create_settlement_with_profile' in content:
                    print("   ✅ PASS: Profile action method found")
                    passed += 1
                else:
                    print("   ❌ FAIL: Profile action method not found")
            
        except FileNotFoundError:
            print(f"   ❌ FAIL: File {test['file']} not found")
        except Exception as e:
            print(f"   ❌ ERROR: {e}")
    
    print("\n" + "=" * 60)
    print(f"PROFILE INTEGRATION TEST SUMMARY: {passed}/{total} tests passed")
    
    if passed == total:
        print("✅ Profile integration is properly implemented!")
        print("\nWorkflow Test:")
        print("1. Open Marketplace > Profiles")
        print("2. Select a profile and click 'Create Settlement'")
        print("3. Wizard should open with profile fields pre-populated")
        print("4. Change profile in wizard should update other fields")
        print("5. Created settlement should store profile reference")
        return True
    else:
        print("⚠️ Some profile integration tests failed")
        return False

if __name__ == '__main__':
    import os
    os.chdir('/opt/instance1/odoo17/custom-addons/marketplace_settlement')
    success = test_profile_integration()
    exit(0 if success else 1)
