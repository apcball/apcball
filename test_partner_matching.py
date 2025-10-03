#!/usr/bin/env python3
"""
Test script to check advance box partner vs journal entry partner
"""
print("=== Partner Matching Test ===")

# ค้นหา journal entries ล่าสุดที่เกี่ยวข้องกับ account 113001 (เงินทดรองจ่าย)
# และ partner_id ต่างๆ

import sys
import subprocess

try:
    print("\n🔍 Searching for recent journal entries with account 113001...")
    
    # ค้นหา journal entries ที่เกี่ยวข้องกับเงินทดรองจ่าย
    cmd = "sudo journalctl -u instance1 --no-pager -n 200 | grep -E 'Credit Advance Box|📥.*113001|partner_id.*113001' || echo 'No logs found'"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    if result.stdout.strip() != 'No logs found':
        print("Found logs:")
        print(result.stdout)
    else:
        print("⚠️ No specific logs found")
    
    print("\n🔍 Checking if there are any account.move.line entries for account 113001...")
    print("(This would show what partner_ids are actually in the system)")
    
    # ดูว่ามี account.move.line อะไรบ้างสำหรับ account 113001
    print("\n💡 To check partner matching, we should look at:")
    print("1. Advance Box Employee: นภัคสรณ์ วชิรพันธ์วิชาญ")
    print("2. Journal Entry Partner: Napaksorn")
    print("3. Are they the same res.partner record with different display names?")
    
    print("\n📋 Suggested SQL queries to run in Odoo shell:")
    print("# Find advance box employee partner")
    print("employee = env['hr.employee'].search([('name', '=', 'นภัคสรณ์ วชิรพันธ์วิชาญ')])")
    print("print(f'Employee: {employee.name}')")
    print("print(f'User Partner: {employee.user_id.partner_id.name if employee.user_id else None}')")
    print("print(f'Home Address: {employee.address_home_id.name if hasattr(employee, \"address_home_id\") and employee.address_home_id else None}')")
    
    print("\n# Find Napaksorn partner")
    print("napaksorn = env['res.partner'].search([('name', 'ilike', 'Napaksorn')])")
    print("print(f'Napaksorn partners: {[(p.id, p.name) for p in napaksorn]}')")
    
    print("\n# Check account moves for account 113001")
    print("account = env['account.account'].search([('code', '=', '113001')])")
    print("moves = env['account.move.line'].search([('account_id', '=', account.id), ('create_date', '>=', '2025-10-03')])")
    print("for move in moves:")
    print("    print(f'Date: {move.date}, Partner: {move.partner_id.name}, Debit: {move.debit}, Credit: {move.credit}')")

except Exception as e:
    print(f"❌ Error: {e}")

print("\n=== End Test ===")