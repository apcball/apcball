# Credit Note Netting Fix - Marketplace Settlement

## Issue Description
เมื่อมี **Credit Note (in_refund)** ใน Vendor Bills ระบบคำนวณยอด netting ไม่ถูกต้อง

### ตัวอย่างปัญหา:
- **Customer Receivables**: 2,850.00
- **Vendor Bills**: 
  - Bill 1: 300.00 (regular in_invoice)
  - Credit Note 1: -100.00 (in_refund)
  - **Net Payables**: 200.00
- **คาดหวัง**: Netting JE ควรลง 200.00
- **ปัญหา**: Netting JE ลง 300.00 (ไม่ได้หัก credit note)

---

## Root Cause

### ปัญหาในโค้ดเดิม

```python
# โค้ดเดิมที่ผิด
for line in bill_payable_lines:
    if line.credit > 0:  # We owe marketplace
        total_payable_amount += line.credit
```

**สาเหตุ:**
1. โค้ดเดิมดูจาก **journal entry lines** โดยตรง
2. สำหรับ **Credit Note**, payable line จะเป็น **Debit** (ลด AP) ไม่ใช่ Credit
3. เงื่อนไข `if line.credit > 0` จะไม่เจอ credit note เลย
4. ทำให้ credit note ไม่ถูกหักออกจากยอด payable

---

## Solution

### แก้ไขโดยใช้ `move_type` และ `amount_residual`

```python
# โค้ดใหม่ที่ถูกต้อง
for bill in self.vendor_bill_ids:
    if bill.state != 'posted':
        continue
    
    # คำนวณตาม bill type
    if bill.move_type == 'in_invoice':
        # Regular vendor bill - เพิ่มยอดที่เราต้องจ่าย
        bill_payable_amount = abs(bill.amount_residual)
    elif bill.move_type == 'in_refund':
        # Credit note - ลดยอดที่เราต้องจ่าย (ติดลบ)
        bill_payable_amount = -abs(bill.amount_residual)
    
    total_payable_amount += bill_payable_amount
```

---

## Changes Made

### 1. แก้ไข `_create_netting_move()` Method

**Location:** `models/settlement.py` ~line 1570

**Before:**
```python
for line in bill_payable_lines:
    if line.credit > 0:  # We owe marketplace
        total_payable_amount += line.credit
        netting_lines.append((0, 0, {
            'name': f'Net-off AP: {line.name}',
            'account_id': line.account_id.id,
            'partner_id': marketplace_partner.id,
            'debit': line.credit,
            'credit': 0.0,
        }))
```

**After:**
```python
for bill in self.vendor_bill_ids:
    if bill.state != 'posted':
        continue
    
    bill_payable_amount = 0.0
    
    if bill.move_type == 'in_invoice':
        bill_payable_amount = abs(bill.amount_residual)
        payable_debug_info.append(f"Bill {bill.name} (IN_INVOICE): +{bill_payable_amount}")
    elif bill.move_type == 'in_refund':
        bill_payable_amount = -abs(bill.amount_residual)
        payable_debug_info.append(f"Bill {bill.name} (IN_REFUND/Credit Note): {bill_payable_amount}")
    
    total_payable_amount += bill_payable_amount
```

### 2. ปรับปรุงการสร้าง Netting Journal Entry

**Before:**
```python
netting_amount = min(total_receivable_amount, total_payable_amount)
```

**After:**
```python
# Use absolute value เผื่อกรณี credit notes ทำให้ติดลบ
netting_amount = min(total_receivable_amount, abs(total_payable_amount))
```

### 3. ยืนยันว่า `_compute_amounts()` ใช้ตรรกะเดียวกัน

ตรวจสอบแล้วว่าการคำนวณ `total_vendor_bills` ใน `_compute_amounts()` ใช้ตรรกะเดียวกัน:

```python
if bill.move_type == 'in_refund':
    total_vendor_bills -= abs(bill_amount)
else:
    total_vendor_bills += abs(bill_amount)
```

---

## Expected Behavior After Fix

### ตัวอย่าง Test Case

**Scenario:**
- Settlement Receivables: 2,850.00
- Vendor Bill #1: 300.00
- Credit Note #1: -100.00

**Expected Results:**

1. **Settlement View:**
   - Customer Receivables: 2,850.00
   - Vendor Payables: **200.00** ✅ (300 - 100)
   - Net Payout Amount: 2,650.00

2. **Netting Journal Entry:**
   ```
   Dr. AP (เจ้าหนี้การค้า)    200.00  ✅
   Cr. AR (ลูกหนี้การค้า)    200.00  ✅
   ```

3. **Debug Log:**
   ```
   Bill BILL001 (IN_INVOICE): +300.0
   Bill CN001 (IN_REFUND/Credit Note): -100.0
   Total Payable Amount (after credit notes): 200.0
   Expected Netting Amount: 200.0
   ```

---

## Testing Instructions

### 1. Create Test Data

