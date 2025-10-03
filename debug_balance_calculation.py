#!/usr/bin/env python3
"""
Debug script to check advance box balance calculation in detail
"""
print("=== Advance Box Balance Calculation Debug ===")

import sys
import os

try:
    # อ่าน advance_box.py เพื่อดูการคำนวณ balance
    with open('/opt/instance1/odoo17/custom-addons/employee_advance/models/advance_box.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    print("📊 Current Balance Calculation Logic:")
    print("=====================================")
    
    lines = content.split('\n')
    in_compute_balance = False
    
    for i, line in enumerate(lines):
        if '_compute_balance' in line and 'def' in line:
            in_compute_balance = True
            print(f"Found _compute_balance at line {i+1}")
            
        if in_compute_balance:
            print(f"{i+1:3d}: {line}")
            
            # หาจุดจบของ method
            if line.strip() and not line.startswith('    ') and not line.startswith('\t') and 'def ' in line and i > 0:
                if not '_compute_balance' in line:
                    break
                    
            # หยุดเมื่อเจอ method ถัดไป
            if line.strip().startswith('def ') and '_compute_balance' not in line and in_compute_balance and i > 0:
                break
                
            if line.strip() == '' and i > 0:
                next_lines = lines[i+1:i+3]
                if any(line.strip().startswith('def ') for line in next_lines):
                    break
    
    print("\n🔍 Key Points to Check:")
    print("======================")
    print("1. Account ID ใช้ถูกต้องหรือไม่ (113001 เงินทดรองจ่าย)")
    print("2. Partner ID หาถูกต้องหรือไม่")
    print("3. Journal Entry State = 'posted' หรือไม่")
    print("4. Debit/Credit คำนวณถูกต้องหรือไม่")
    
    print("\n💡 Recommended Odoo Shell Commands to Debug:")
    print("============================================")
    print("# 1. ตรวจสอบ Advance Box")
    print("advance_box = env['employee.advance.box'].browse(1)")
    print("print(f'Employee: {advance_box.employee_id.name}')")
    print("print(f'Account: {advance_box.account_id.code} - {advance_box.account_id.name}')")
    print("print(f'Current Balance: {advance_box.balance}')")
    print()
    
    print("# 2. ตรวจสอบ Employee Partner")
    print("employee = advance_box.employee_id")
    print("print(f'Employee Name: {employee.name}')")
    print("print(f'User Partner: {employee.user_id.partner_id.name if employee.user_id else None}')")
    print("print(f'User Partner ID: {employee.user_id.partner_id.id if employee.user_id else None}')")
    print()
    
    print("# 3. หา Partner ตามชื่อ Employee")
    print("employee_partners = env['res.partner'].search([('name', '=', employee.name), ('is_company', '=', False)])")
    print("print(f'Employee Partners: {[(p.id, p.name) for p in employee_partners]}')")
    print()
    
    print("# 4. ตรวจสอบ Account Move Lines")
    print("account = advance_box.account_id")
    print("all_lines = env['account.move.line'].search([")
    print("    ('account_id', '=', account.id),")
    print("    ('move_id.state', '=', 'posted')")
    print("])")
    print("print(f'Total lines for account {account.code}: {len(all_lines)}')")
    print()
    
    print("# 5. ตรวจสอบ Lines ตาม Partner")
    print("for partner_id in [employee.user_id.partner_id.id if employee.user_id else None] + [p.id for p in employee_partners]:")
    print("    if partner_id:")
    print("        partner = env['res.partner'].browse(partner_id)")
    print("        lines = env['account.move.line'].search([")
    print("            ('account_id', '=', account.id),")
    print("            ('move_id.state', '=', 'posted'),")
    print("            ('partner_id', '=', partner_id)")
    print("        ])")
    print("        total_debit = sum(lines.mapped('debit'))")
    print("        total_credit = sum(lines.mapped('credit'))")
    print("        balance = total_debit - total_credit")
    print("        print(f'Partner {partner.name} (ID: {partner_id}): Debit {total_debit}, Credit {total_credit}, Balance {balance}')")
    print("        for line in lines:")
    print("            print(f'  {line.date} | {line.move_id.name} | Dr: {line.debit} | Cr: {line.credit} | {line.name}')")
    
except Exception as e:
    print(f"❌ Error: {e}")

print("\n=== End Debug ===")