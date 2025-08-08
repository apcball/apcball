# 🔧 แก้ปัญหา WHT Tax ไม่คำนวณในหน้า Bill

## ปัญหา: WHT Tax ไม่คำนวณหน้า Bill ทั้งที่ใส่ WHT แล้ว

### สาเหตุที่เป็นไปได้:

1. **WHT Tax field ถูกซ่อนในหน้า Bill**
2. **Product ไม่ได้ตั้งค่า WHT Tax**
3. **Invoice Lines ไม่มี WHT Tax assigned**
4. **WHT Amount computation ไม่ทำงาน**
5. **View ไม่แสดง WHT fields**

---

## 🚀 วิธีแก้ไขด่วน (Quick Fix)

### Option 1: รัน Fix Script
```bash
cd /opt/instance1/odoo17
./odoo-bin shell -d your_database --no-http
```

```python
# รัน Quick Fix Script
exec(open('/opt/instance1/odoo17/custom-addons/l10n_th_account_tax/tools/quick_fix_wht_bill.py').read())
```

### Option 2: รัน Test Script
```python
# รัน Comprehensive Test Script
exec(open('/opt/instance1/odoo17/custom-addons/l10n_th_account_tax/tools/test_wht_bill_calculation.py').read())
```

---

## 🔍 การแก้ไขแบบ Manual

### ขั้นตอนที่ 1: ตรวจสอบ WHT Tax Types

1. **ไปที่:** `Accounting → Configuration → WHT Configuration → WHT Tax Types`

2. **ตรวจสอบ:**
   - มี Service WHT 3% และ Rental WHT 5%
   - แต่ละ WHT Tax มี Account กำหนดไว้

3. **ถ้าไม่มี WHT Tax Types:**
   ```
   สร้างใหม่:
   - Name: Service WHT 3%
   - Amount: 3
   - Account: WHT Tax Payable Account
   ```

### ขั้นตอนที่ 2: ตั้งค่า Product WHT Tax

1. **ไปที่:** `Inventory → Master Data → Products`

2. **เลือก Product ประเภท Service**

3. **ใน Purchase Tab ตั้งค่า:**
   ```
   - Supplier Company WHT Tax: Service WHT 3%
   - Supplier Individual WHT Tax: Service WHT 3%
   ```

4. **Save Product**

### ขั้นตอนที่ 3: ตรวจสอบ View Settings

1. **ในหน้า Bill/Invoice:**
   - คลิก Settings icon (⚙️) ขวาบนของ table
   - เปิด "WHT Tax" column
   - เปิด "WHT Amount" column

2. **ถ้าไม่มี WHT columns:**
   - Module อาจจะยังไม่ Update
   - ต้อง Update Module l10n_th_account_tax

### ขั้นตอนที่ 4: แก้ไข Draft Bills ที่มีอยู่

1. **หา Draft Bills ที่ยังไม่มี WHT:**
   ```
   Accounting → Vendors → Bills
   Filter: State = Draft
   ```

2. **Edit แต่ละ Invoice Line:**
   - เปิด Bill
   - คลิกแก้ไข Invoice Line
   - กำหนด WHT Tax field
   - Save line

3. **ตรวจสอบ WHT Amount:**
   - ควรแสดง WHT Amount ที่คำนวณได้
   - เช่น: 10,000 × 3% = 300

---

## 🛠️ การแก้ไขแบบ Technical

### Fix 1: อัปเดต View เพื่อแสดง WHT Fields

แก้ไขไฟล์: `views/account_move_view.xml`
```xml
<!-- เปลี่ยนจาก optional="hide" เป็น optional="show" -->
<field name="wht_tax_id" optional="show" string="WHT Tax"/>
<field name="wht_amount" optional="show" string="WHT Amount"/>
```

### Fix 2: เพิ่ม WHT Amount Computation

แก้ไขไฟล์: `models/account_move.py`
```python
@api.depends("wht_tax_id", "price_subtotal")
def _compute_wht_amount(self):
    for rec in self:
        if rec.wht_tax_id and rec.price_subtotal:
            rec.wht_amount = rec.price_subtotal * (rec.wht_tax_id.amount / 100)
        else:
            rec.wht_amount = 0
```

