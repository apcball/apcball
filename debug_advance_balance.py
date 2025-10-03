#!/usr/bin/env python3
"""
Debug script to check advance box balance calculation
"""
print("=== Advance Box Balance Debug ===")

# ตรวจสอบว่า advance box ID 1 มี journal entries อะไรบ้าง
# และคำนวณ balance อย่างไร

import sys
import os

# Let's check the advance box balance calculation logic
try:
    # Read the advance box model to understand balance computation
    with open('/opt/instance1/odoo17/custom-addons/employee_advance/models/advance_box.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    print("\n📊 Looking for balance computation in advance_box.py:")
    
    lines = content.split('\n')
    in_balance_method = False
    balance_lines = []
    
    for i, line in enumerate(lines):
        if '_compute_balance' in line or 'def balance' in line:
            in_balance_method = True
            balance_lines = []
            print(f"\n🔍 Found balance method at line {i+1}:")
        
        if in_balance_method:
            balance_lines.append(f"{i+1:3d}: {line}")
            
            # Stop when we hit the next method or significant indentation change
            if line.strip() and not line.startswith('    ') and not line.startswith('\t') and i > 0:
                if not line.strip().startswith('def ') and not line.strip().startswith('@'):
                    in_balance_method = False
                    break
    
    if balance_lines:
        print("\n".join(balance_lines))
    
    print("\n📊 Looking for account moves and partner matching:")
    for i, line in enumerate(lines):
        if 'account.move.line' in line or 'partner_id' in line:
            print(f"Line {i+1}: {line.strip()}")

except Exception as e:
    print(f"❌ Error: {e}")

print("\n=== End Debug ===")