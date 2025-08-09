# WHT Certificate Module สำหรับ Odoo 17

## สรุปการปรับปรุงโมดูล l10n_th_account_tax

### ฟีเจอร์หลักที่ปรับปรุงแล้ว

#### 1. Smart Buttons ใน Payment Form
- **Generate WHT Cert**: ปุ่มสำหรับสร้าง WHT Certificate ด้วยตนเอง
- **View WHT Certificates**: ปุ่มสำหรับดู WHT Certificates ที่สร้างแล้ว
- **WHT Cert Counter**: แสดงจำนวน WHT Certificates

#### 2. การสร้าง WHT Certificate อัตโนมัติ
- สร้างอัตโนมัติเมื่อ **Post Payment** ที่มี Withholding Tax
- เงื่อนไข: Payment ต้องมี `wht_move_ids` (Withholding Tax Moves)

#### 3. การสร้าง WHT Certificate ด้วยตนเอง
- ใช้ปุ่ม "Generate WHT Cert" ใน Payment form
- แสดง notification ผลลัพธ์ (สำเร็จ/ข้อผิดพลาด)

### ไฟล์ที่ปรับปรุง

#### Models
- `account_payment_wht.py` - ฟังก์ชัน WHT Certificate generation
- `account_payment.py` - ปรับปรุง action_post และเพิ่ม helper methods
- `account_move.py` - auto-create WHT cert from payment
- `account_withholding_move.py` - ปรับปรุงการหา payment
- `withholding_tax_cert.py` - Model หลักของ WHT Certificate

#### Views
- `account_payment_view.xml` - เพิ่ม Smart Buttons และ Alert Messages

#### Security
- `ir.model.access.csv` - ลบ access rules ที่ไม่ใช้

### วิธีการใช้งาน

#### 1. สร้าง Vendor Bill ที่มี WHT Tax
```
1. สร้าง Vendor Bill
2. เพิ่ม Product/Service ที่มี WHT Tax
3. Post Bill
4. ระบบจะสร้าง Withholding Tax Moves อัตโนมัติ
```

#### 2. Register Payment
```
1. ไปที่ Vendor Bill
2. คลิก "Register Payment"
3. กรอกข้อมูล Payment
4. คลิก "Create Payment"
5. Payment จะถูก Post และสร้าง WHT Certificate อัตโนมัติ
```

#### 3. สร้าง WHT Certificate ด้วยตนเอง
```
1. ไปที่ Payment ที่มี Withholding Tax
2. คลิกปุ่ม "Generate WHT Cert" (Smart Button)
3. ระบบจะสร้าง WHT Certificate
4. สามารถดู Certificate ที่สร้างได้ด้วยปุ่ม "WHT Certificate"
```

### เงื่อนไขสำคัญ

#### Payment ต้องมี:
- `wht_move_ids` (Withholding Tax Moves)
- สถานะเป็น `posted`
- `payment_type` เป็น `outbound`

#### WHT Certificate จะสร้างเมื่อ:
- Payment มี Withholding Tax Moves
- ยังไม่มี WHT Certificate อยู่ก่อน
- Payment ถูก Post สำเร็จ

### การแก้ไขปัญหา

#### ถ้า Smart Button ไม่แสดง:
1. ตรวจสอบว่า Payment มี `wht_move_ids` หรือไม่
2. ตรวจสอบ `payment_type` ต้องเป็น `outbound`
3. ตรวจสอบ Payment ต้องอยู่ในสถานะ `posted`

#### ถ้าไม่สร้าง WHT Certificate อัตโนมัติ:
1. ตรวจสอบ Vendor Bill มี WHT Tax หรือไม่
2. ตรวจสอบว่ามี Withholding Tax Moves ใน Payment หรือไม่
3. ดู Log ของ Odoo สำหรับข้อผิดพลาด

### Log Files
- `/var/log/odoo/instance1.log` - สำหรับตรวจสอบข้อผิดพลาด

### ความคิดเห็น
Module นี้ได้รับการปรับปรุงให้ทำงานได้บน Odoo 17 และใช้งานได้จริง โดยมีการ:
- ลบ dependencies ที่ไม่จำเป็น
- แก้ไข field และ method ที่ไม่มีจริง
- เพิ่ม error handling ที่ดีขึ้น
- ปรับปรุง UI/UX ให้ใช้งานง่ายขึ้น
