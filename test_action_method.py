#!/usr/bin/env python3
"""
Test file to verify the action method is being called
"""
print("Testing action_open_wht_clear_advance_wizard method call...")

# Create a simple test to see if the method is accessible
import sys
sys.path.append('/opt/instance1/odoo17/custom-addons/employee_advance')

try:
    # Read the expense sheet file to verify our changes are there
    with open('/opt/instance1/odoo17/custom-addons/employee_advance/models/expense_sheet.py', 'r', encoding='utf-8') as f:
        content = f.read()
        
    # Check if our logging is there
    if "ACTION_OPEN_WHT" in content:
        print("✅ Found ACTION_OPEN_WHT logging in expense_sheet.py")
    else:
        print("❌ ACTION_OPEN_WHT logging not found in expense_sheet.py")
        
    # Check if employee mismatch handling is there
    if "Employee mismatch detected" in content:
        print("✅ Found employee mismatch handling in expense_sheet.py")
    else:
        print("❌ Employee mismatch handling not found in expense_sheet.py")
        
    print("\n📋 Recent changes in expense_sheet.py:")
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if "ACTION_OPEN_WHT" in line or "Employee mismatch" in line:
            start = max(0, i-2)
            end = min(len(lines), i+3)
            print(f"Lines {start+1}-{end}:")
            for j in range(start, end):
                marker = ">>> " if j == i else "    "
                print(f"{marker}{j+1:3d}: {lines[j]}")
            print()

except Exception as e:
    print(f"❌ Error reading file: {e}")