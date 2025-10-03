#!/usr/bin/env python3
"""
Debug script to check expense sheet vendor bill structure
"""
print("=== Expense Sheet Vendor Bill Debug ===")

# Let's examine what might be in the expense sheet
import sys
import os

# Add the module path
sys.path.append('/opt/instance1/odoo17')
sys.path.append('/opt/instance1/odoo17/custom-addons')

try:
    # Read the expense sheet model to see relationships
    with open('/opt/instance1/odoo17/custom-addons/employee_advance/models/expense_sheet.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    print("\n📋 Looking for account_move relationships in expense_sheet.py:")
    
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if 'account_move' in line.lower() or 'vendor' in line.lower() or 'bill' in line.lower():
            print(f"Line {i+1}: {line.strip()}")
    
    print("\n📋 Looking for relationship field definitions:")
    for i, line in enumerate(lines):
        if 'Many2one' in line and ('account.move' in line or 'move' in line):
            # Show context around the field definition
            start = max(0, i-2)
            end = min(len(lines), i+3)
            print(f"\nLines {start+1}-{end}:")
            for j in range(start, end):
                marker = ">>> " if j == i else "    "
                print(f"{marker}{j+1:3d}: {lines[j]}")

except Exception as e:
    print(f"❌ Error: {e}")

print("\n=== End Debug ===")