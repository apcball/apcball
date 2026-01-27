# การวิเคราะห์ Credit Note กับ VAT Undue

## 📋 Overview

เมื่อต้องการออก Credit Note (CN) สำหรับ Vendor Bill ที่มี VAT Undue จะมี 2 กรณีหลัก:
1. **Case 11.1**: VAT Undue ยัง**ไม่ถูก Use** (state=undue)
2. **Case 11.2**: VAT Undue **ถูก Use ไปแล้ว** (state=used) → **มี Tax Invoice ออกไปแล้ว**

---

## 🎯 Scenario: Credit Note หลังจาก Use VAT

### สถานการณ์ตัวอย่าง

```
Step 1: สร้าง Vendor Bill
----------------------------------------
Date: 2025-01-01
Vendor: ABC Co., Ltd.
Tax Invoice: SINV-2025-001
Tax Date: 2025-01-01

Items:
- Product A: 1,000.00
- VAT Undue 7%: 70.00
Total: 1,070.00

Journal Entry (Bill):
Dr Expenses (510100)      1,000.00
Dr VAT Undue (116600)        70.00
   Cr Payable (211100)              1,070.00

Tax Undue Line:
- Tax Invoice No: SINV-2025-001
- Tax Date: 2025-01-01
- Tax Amount: 70.00
- State: undue
- Remaining: 70.00


Step 2: จ่ายเงิน (Payment)
----------------------------------------
Date: 2025-01-15

Journal Entry (Payment):
Dr Payable (211100)      1,070.00
   Cr Bank (110100)                1,070.00


Step 3: Use VAT (Convert Undue → Input VAT)
----------------------------------------
Date: 2025-01-20 (Accounting Date ที่ User เลือก)

Journal Entry (Clearing):
Dr Input VAT (116400)       70.00
   Cr VAT Undue (116600)           70.00

Tax Invoice Created:
- Move: JV/2025/0015
- Tax Invoice Number: SINV-2025-001
- Tax Invoice Date: 2025-01-20 ← Accounting Date จาก Wizard
- Tax Base: 1,000.00
- Tax Amount: 70.00
- ✅ ปรากฏใน Tax Report (PP30)

Tax Undue Line Updated:
- Used Tax Amount: 70.00
- State: used
- Remaining: 0.00


Step 4: ต้องการ Credit Note (ยกเลิกบิล)
----------------------------------------
Date: 2025-01-25
Reason: สินค้าเสียหาย, ส่งคืนทั้งหมด

❓ จะต้องทำอย่างไร?
```

---

## 🔍 การวิเคราะห์ Logic (Case 11.2)

### ปัญหาที่ต้องแก้

1. ✅ **Bill ต้นฉบับถูก Cancel/Reverse**
   - Dr Payable 1,070.00
   - Cr Expenses 1,000.00
   - Cr VAT Undue 70.00

2. ⚠️ **Input VAT ที่ออก Tax Invoice ไปแล้วต้องถูก Reverse**
   - Tax Invoice SINV-2025-001 ปรากฏใน PP30 แล้ว
   - ต้องสร้างรายการ Credit เพื่อ offset

3. ⚠️ **VAT Undue Account ต้อง Balance**
   - Bill CN: Cr 116600 (70.00) → ลดยอด Debit
   - Use VAT: Cr 116600 (70.00) → ลดยอด Debit อีก
   - ❌ จะเกิดยอด Credit เกิน!

---

## 💡 Logic ที่ Module ใช้ (ตาม Code)

### Code Location: `_handle_vat_undue_refund()` และ `_create_refund_vat_reclassification()`

```python
# File: models/account_move.py, line 135-225

def _handle_vat_undue_refund(self):
    reversed_move = self.reversed_entry_id  # Bill ต้นฉบับ
    if reversed_move:
        undue_lines = self.env['tax.undue.line'].search([
            ('move_id', '=', reversed_move.id)
        ])
        
        if undue_lines:
            all_unused = all(l.state == 'undue' for l in undue_lines)
            
            if all_unused:
                # Case 11.1: ยังไม่ Use VAT
                # → สร้าง Tax Undue Line แบบลบ (negative)
                created_cn_lines = self._create_vat_undue_lines()
                # ... (update refunded_tax_amount)
            else:
                # Case 11.2: Use VAT ไปแล้ว
                # → สร้าง Reclassification Entry
                self._create_refund_vat_reclassification(undue_lines)
```

### Reclassification Logic

