#!/usr/bin/env python3
"""
Partner Mismatch Issue Fix - แก้ปัญหา Partner ไม่ตรงกันระหว่าง Journal Entry กับ Balance Calculation
"""

print("=== PARTNER MISMATCH ISSUE ===")

print("""
🐛 ปัญหา: Refill to Base สร้าง Journal Entry แต่ยอดเงินไม่ขึ้น

🔍 สาเหตุ:
1. Refill Wizard ใช้ _get_employee_partner() → return User Partner ID
2. Balance Calculation ใช้ Employee Partner (search by name)
3. Partner ที่ต่างกัน → Journal Entry ไม่ match กับ Balance Calculation

📋 Evidence จาก Journal Entry:
- Account: 113001 เงินทดรองจ่าย
- Partner: Napaksorn (User Partner)
- Debit: 51,070.00 ฿

- Account: 112000 เงินฝากธนาคาร  
- Partner: (ไม่มี Partner)
- Credit: 51,070.00 ฿

🔧 การแก้ไข:
ใน advance_refill_base_wizard.py แก้ให้ใช้ Partner logic เดียวกันกับ _compute_balance:

1. หา Employee Partner ที่มีชื่อเดียวกับ Employee ก่อน
2. ถ้าไม่เจอ ใช้ fallback method เดิม
3. ใช้ Partner ID เดียวกันสำหรับทั้ง Journal Entry และ Balance Calculation

💡 Logic ที่ถูกต้อง:
- ใช้ Employee Partner (name match) เป็นหลัก
- Fallback ไปใช้ User Partner ถ้าจำเป็น
- ให้ Journal Entry และ Balance Calculation ใช้ Partner เดียวกัน

🎯 ผลลัพธ์ที่คาดหวัง:
- Journal Entry ใช้ Partner เดียวกันกับ Balance Calculation
- Refill to Base ทำให้ยอดเงินขึ้นถูกต้อง
- Debug log แสดงการใช้ Partner ที่ consistent

🔍 วิธีเช็ค Partner ที่ถูกต้อง:
1. ดู Balance Calculation debug log → Partner ID ไหน
2. ดู Refill debug log → Partner ID ไหน  
3. เช็คว่า Partner ID ตรงกันไหม
4. ดู Journal Entry ที่สร้างใช้ Partner ID เดียวกันไหม
""")

print("\n=== Debug Commands ===")
debug_commands = '''
# เช็ค Employee Partner vs User Partner
employee = env['hr.employee'].search([('name', '=', 'นฤศรณ์ วชิรพันธุวิชัย')], limit=1)
print("Employee:", employee.name)

# Employee Partner (ใช้ใน Balance Calculation)
employee_partner = env['res.partner'].search([
    ('name', '=', employee.name),
    ('is_company', '=', False)
], limit=1)
print("Employee Partner:", employee_partner.name if employee_partner else "Not Found", "ID:", employee_partner.id if employee_partner else None)

# User Partner (ใช้ใน _get_employee_partner)
if employee.user_id:
    print("User Partner:", employee.user_id.partner_id.name, "ID:", employee.user_id.partner_id.id)

# เช็ค Journal Entries ล่าสุด
recent_moves = env['account.move'].search([
    ('ref', 'ilike', 'Refill Advance'),
    ('create_date', '>=', datetime.now() - timedelta(hours=1))
], order='create_date desc', limit=1)

for move in recent_moves:
    print(f"\\nMove: {move.name}")
    for line in move.line_ids:
        print(f"  Account: {line.account_id.code} | Partner: {line.partner_id.name if line.partner_id else 'No Partner'} | ID: {line.partner_id.id if line.partner_id else None}")
        print(f"  Debit: {line.debit} | Credit: {line.credit}")
'''

print(debug_commands)