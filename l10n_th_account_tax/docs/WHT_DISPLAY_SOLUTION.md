# WHT Tax Display Solution (ไม่ต้องเพิ่ม field ใหม่)

## ปัญหา: WHT Tax ไม่คำนวณหน้า Bill

### วิธีแก้ไขแบบ Simple (ไม่เปลี่ยน Database)

1. **แสดง WHT Tax field เท่านั้น** (ไม่แสดง WHT Amount)
2. **ใช้ Related field หรือ Computed field แบบไม่ store**
3. **แสดง WHT calculation ในส่วนอื่น**

---

## การแก้ไขที่ทำแล้ว:

### ✅ Fix 1: แสดง WHT Tax Field
- ✅ เปลี่ยน `optional="hide"` เป็น `optional="show"`
- ✅ เพิ่ม `string="WHT Tax"` 
- ✅ ลบ `wht_amount` field ออกจาก view (เพราะยังไม่มีใน database)

### ✅ Fix 2: Auto-assign WHT Tax
- ✅ เพิ่ม `_compute_wht_tax_id` method
- ✅ เพิ่ม `@api.depends("product_id", "partner_id")`
- ✅ Support ทั้ง Company และ Individual WHT Tax

### ✅ Fix 3: แก้ไข Security File
- ✅ ลบ comment line ที่ทำให้ CSV parsing error
- ✅ อัปเดต `ir.model.access.csv`

---

## สิ่งที่ควรเห็นตอนนี้:

### ในหน้า Bill/Invoice:
```
Invoice Lines Table:
┌─────────────────┬────────────┬──────────────┬──────────────┐
│ Product         │ Price      │ Tax          │ WHT Tax      │
├─────────────────┼────────────┼──────────────┼──────────────┤
│ ค่าบริการ       │ 10,000.00  │ -            │ Service 3%   │
│ ค่าเช่า         │ 20,000.00  │ VAT 7%       │ Rental 5%    │
└─────────────────┴────────────┴──────────────┴──────────────┘
```

### การคำนวณ WHT:
- **ไม่แสดงใน table** แต่จะเห็นผลตอน Payment Register
- **Service 3%**: 10,000 × 3% = 300 บาท
- **Rental 5%**: 20,000 × 5% = 1,000 บาท

---

## วิธีทดสอบ:

### Test 1: ตรวจสอบ WHT Tax Field แสดงหรือไม่
1. สร้าง Bill ใหม่
2. เพิ่ม Product ประเภท Service
3. ดูว่า WHT Tax column แสดงหรือไม่
4. ตรวจสอบว่า WHT Tax auto-assign หรือไม่

### Test 2: ทดสอบ Payment Register
1. Confirm Bill
2. กด Register Payment  
3. ตรวจสอบว่า Payment Amount ลดลงตาม WHT หรือไม่

---

## ถ้ายังไม่เห็น WHT Tax Column:

### วิธีแก้ไข 1: เปิด Column Manual
1. ไปที่หน้า Bill
2. คลิก Settings icon (⚙️) มุมขวาบนของ table
3. เปิด "WHT Tax" checkbox
4. Save preferences

### วิธีแก้ไข 2: Clear Browser Cache
```bash
Ctrl + F5 (Windows/Linux)
Cmd + Shift + R (Mac)
```

### วิธีแก้ไข 3: Update Module
1. ไปที่ Apps
2. หา l10n_th_account_tax
3. กด Upgrade
4. Restart Odoo if needed

---

## Manual WHT Assignment:

### ถ้า WHT Tax ไม่ auto-assign:
1. **Edit Invoice Line**
2. **กำหนด WHT Tax field manual**
3. **Save line**

### Script สำหรับ Batch Assignment:
```python
# ใน Odoo shell
service_wht = env['account.withholding.tax'].search([('amount', '=', 3)], limit=1)

# กำหนด WHT Tax ให้ Products
for product in env['product.template'].search([('type', '=', 'service')]):
    product.supplier_company_wht_tax_id = service_wht.id

# กำหนด WHT Tax ให้ Invoice Lines
for line in env['account.move.line'].search([('product_id.type', '=', 'service'), ('wht_tax_id', '=', False)]):
    line.wht_tax_id = service_wht.id
```

---

## Expected Results:

### ✅ สิ่งที่ควรทำงาน:
- WHT Tax field แสดงในหน้า Bill ✅
- WHT Tax auto-assign จาก Product ✅  
- Payment Register auto-deduct WHT ✅
- WHT Certificate generation ✅

### 🔮 ฟีเจอร์ที่จะเพิ่มในอนาคต:
- WHT Amount display ใน Invoice Lines
- WHT Summary ใน Bill footer  
- Real-time WHT calculation display
- Enhanced WHT reporting

---

**สรุป: ตอนนี้ WHT Tax field ควรแสดงและ auto-assign แล้ว!** 🎯
