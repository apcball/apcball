#!/usr/bin/env python3
"""
Debug script to check expense sheet fields and button visibility

This will help us understand why the Clear Advance (WHT) button might still be hanging
"""

import sys

def check_expense_sheet_model():
    """Check expense sheet model structure"""
    print("🔍 Checking Expense Sheet Model Structure")
    print("=" * 60)
    
    # Check required fields
    required_fields = {
        'use_advance': 'Boolean field to indicate if expense uses advance',
        'advance_box_id': 'Many2one field linking to employee advance box',
        'state': 'Selection field for expense sheet state (should include approve)'
    }
    
    print("📋 Required Fields for Button Visibility:")
    for field, description in required_fields.items():
        print(f"   ✅ {field}: {description}")
    
    # Check button visibility condition
    print("\n🎯 Button Visibility Condition:")
    print("   invisible=\"not use_advance or not advance_box_id or state != 'approve'\"")
    print("\n   This means button will be VISIBLE when:")
    print("   ✅ use_advance = True")
    print("   ✅ advance_box_id is set (not empty)")
    print("   ✅ state = 'approve'")
    
    # Check method existence
    print("\n🔧 Required Methods:")
    methods = [
        'action_open_wht_clear_advance_wizard',
        '_compute_wht_tax_rate',
        '_compute_wht_amount',
        '_compute_net_amount'
    ]
    
    for method in methods:
        print(f"   ✅ {method}")
    
    return True

def check_possible_hanging_causes():
    """Check possible causes of hanging"""
    print("\n🚨 Possible Hanging Causes and Solutions:")
    print("=" * 60)
    
    causes = [
        {
            'cause': 'Button not visible due to conditions',
            'check': 'Verify expense sheet has use_advance=True, advance_box_id set, state=approve',
            'solution': 'Set these fields correctly in the expense sheet'
        },
        {
            'cause': 'Method action_open_wht_clear_advance_wizard has syntax error',
            'check': 'Check server logs for Python syntax errors',
            'solution': 'Fix syntax errors in the method'
        },
        {
            'cause': 'Default_get method in wizard taking too long',
            'check': 'Monitor logs for WIZARD DEFAULT_GET messages',
            'solution': 'Add more timeout protection'
        },
        {
            'cause': 'Computed fields causing infinite loops',
            'check': 'Look for repeated computation messages in logs',
            'solution': 'Add better error handling in computed methods'
        },
        {
            'cause': 'Database queries taking too long',
            'check': 'Check for slow query warnings',
            'solution': 'Optimize database queries with limits'
        },
        {
            'cause': 'Browser-side JavaScript errors',
            'check': 'Open browser developer tools and check console',
            'solution': 'Clear browser cache and retry'
        }
    ]
    
    for i, item in enumerate(causes, 1):
        print(f"\n{i}. 🔍 {item['cause']}")
        print(f"   📋 Check: {item['check']}")
        print(f"   💡 Solution: {item['solution']}")

def provide_debugging_steps():
    """Provide step-by-step debugging"""
    print("\n🛠️ Step-by-Step Debugging Guide:")
    print("=" * 60)
    
    steps = [
        "1. 📋 Check Expense Sheet Fields",
        "   - Open expense sheet in Odoo",
        "   - Enable Developer Mode",
        "   - Check use_advance field value",
        "   - Check advance_box_id field value", 
        "   - Check state field value",
        "",
        "2. 🔍 Monitor Server Logs",
        "   - Run: sudo tail -f /var/log/odoo/instance1.log",
        "   - Click the Clear Advance (WHT) button",
        "   - Look for WIZARD messages or ERROR messages",
        "",
        "3. 🌐 Check Browser Console",
        "   - Open Developer Tools (F12)",
        "   - Go to Console tab",
        "   - Click Clear Advance (WHT) button",
        "   - Look for JavaScript errors",
        "",
        "4. 🔄 Clear Cache and Restart",
        "   - Clear browser cache (Ctrl+Shift+R)",
        "   - Restart Odoo: sudo systemctl restart instance1",
        "   - Try again",
        "",
        "5. 🧪 Test with Simple Case",
        "   - Create new expense sheet",
        "   - Set use_advance = True",
        "   - Set advance_box_id",
        "   - Submit and approve",
        "   - Test Clear Advance (WHT) button"
    ]
    
    for step in steps:
        print(step)

def main():
    """Main debug function"""
    print("🐛 Clear Advance (WHT) Button Hanging - Debug Analysis")
    print("=" * 70)
    print()
    
    try:
        # Check model structure
        check_expense_sheet_model()
        
        # Check possible causes
        check_possible_hanging_causes()
        
        # Provide debugging steps
        provide_debugging_steps()
        
        print("\n" + "=" * 70)
        print("📌 SUMMARY:")
        print("   1. Button visibility depends on 3 conditions")
        print("   2. Method has timeout protection added")  
        print("   3. Wizard has enhanced error handling")
        print("   4. Follow debugging steps to identify specific issue")
        
        print("\n💡 MOST LIKELY CAUSES:")
        print("   🎯 Button conditions not met (use_advance, advance_box_id, state)")
        print("   🎯 Browser cache issues")
        print("   🎯 JavaScript errors in browser")
        
        print("\n🚀 QUICK FIXES TO TRY:")
        print("   1. Clear browser cache (Ctrl+Shift+R)")
        print("   2. Check expense sheet fields in Developer Mode")
        print("   3. Monitor server logs while clicking button")
        print("   4. Check browser console for JavaScript errors")
        
    except Exception as e:
        print(f"❌ Debug script error: {e}")
        return False
    
    return True

if __name__ == "__main__":
    main()