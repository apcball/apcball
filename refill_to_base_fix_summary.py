#!/usr/bin/env python3
"""
Summary of Refill to Base button fix - แก้ปัญหากดปุ่ม Refill to Base แล้วยอดเงินไม่ขึ้น
"""

print("=== REFILL TO BASE BUG FIXES ===")

print("""
🐛 ปัญหาที่เจอ: กดปุ่ม "Refill to Base" แต่ยอดเงินไม่ขึ้น

🔧 การแก้ไขที่ทำ:

1. แก้ไข partner_id ใน wizard (advance_refill_base_wizard.py):
   - เปลี่ยนจาก: 'partner_id': partner
   - เป็น: 'partner_id': partner.id if partner else False
   
2. เพิ่ม debug logging ใน wizard เพื่อติดตาม:
   - การสร้าง journal entry
   - Partner ID ที่ใช้
   - Balance ก่อนและหลัง refill
   
3. แก้ไข _refresh_balance_simple ให้บังคับคำนวณใหม่:
   - เปลี่ยนจากการ invalidate อย่างเดียว
   - เป็นการเรียก _compute_balance() โดยตรง
   
4. เพิ่มการเช็ค credit account:
   - เช็ค default_account_id ของ journal
   - Fallback ไปใช้ company cash account
   - แจ้ง error ถ้าไม่มี account
   
5. เพิ่ม extensive logging เพื่อ debug:
   - ใน advance_box.py _compute_balance
   - ใน refill wizard action_confirm
   - ใน balance refresh methods

📝 ไฟล์ที่แก้ไข:
- employee_advance/models/advance_box.py
- employee_advance/wizards/advance_refill_base_wizard.py

🔍 วิธีทดสอบ:
1. กดปุ่ม "Refill to Base" 
2. ดู Odoo log จะเห็น debug messages
3. เช็คว่า journal entry ถูกสร้างและ post
4. เช็คว่า balance อัพเดทถูกต้อง

💡 สาเหตุที่เป็นไปได้:
- Partner ID ไม่ใช่ integer (ส่ง object แทน)
- Credit account ไม่ถูกต้อง
- Balance ไม่ได้ recompute หลัง journal entry
- Account move line ไม่ match กับ search criteria

🎯 ผลลัพธ์ที่คาดหวัง:
- กดปุ่ม Refill to Base แล้วยอดเงินขึ้น
- Journal entry ถูกสร้างและ post
- Balance calculation ถูกต้อง
""")

print("\n=== Test Commands ===")
test_commands = '''
# เทสต์ใน Odoo shell:
box = env['employee.advance.box'].browse(1)  # เปลี่ยน ID ตามต้องการ
print("Before refill:", box.balance)

# กดปุ่ม Refill to Base ผ่าน UI แล้ว...

box.invalidate_recordset(['balance'])
print("After refill:", box.balance)

# เช็ค journal entries ที่สร้างล่าสุด
recent_moves = env['account.move'].search([
    ('create_date', '>=', datetime.now() - timedelta(hours=1)),
    ('ref', 'ilike', 'Refill Advance')
], order='create_date desc')

for move in recent_moves:
    print(f"Move: {move.name} | State: {move.state}")
    for line in move.line_ids:
        print(f"  Account: {line.account_id.code} | Partner: {line.partner_id.name if line.partner_id else None}")
        print(f"  Debit: {line.debit} | Credit: {line.credit}")
'''

print(test_commands)