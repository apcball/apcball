# 🔧 WHT Field Duplicate Issue Fixed

## ปัญหาที่พบ
มี field WHT ซ้ำกันใน module l10n_th_account_tax:

### Field ซ้ำ:
1. **`wht_tax_id`** - field เดิมที่มีอยู่แล้วใน `account_move.py` (บรรทัด 22)
2. **`wht_invoice_line_tax`** - field ใหม่ที่เราสร้างใน `account_move_odoo17.py`

## การแก้ไข ✅

### 1. รวม field เข้าด้วยกัน
- ลบ field `wht_invoice_line_tax` ออก
- ใช้ field `wht_tax_id` ที่มีอยู่แล้ว
- เพิ่มการทำงานใหม่ให้กับ field เดิม

### 2. แก้ไขไฟล์ที่เกี่ยวข้อง

#### `models/account_move_odoo17.py`:
- ลบ field definition `wht_invoice_line_tax`
- แก้ไข compute method ให้ใช้ `wht_tax_id`
- แก้ไข depends ให้ใช้ field เดิม
- แก้ไข fields_view_get ให้เพิ่ม `wht_tax_id` ลงใน tree view

#### `views/account_move_line_wht_view.xml`:
- เปลี่ยน `wht_invoice_line_tax` เป็น `wht_tax_id`
- ลบ domain `[('wht_account', '=', True)]` ที่ไม่มี field อยู่จริง

#### `views/wht_fields_direct.xml`:
- เปลี่ยน `wht_invoice_line_tax` เป็น `wht_tax_id`
- ลบ domain ที่ไม่ถูกต้อง

#### `models/__init__.py`:
- ลบ import `account_withholding_tax` ที่ไม่จำเป็น

### 3. ลบไฟล์ที่ไม่จำเป็น
- ลบ `models/account_withholding_tax.py` (ไม่จำเป็นแล้ว)

## ผลลัพธ์ 🎯

### ก่อนแก้ไข ❌:
- มี field WHT ซ้ำกัน 2 ตัว
- สับสนในการใช้งาน
- เกิด field conflict

### หลังแก้ไข ✅:
- ใช้ field `wht_tax_id` เดียว (field เดิมที่มีอยู่แล้ว)
- ไม่มี field ซ้ำ
- การทำงานยังคงเหมือนเดิม
- invoice line มี WHT field เต็มรูปแบบ

## การใช้งาน 📋

ตอนนี้ผู้ใช้สามารถ:
1. เลือก WHT ใน invoice line ผ่าน field `wht_tax_id`
2. ระบบคำนวณ WHT amount อัตโนมัติ
3. สร้าง Withholding Tax Moves ได้ถูกต้อง
4. ไม่มีความสับสนจาก field ซ้ำ

## ขั้นตอนถัดไป 🚀

1. **Upgrade Module**: Apps > l10n_th_account_tax > Upgrade
2. **ทดสอบ**: สร้าง invoice และเลือก WHT tax
3. **ตรวจสอบ**: Withholding Tax Move ถูกสร้างถูกต้อง

---
**สถานะ**: ✅ แก้ไขเสร็จสิ้น - พร้อมใช้งาน  
**เวลา**: $(date '+%Y-%m-%d %H:%M:%S')
