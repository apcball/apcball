# สรุปการแก้ไข VAT Undue Module

## ปัญหาที่พบ
จากการตรวจสอบ Journal Entry ที่สร้างจาก "Clear Undue VAT" พบว่า:

**❌ การลงบัญชีผิด:**
- บัญชี 116600 (VAT Undue): Debit 0.00, Credit 70.00 ✓
- บัญชี 111002 (Bank Suspense - Automatic Balancing Line): Debit 70.00 ✗

**✅ การลงบัญชีที่ถูกต้อง:**
- บัญชี 116600 (VAT Undue): Debit 0.00, Credit 70.00 
- บัญชี 116400 (Input VAT): Debit 70.00, Credit 0.00

## สาเหตุ
1. Journal Entry ที่สร้างไม่ได้ใช้บัญชี Input VAT ที่กำหนดไว้
2. ระบบสร้าง Automatic Balancing Line แทน
3. ขาด validation ก่อนสร้าง entry

## การแก้ไข

### 1. ปรับปรุง Logic ใน `action_use_vat()` (tax_undue_line.py)

**เพิ่ม Validation:**
- ตรวจสอบว่าบัญชี Undue และ Input VAT ต้องไม่เหมือนกัน
- ตรวจสอบ amount ต้องมีค่ามากกว่า 0
- ตรวจสอบว่า Journal Entry ต้องมี 2 lines เท่านั้น
- ตรวจสอบว่า Debit = Credit (balance)
- ตรวจสอบว่าใช้บัญชีที่ถูกต้อง

**แก้ไข Debit/Credit Logic:**
```python
# กรณีปกติ: ภาษีซื้อ
# Dr 116400 Input VAT    (เพิ่มยอด Input VAT)
# Cr 116600 VAT Undue    (ลดยอด VAT Undue)

if amount > 0:
    line_1_debit = amount_abs   # Input VAT
    line_1_credit = 0.0
    line_2_debit = 0.0
    line_2_credit = amount_abs  # VAT Undue
```

### 2. สร้าง Diagnostic Wizard

**ฟีเจอร์:**
- 🔍 ตรวจสอบ Journal Entries ที่มี VAT Undue
- ✅ ตรวจสอบว่าใช้บัญชีที่ถูกต้องหรือไม่
- ✅ ตรวจสอบ Debit/Credit ว่าถูกต้องหรือไม่
- ✅ ตรวจสอบ Balance
- 🔧 แก้ไขปัญหาอัตโนมัติ (ยกเลิกและสร้างใหม่)

**วิธีใช้งาน:**
1. ไปที่เมนู: Accounting → Configuration → VAT Undue → 🔍 ตรวจสอบความถูกต้อง
2. คลิก "🔍 ตรวจสอบ" เพื่อสแกนหา issues
3. หาก found issues:
   - คลิก "📋 ดูรายการที่มีปัญหา" เพื่อดู entries
   - คลิก "🔧 แก้ไขปัญหาทั้งหมด" เพื่อแก้ไขอัตโนมัติ

### 3. เพิ่ม Validation ก่อน Post Journal Entry

ระบบจะตรวจสอบก่อน post:
- Journal Entry ต้อง balance (Debit = Credit)
- ต้องมี 2 lines เท่านั้น
- ต้องใช้บัญชีที่ถูกต้อง (Input VAT และ VAT Undue)

หาก validation ไม่ผ่าน ระบบจะ:
- ลบ Journal Entry ที่สร้าง
- แสดง error message ที่ชัดเจน

## ไฟล์ที่แก้ไข

1. **models/tax_undue_line.py**
   - แก้ไข `action_use_vat()` method
   - เพิ่ม validation logic
   - แก้ไข Debit/Credit calculation

2. **wizard/vat_undue_diagnostic_wizard.py** (ใหม่)
   - สร้าง diagnostic wizard
   - ตรวจสอบ Journal Entries
   - แก้ไขปัญหาอัตโนมัติ

3. **wizard/vat_undue_diagnostic_wizard_views.xml** (ใหม่)
   - Form view สำหรับ wizard
   - Menu item

4. **__manifest__.py**
   - เพิ่ม wizard view file

5. **security/ir.model.access.csv**
   - เพิ่ม access rights สำหรับ wizard

## การทดสอบ

### ทดสอบการสร้าง Journal Entry ใหม่:
1. สร้าง Vendor Bill ที่มี VAT Undue
2. Post bill
3. ไปที่ Tax Undue Lines
4. เลือก line และคลิก "Use VAT"
5. ตรวจสอบ Journal Entry ที่สร้าง:
   - ✅ ต้องมี 2 lines
   - ✅ Dr 116400 (Input VAT)
   - ✅ Cr 116600 (VAT Undue)
   - ✅ Debit = Credit

### ทดสอบ Diagnostic Wizard:
1. ไปที่เมนู Diagnostic
2. คลิก "ตรวจสอบ"
3. ระบบจะแสดงรายการที่มีปัญหา (ถ้ามี)
4. คลิก "แก้ไขปัญหาทั้งหมด" เพื่อแก้ไข

## คำแนะนำ

1. **Upgrade Module:**
   ```bash
   sudo -u odoo /opt/instance1/odoo17/odoo-bin -c /etc/instance1.conf \
     -d YOUR_DATABASE -u buz_th_vat_undue --stop-after-init
   ```

2. **ตรวจสอบ Tax Configuration:**
   - ไปที่ Accounting → Configuration → Taxes
   - เลือก "7% undue" tax
   - ตรวจสอบว่า:
     - ✅ Is VAT Undue: checked
     - ✅ Target VAT Tax: 7% (ภาษีซื้อปกติ)
     - ✅ Input VAT Account: 116400 ภาษีซื้อ

3. **แก้ไข Journal Entries เก่า:**
   - ใช้ Diagnostic Wizard
   - หรือยกเลิกและสร้างใหม่ด้วยตนเอง

## FAQ

**Q: ทำไม Journal Entry เก่าถึงใช้บัญชี Bank Suspense?**
A: เพราะ Journal Entry ไม่ balance หรือมี configuration ผิด ระบบจึงสร้าง Automatic Balancing Line

**Q: จะแก้ไข Journal Entry เก่าอย่างไร?**
A: ใช้ Diagnostic Wizard หรือยกเลิกและสร้างใหม่ด้วย action_use_vat()

**Q: ถ้า validation error ต้องทำอย่างไร?**
A: ตรวจสอบ Tax Configuration ว่าตั้งค่า Input VAT Account ถูกต้องหรือไม่
