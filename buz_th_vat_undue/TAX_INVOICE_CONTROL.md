# การแก้ไข: Tax Invoice บันทึกเฉพาะตอนกด "Use VAT"

## ปัญหาเดิม
เมื่อ Post Vendor Bill ที่มี VAT Undue:
- ระบบสร้าง `account.move.tax.invoice` record ทันที
- Tax ปรากฏใน Tax Report (PP30) ทันที
- **ไม่ถูกต้อง** เพราะ VAT Undue ยังไม่สามารถนำไปหักได้จนกว่าจะจ่ายเงิน

## การแก้ไข (Version 17.0.1.0.4)

### 1. เพิ่มไฟล์ `models/account_move_line.py`
Override `create()` method เพื่อป้องกันการสร้าง tax invoice สำหรับ VAT Undue:

```python
@api.model_create_multi
def create(self, vals_list):
    move_lines = super().create(vals_list)
    
    # ตรวจสอบและลบ tax invoice records ที่สร้างสำหรับ VAT Undue
    for line in move_lines:
        if line.tax_line_id and hasattr(line.tax_line_id, 'is_vat_undue') and line.tax_line_id.is_vat_undue:
            tax_invoices_to_remove = line.tax_invoice_ids
            if tax_invoices_to_remove:
                tax_invoices_to_remove.with_context(
                    force_remove_tax_invoice=True
                ).sudo().unlink()
    
    return move_lines
```

### 2. ปรับปรุง `models/tax_undue_line.py`
เพิ่มข้อมูลครบถ้วนตอนสร้าง tax invoice ใน `action_use_vat()`:

```python
tax_invoice_vals = {
    'move_id': move.id,
    'move_line_id': input_vat_line[0].id,
    'partner_id': rec.partner_id.id,
    'tax_invoice_number': rec.name,
    'tax_invoice_date': rec.tax_invoice_date,
    'tax_base_amount': rec.tax_base,  # เพิ่ม
    'balance': amount,  # เพิ่ม
}
```

## ผลลัพธ์

### ตอน Post Bill (VAT Undue):
✅ สร้าง Tax Undue Line  
✅ ลงบัญชี 116600 (VAT Undue)  
❌ **ไม่สร้าง** Tax Invoice  
❌ **ไม่ปรากฏ** ใน Tax Report  

### ตอนกด "Use VAT":
✅ สร้าง Journal Entry (Dr 116400, Cr 116600)  
✅ **สร้าง Tax Invoice**  
✅ **ปรากฏใน Tax Report**  

## การทดสอบ

### 1. Post Vendor Bill
```sql
-- ตรวจสอบว่าไม่มี tax invoice สำหรับ VAT Undue
SELECT * FROM account_move_tax_invoice 
WHERE move_id = [bill_id];
-- ผลลัพธ์: ไม่มีข้อมูล (empty)
```

### 2. กด "Use VAT"
```sql
-- ตรวจสอบว่ามี tax invoice แล้ว
SELECT * FROM account_move_tax_invoice 
WHERE move_id = [clearing_entry_id];
-- ผลลัพธ์: มี 1 record
```

### 3. ตรวจสอบ Tax Report
- **ก่อนกด Use VAT**: ไม่เห็น VAT Undue ใน PP30
- **หลังกด Use VAT**: เห็น Input VAT ใน PP30

## ไฟล์ที่เปลี่ยนแปลง

1. **models/account_move_line.py** (ใหม่)
   - Override `create()` เพื่อป้องกันสร้าง tax invoice

2. **models/tax_undue_line.py**
   - เพิ่มข้อมูล `tax_base_amount` และ `balance`

3. **models/__init__.py**
   - Import `account_move_line`

4. **__manifest__.py**
   - Version: 17.0.1.0.3 → 17.0.1.0.4

5. **README.md**
   - อัพเดท documentation

## Integration กับ l10n_th_account_tax

Module `l10n_th_account_tax` มี validation ที่ skip สำหรับ VAT Undue อยู่แล้ว:

```python
# l10n_th_account_tax/models/account_move.py line 445
if hasattr(tax_invoice.tax_line_id, 'is_vat_undue') and tax_invoice.tax_line_id.is_vat_undue:
    continue  # Skip validation
```

ดังนั้น module ของเราทำงานร่วมกันได้ดี:
- `l10n_th_account_tax`: Skip validation สำหรับ VAT Undue
- `buz_th_vat_undue`: ป้องกันการสร้าง tax invoice และสร้างตอนกด "Use VAT"

## Compatibility
- Odoo Version: 17.0
- Dependencies: `account`, `l10n_th`, `l10n_th_account_tax`
- License: LGPL-3