```python
# Create settlement with vendor bills including credit note
settlement = env['marketplace.settlement'].search([('name', '=', 'TEST-SETTLE-001')])

# Create regular vendor bill
bill1 = env['account.move'].create({
    'move_type': 'in_invoice',
    'partner_id': settlement.marketplace_partner_id.id,
    'invoice_date': fields.Date.today(),
    'x_settlement_id': settlement.id,
    'invoice_line_ids': [(0, 0, {
        'name': 'Marketplace Fee',
        'price_unit': 300.00,
        'quantity': 1,
    })]
})
bill1.action_post()

# Create credit note
credit_note = env['account.move'].create({
    'move_type': 'in_refund',
    'partner_id': settlement.marketplace_partner_id.id,
    'invoice_date': fields.Date.today(),
    'x_settlement_id': settlement.id,
    'invoice_line_ids': [(0, 0, {
        'name': 'Fee Adjustment',
        'price_unit': 100.00,
        'quantity': 1,
    })]
})
credit_note.action_post()
```

### 2. Verify Calculations

```python
# Check total_vendor_bills
settlement._compute_amounts()
print(f"Total Vendor Bills: {settlement.total_vendor_bills}")
# Expected: 200.00 (300 - 100)

# Perform netting
settlement.action_netoff_ar_ap()

# Check netting move amount
netting_move = settlement.netting_move_id
print(f"Netting Amount: {netting_move.amount_total}")
# Expected: 200.00
```

### 3. Visual Verification

1. เปิด Settlement form
2. ตรวจสอบ **Netting Details** tab:
   - Customer Receivables: แสดงถูกต้อง
   - Vendor Payables: **200.00** (ไม่ใช่ 300.00)
   - Net Payout Amount: คำนวณถูกต้อง

3. เปิด Netting Journal Entry
4. ตรวจสอบ Journal Items:
   - Debit AP: **200.00** ✅
   - Credit AR: **200.00** ✅

---

## Edge Cases Covered

### 1. Multiple Credit Notes
```
Bill 1: +500.00
Credit Note 1: -100.00
Credit Note 2: -50.00
Total: 350.00 ✅
```

### 2. Credit Note > Bill Amount
```
Bill 1: +200.00
Credit Note 1: -300.00
Total: -100.00 (ติดลบ - ต้อง handle ด้วย abs())
```

### 3. Only Credit Notes
```
Credit Note 1: -100.00
Total: -100.00 (ใช้ abs() ใน netting_amount calculation)
```

### 4. Mixed Bills and Credit Notes
```
Bill 1: +1000.00
Bill 2: +500.00
Credit Note 1: -200.00
Credit Note 2: -100.00
Total: 1200.00 ✅
```

---

## Impact Analysis

### ✅ Benefits

1. **Accurate Netting:** Netting amount ถูกต้องตาม vendor bills จริง
2. **Proper Accounting:** Journal entries reflect true outstanding amounts
3. **Credit Note Support:** รองรับ credit notes อย่างถูกต้อง
4. **Consistency:** `total_vendor_bills` ใน UI ตรงกับ netting JE
5. **Better Debugging:** มี logs แสดงรายละเอียดการคำนวณ

### ⚠️ Considerations

1. **Existing Netted Settlements:** 
   - Settlements ที่ netted ไปแล้วจะไม่ได้รับผลกระทบ
   - Netting moves ที่มีอยู่แล้วจะไม่เปลี่ยนแปลง

2. **Performance:**
   - ไม่มีผลกระทบต่อ performance
   - ยังคงใช้ amount_residual ที่ compute แล้ว

3. **Backward Compatibility:**
   - รองรับทั้ง Odoo 16 และ 17
   - ไม่ต้อง migrate data

---

## Related Documentation

- [LOGIC_CONSISTENCY_FIXES.md](./LOGIC_CONSISTENCY_FIXES.md) - Overall consistency fixes
- [NETTING_JE_INTEGRATION_COMPLETE.md](./NETTING_JE_INTEGRATION_COMPLETE.md) - Netting implementation
- [README_VENDOR_BILLS.md](./README_VENDOR_BILLS.md) - Vendor bill integration

---

## Version History

- **v1.0** (2025-12-15): Initial fix for credit note netting issue
  - Fixed `_create_netting_move()` to handle credit notes correctly
  - Updated netting amount calculation
  - Added detailed debug logging

---

## Deployment Checklist

- [x] Code changes applied
- [x] Restart Odoo service: `sudo systemctl restart instance1`
- [ ] Test with existing settlement (read-only)
- [ ] Create new test settlement with credit note
- [ ] Verify netting amount is correct
- [ ] Check journal entry amounts
- [ ] Monitor logs for any errors
- [ ] User acceptance testing

---

## Support

หากพบปัญหาหรือมีคำถาม:

1. ตรวจสอบ logs: `/var/log/odoo/instance1.log`
2. ดู debug info ในระหว่าง netting operation
3. ตรวจสอบว่า vendor bills มี `move_type` ถูกต้อง
4. ยืนยันว่า credit notes เป็น `in_refund` ไม่ใช่ `in_invoice` ที่มียอดติดลบ

---

**Last Updated:** December 15, 2025  
**Status:** ✅ Implemented and Ready for Testing