```python
def _create_refund_vat_reclassification(self, original_undue_lines):
    """
    สร้าง Journal Entry เพื่อ reclassify 
    จาก Undue Account ไปเป็น Input VAT Account
    """
    move_lines = []
    
    for line in self.line_ids:  # Credit Note lines
        if line.tax_line_id and line.tax_line_id.is_vat_undue:
            # CN: line.balance เป็น Credit (ลบ)
            amount = abs(line.balance)  # 70.00
            
            # สร้าง reclassification lines
            move_lines.extend([
                (0, 0, {
                    'name': "Reclassify Undue to Input VAT",
                    'account_id': line.account_id.id,  # 116600 (Undue)
                    'debit': amount,   # Dr 70.00
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': "Input VAT Refund",
                    'account_id': input_vat_account.id,  # 116400 (Input VAT)
                    'debit': 0.0,
                    'credit': amount,  # Cr 70.00
                    'tax_tag_ids': [(6, 0, rep_line.tag_ids.ids)],
                    'tax_repartition_line_id': rep_line.id,
                }),
            ])
            
            # อัพเดท used_tax_amount ของ original undue lines
            matching_undue = original_undue_lines.filtered(
                lambda l: l.tax_id == line.tax_line_id and l.state != 'undue'
            )
            for undue_line in matching_undue:
                # ลด used amount กรณี refund
                undue_line.used_tax_amount -= amount  # 70 - 70 = 0
    
    # สร้าง Journal Entry
    reclass_move = self.env['account.move'].create({
        'journal_id': journal.id,
        'date': self.date,  # วันที่ของ CN
        'ref': "VAT Reclassification for Refund: [CN Number]",
        'move_type': 'entry',
        'line_ids': move_lines,
    })
    reclass_move.action_post()
```

---

## 📊 ตัวอย่าง Journal Entries ทั้งหมด

### 1. Original Bill (2025-01-01)
```
Dr Expenses (510100)      1,000.00
Dr VAT Undue (116600)        70.00
   Cr Payable (211100)              1,070.00
```

### 2. Payment (2025-01-15)
```
Dr Payable (211100)      1,070.00
   Cr Bank (110100)                1,070.00
```

### 3. Use VAT - Clearing Entry (2025-01-20)
```
Dr Input VAT (116400)       70.00
   Cr VAT Undue (116600)           70.00

✅ Tax Invoice: SINV-2025-001, Date: 2025-01-20
✅ ปรากฏใน PP30
```

### 4. Credit Note (2025-01-25)
```
Dr Payable (211100)      1,070.00
   Cr Expenses (510100)            1,000.00
   Cr VAT Undue (116600)              70.00
```

### 5. Reclassification Entry (2025-01-25) - **สร้างอัตโนมัติ**
```
Dr VAT Undue (116600)       70.00
   Cr Input VAT (116400)           70.00

✅ มี Tax Tags เพื่อ offset Tax Report
✅ กลับรายการ Input VAT
```

---

## 📈 ยอดคงเหลือในบัญชี

### Account 116600 (VAT Undue)
```
Bill:         Dr  70.00  |  Balance:  70.00 Dr
Use VAT:             70.00 Cr  Balance:   0.00
CN:                  70.00 Cr  Balance:  70.00 Cr ← เกิน!
Reclass:      Dr  70.00  |  Balance:   0.00 ✅
```

### Account 116400 (Input VAT)
```
Use VAT:      Dr  70.00  |  Balance:  70.00 Dr
Reclass:             70.00 Cr  Balance:   0.00 ✅
```

### Tax Report (PP30)
```
Use VAT Entry:    Input VAT +70.00
Reclass Entry:    Input VAT -70.00
Net Effect:       0.00 ✅
```

---

## ⚠️ ปัญหาที่ต้องตรวจสอบ

### 1. ❓ Tax Invoice Record ต้องทำอย่างไร?

**ปัจจุบัน:**
- Tax Invoice สร้างที่ Use VAT Entry (JV/2025/0015)
- Reclassification Entry ไม่ได้สร้าง Tax Invoice ใหม่
- ใช้ Tax Tags เพื่อ offset ใน Tax Report

**คำถาม:**
- ต้องสร้าง Tax Invoice Record สำหรับ Reclassification Entry หรือไม่?
- หรือใช้ Tax Tags อย่างเดียวพอ?

### 2. ❓ Tax Invoice Date ใน Reclassification Entry

**ปัจจุบัน:**
- Reclassification Entry ใช้ date จาก Credit Note (2025-01-25)
- Tax Tags ถูกใช้เพื่อ offset ใน Tax Report

