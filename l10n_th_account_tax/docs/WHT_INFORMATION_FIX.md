# 🔧 แก้ปัญหา Withholding Tax Information แสดง 0.00 ฿

## ปัญหา: Withholding Tax Information แสดง
```
Total Withholding Base: 0.00 ฿
Total Withholding Tax: 0.00 ฿
```

### สาเหตุ: ระบบมี 2 WHT systems ทำงานไม่ sync กัน

1. **ระบบเดิม:** `wht_tax_id` (ใน l10n_th_account_tax)
2. **ระบบใหม่:** `withholding_tax_id` (ใน account_move_odoo17.py)

---

## 🚀 วิธีแก้ไขด่วน

### Option 1: รัน Fix Script
```bash
cd /opt/instance1/odoo17
./odoo-bin shell -d your_database --no-http
```

```python
# รัน Fix Script
exec(open('/opt/instance1/odoo17/custom-addons/l10n_th_account_tax/tools/fix_wht_information_display.py').read())
```

### Option 2: Manual Fix ในหน้าเว็บ

1. **เปิด Bill ที่มี WHT Tax**
2. **Edit Invoice Line**
3. **ตรวจสอบ WHT Tax field มีค่า**
4. **Save line**
5. **Refresh หน้า (F5)**

---

## 🔍 การตรวจสอบปัญหา

### ขั้นตอนที่ 1: ตรวจสอบ Invoice Lines

ใน Bill ที่มีปัญหา ตรวจสอบ:

```
Invoice Lines Table:
┌─────────────────┬────────────┬──────────────┐
│ Product         │ Price      │ WHT Tax      │
├─────────────────┼────────────┼──────────────┤
│ ค่าบริการ       │ 10,000.00  │ Service 3%   │ ✅ ต้องมีค่า
└─────────────────┴────────────┴──────────────┘
```

### ขั้นตอนที่ 2: ตรวจสอบ WHT Tax Configuration

1. **ไปที่:** `Accounting → Configuration → WHT Configuration → WHT Tax Types`
2. **ตรวจสอบ:** มี Service WHT 3% หรือไม่
3. **ตรวจสอบ:** มี Account กำหนดไว้หรือไม่

### ขั้นตอนที่ 3: ตรวจสอบ Product Configuration

1. **ไปที่:** `Inventory → Master Data → Products`
2. **เลือก Service Product**
3. **ตรวจสอบ Purchase Tab:**
   - Supplier Company WHT Tax: ต้องมีค่า
   - Supplier Individual WHT Tax: ต้องมีค่า

---

## 🛠️ การแก้ไขแบบ Manual

### Fix 1: กำหนด WHT Tax ให้ Invoice Lines

**สำหรับ Bills ที่มีอยู่:**

1. **เปิด Bill**
2. **Edit Invoice Line**
3. **กำหนด WHT Tax field**
4. **Save line**
5. **ตรวจสอบ Withholding Tax Information**

### Fix 2: อัปเดต Product Configuration

**สำหรับ Products ที่ยังไม่มี WHT:**

```python
# ใน Odoo Shell
service_wht = env['account.withholding.tax'].search([('amount', '=', 3)], limit=1)

for product in env['product.template'].search([('type', '=', 'service')]):
    product.write({
        'supplier_company_wht_tax_id': service_wht.id,
        'supplier_wht_tax_id': service_wht.id,
    })
```

### Fix 3: Force Recompute WHT Totals

**สำหรับ Bills ที่มี WHT แต่ไม่แสดงยอด:**

```python
# ใน Odoo Shell
bills = env['account.move'].search([
    ('move_type', '=', 'in_invoice'),
    ('invoice_line_ids.wht_tax_id', '!=', False),
])

for bill in bills:
    # Force recompute
    bill.line_ids._compute_withholding_tax_amount()
    bill._compute_withholding_totals()
```

---

## 🎯 ผลลัพธ์ที่คาดหวัง

### หลังแก้ไขแล้ว Bill ควรแสดง:

```
Withholding Tax Information:
┌─────────────────────────────┬─────────────┐
│ Total Withholding Base      │ 10,000.00 ฿ │
│ Total Withholding Tax       │    300.00 ฿ │
└─────────────────────────────┴─────────────┘
```

### คำนวณ:
- **Service 3%:** 10,000 × 3% = 300 ฿
- **Rental 5%:** 20,000 × 5% = 1,000 ฿

---

## 🚨 Troubleshooting

### ปัญหา: ยังแสดง 0.00 หลังแก้ไข

**วิธีแก้ไข:**

1. **Clear Browser Cache** (Ctrl + F5)
2. **Restart Odoo Server:**
   ```bash
   sudo systemctl restart odoo17
   ```
3. **Update Module:**
   - Apps → l10n_th_account_tax → Upgrade

### ปัญหา: WHT Tax field ไม่แสดง

**วิธีแก้ไข:**

1. **เปิด Column Settings** (⚙️ icon)
2. **เปิด "WHT Tax" checkbox**
3. **Save preferences**

### ปัญหา: Invoice Lines ไม่มี WHT Tax

**วิธีแก้ไข:**

```python
# Auto-assign WHT Tax
service_wht = env['account.withholding.tax'].search([('amount', '=', 3)], limit=1)

for line in env['account.move.line'].search([
    ('move_id.move_type', '=', 'in_invoice'),
    ('product_id.type', '=', 'service'),
    ('wht_tax_id', '=', False),
]):
    line.wht_tax_id = service_wht.id
```

---

## ✅ Checklist การแก้ไข

- [ ] ✅ WHT Tax Types มีอยู่และมี Account
- [ ] ✅ Products มี WHT Tax configuration  
- [ ] ✅ Invoice Lines มี WHT Tax assigned
- [ ] ✅ WHT Tax field แสดงใน Bill
- [ ] ✅ Withholding Tax Information แสดงยอดถูกต้อง
- [ ] ✅ Payment Register auto-deduct WHT
- [ ] ✅ Browser cache cleared
- [ ] ✅ Module updated

---

## 📋 การทดสอบ

### Test Case: สร้าง Bill ใหม่

1. **สร้าง Vendor Bill:**
   ```
   - Product: Service ที่มี WHT Tax
   - Quantity: 1
   - Price: 10,000 ฿
   ```

2. **ตรวจสอบผลลัพธ์:**
   ```
   ✅ WHT Tax: Service 3%
   ✅ Total Withholding Base: 10,000.00 ฿
   ✅ Total Withholding Tax: 300.00 ฿
   ```

3. **ทดสอบ Payment:**
   ```
   - Original: 10,000 ฿
   - WHT Deduction: 300 ฿
   - Payment Amount: 9,700 ฿ ✅
   ```

---

## 🎉 สรุป

**หลังจากแก้ไขแล้ว:**
- ✅ Withholding Tax Information แสดงยอดถูกต้อง
- ✅ รองรับทั้ง 2 ระบบ WHT 
- ✅ Auto-sync ระหว่าง `wht_tax_id` และ `withholding_tax_id`
- ✅ Payment Register ทำงานถูกต้อง

**WHT System พร้อมใช้งานเต็มรูปแบบ!** 🚀