### Fix 3: เพิ่ม Auto-assign WHT Tax

```python
@api.onchange('product_id')
def _onchange_product_id_wht(self):
    if self.product_id and self.move_id.move_type == 'in_invoice':
        partner = self.move_id.partner_id
        if partner.company_type == 'company':
            self.wht_tax_id = self.product_id.supplier_company_wht_tax_id
        else:
            self.wht_tax_id = self.product_id.supplier_wht_tax_id
```

---

## ✅ การทดสอบหลังแก้ไข

### Test Case 1: สร้าง Bill ใหม่

1. **สร้าง Vendor Bill:**
   ```
   - Vendor: เลือก Company Type
   - Product: เลือก Service ที่มี WHT Tax
   - Quantity: 1
   - Price: 10,000
   ```

2. **ตรวจสอบผลลัพธ์:**
   ```
   ✅ WHT Tax column แสดง: Service WHT 3%
   ✅ WHT Amount column แสดง: 300.00
   ✅ Price Subtotal: 10,000.00
   ```

### Test Case 2: Manual WHT Assignment

1. **สร้าง Bill ไม่มี WHT:**
   - ใช้ Product ที่ไม่มี WHT Tax

2. **กำหนด WHT Tax manual:**
   - Edit Invoice Line
   - เลือก WHT Tax: Service WHT 3%
   - Save line

3. **ตรวจสอบ:**
   - WHT Amount ต้องคำนวณทันที

---

## 🚨 Troubleshooting

### ปัญหา: WHT Amount = 0 ทั้งที่มี WHT Tax

**สาเหตุ:**
- `_compute_wht_amount` method ไม่ทำงาน
- Field dependencies ไม่ถูกต้อง

**แก้ไข:**
```python
# Force recompute
bill.invoice_line_ids._compute_wht_amount()
```

### ปัญหา: WHT Tax columns ไม่แสดง

**สาเหตุ:**
- View ยังไม่ update
- Module ยังไม่ update

**แก้ไข:**
```bash
# Update Module
./odoo-bin -d your_database -u l10n_th_account_tax --stop-after-init

# Restart Server
sudo systemctl restart odoo17
```

### ปัญหา: WHT Tax ไม่ auto-assign

**สาเหตุ:**
- Product ไม่มี WHT Tax configuration
- `_compute_wht_tax_id` method ไม่ทำงาน

**แก้ไข:**
```python
# Manual assign ใน Odoo shell
for product in env['product.template'].search([('type', '=', 'service')]):
    wht_tax = env['account.withholding.tax'].search([('amount', '=', 3)], limit=1)
    product.supplier_company_wht_tax_id = wht_tax.id
```

---

## 📋 Checklist การแก้ไข

- [ ] ✅ WHT Tax Types มีอยู่และมี Account
- [ ] ✅ Products มี WHT Tax configuration
- [ ] ✅ WHT fields แสดงใน Bill view
- [ ] ✅ WHT Amount คำนวณถูกต้อง
- [ ] ✅ Auto-assign WHT Tax ทำงาน
- [ ] ✅ Manual assign WHT Tax ทำงาน
- [ ] ✅ Draft Bills มี WHT calculation
- [ ] ✅ Module updated และ Server restarted

---

## 🎯 ผลลัพธ์ที่คาดหวัง

### หน้า Bill แสดง:
```
Invoice Lines:
┌─────────────────┬────────────┬──────────────┬─────────────┐
│ Product         │ Price      │ WHT Tax      │ WHT Amount  │
├─────────────────┼────────────┼──────────────┼─────────────┤
│ ค่าบริการ       │ 10,000.00  │ Service 3%   │ 300.00      │
│ ค่าเช่า         │ 20,000.00  │ Rental 5%    │ 1,000.00    │
└─────────────────┴────────────┴──────────────┴─────────────┘
Total: 30,000.00
Total WHT: 1,300.00
```

### เมื่อทำ Payment:
```
- Original Amount: 30,000.00
- WHT Deduction: 1,300.00
- Payment Amount: 28,700.00 ✅
```

---

**หลังจากแก้ไขแล้ว WHT Tax จะคำนวณและแสดงผลในหน้า Bill ได้เรียบร้อย!** 🎉