**คำถาม:**
- วันที่ใน Tax Report ควรเป็นวันที่ไหน?
  - วันที่ Use VAT (2025-01-20)?
  - วันที่ Credit Note (2025-01-25)?

### 3. ❓ Partial Credit Note

**Scenario:**
- Bill: 1,000 + VAT 70 = 1,070
- Use VAT: 70
- CN: คืนเพียง 500 + VAT 35 = 535

**คำถาม:**
- Reclassification ควร offset เพียง 35 บาท
- Tax Undue Line: used_tax_amount = 70 - 35 = 35
- ต้อง handle partial refund

---

## ✅ สรุป Logic

### Case 11.1: VAT Undue ยังไม่ Use (state=undue)
```
1. สร้าง CN ปกติ (Cr VAT Undue)
2. สร้าง Tax Undue Line แบบลบ
3. Update Original Tax Undue Line:
   - refunded_tax_amount += 35
   - remaining_tax_amount = 70 - 0 - 35 = 35
   - state = undue (ยังคงเป็น undue)
```

### Case 11.2: VAT Undue ถูก Use แล้ว (state=used)
```
1. สร้าง CN ปกติ (Cr VAT Undue)
2. สร้าง Reclassification Entry อัตโนมัติ:
   - Dr VAT Undue (ลดยอด Cr จาก CN)
   - Cr Input VAT (กลับรายการ Input VAT)
   - มี Tax Tags เพื่อ offset Tax Report
3. Update Original Tax Undue Line:
   - used_tax_amount -= 35 (ลดยอดที่ใช้)
   - remaining_tax_amount เพิ่มขึ้น
4. ❓ Tax Invoice Record (ต้องตรวจสอบ)
```

---

## 🔧 สิ่งที่ต้องแก้ไข/ปรับปรุง

### 1. ✅ สร้าง Tax Invoice Record สำหรับ Reclassification Entry

เพิ่มใน `_create_refund_vat_reclassification()`:

```python
# หลังจาก post reclassification entry
if input_vat_line:
    # สร้าง tax invoice record สำหรับ offset
    tax_invoice_vals = {
        'move_id': reclass_move.id,
        'move_line_id': input_vat_line.id,
        'partner_id': self.partner_id.id,
        'tax_invoice_number': original_tax_invoice_number,
        'tax_invoice_date': self.date,  # CN date
        'tax_base_amount': -original_tax_base,  # ลบ
        'balance': -amount,  # ลบ
    }
    self.env['account.move.tax.invoice'].create(tax_invoice_vals)
```

### 2. ✅ Handle Partial Credit Note

ปรับปรุงใน `_create_refund_vat_reclassification()` ให้ handle partial refund:

```python
for line in self.line_ids:
    if line.tax_line_id and line.tax_line_id.is_vat_undue:
        cn_amount = abs(line.balance)  # จำนวนใน CN
        
        # หา original undue lines ที่ used แล้ว
        matching_undue = original_undue_lines.filtered(
            lambda l: l.tax_id == line.tax_line_id and l.state == 'used'
        )
        
        # จัดสรร cn_amount ไปยัง original lines
        remaining_cn = cn_amount
        for undue_line in matching_undue:
            if remaining_cn <= 0:
                break
            
            # คำนวณจำนวนที่จะ offset
            offset_amount = min(remaining_cn, undue_line.used_tax_amount)
            
            if offset_amount > 0:
                # สร้าง reclassification entry
                # ...
                
                # อัพเดท undue line
                undue_line.used_tax_amount -= offset_amount
                remaining_cn -= offset_amount
```

### 3. 📝 Documentation & Testing

- เขียน Test Case สำหรับ CN หลัง Use VAT
- เอกสารคู่มือสำหรับ User
- ทดสอบ Partial Credit Note

---

## 📞 ข้อสรุป

**Logic ปัจจุบัน (v17.0.1.0.5):**
- ✅ มี logic handle Credit Note หลัง Use VAT
- ✅ สร้าง Reclassification Entry อัตโนมัติ
- ⚠️ ยังไม่สร้าง Tax Invoice Record สำหรับ Reclassification
- ⚠️ อาจมีปัญหากับ Partial CN

**ควรปรับปรุง:**
1. เพิ่มการสร้าง Tax Invoice Record
2. Handle Partial Credit Note ให้ดีขึ้น
3. เพิ่ม Test Cases
4. เพิ่มเอกสารคู่มือ User
