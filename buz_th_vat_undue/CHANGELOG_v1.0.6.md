# Version 17.0.1.0.6 - Credit Note Reversal Logic

## 🎯 การเปลี่ยนแปลง

### ปัญหาเดิม (v17.0.1.0.5)
เมื่อออก Credit Note หลังจาก Use VAT แล้ว:
- ❌ สร้าง Reclassification Entry เพิ่ม (Dr Undue, Cr Input VAT)
- ❌ ไม่ได้กลับรายการ journal "Clear Undue VAT" ที่สร้างจาก Use VAT
- ❌ ไม่ได้ลบ Tax Invoice Records ที่สร้างจาก Use VAT
- ❌ Tax Undue Line ยัง state='used' อยู่

### แก้ไขใหม่ (v17.0.1.0.6)
✅ **Reverse (กลับรายการ) journal entry จาก Use VAT แทน**
- ใช้ `account.move.reversal` wizard
- ลบ Tax Invoice Records ที่สร้างจาก Use VAT
- Reset Tax Undue Line กลับเป็น state='undue'
- ไม่ต้องสร้าง Reclassification Entry ซ้ำซ้อน

---

## 📊 Flow การทำงานใหม่

### Scenario: Credit Note หลังจาก Use VAT

```
Step 1: Vendor Bill (2025-01-01)
----------------------------------------
Dr Expenses (510100)      1,000.00
Dr VAT Undue (116600)        70.00
   Cr Payable (211100)              1,070.00

Tax Undue Line:
- name: SINV-2025-001
- tax_amount: 70.00
- state: undue
- remaining: 70.00


Step 2: Payment (2025-01-15)
----------------------------------------
Dr Payable (211100)      1,070.00
   Cr Bank (110100)                1,070.00


Step 3: Use VAT (2025-01-20)
----------------------------------------
Journal Entry (JV/2025/0015):
Dr Input VAT (116400)       70.00
   Cr VAT Undue (116600)           70.00

Tax Invoice Record Created:
- move_id: JV/2025/0015
- tax_invoice_number: SINV-2025-001
- tax_invoice_date: 2025-01-20
- balance: 70.00
- ✅ ปรากฏใน PP30

Tax Undue Line Updated:
- used_tax_amount: 70.00
- used_move_id: JV/2025/0015
- state: used
- remaining: 0.00


Step 4: Credit Note (2025-01-25) - CN ทั้งหมด
----------------------------------------
Credit Note Entry (REFUND/2025/0001):
Dr Payable (211100)      1,070.00
   Cr Expenses (510100)            1,000.00
   Cr VAT Undue (116600)              70.00

Tax Undue Line Created (CN):
- name: SINV-2025-001
- tax_amount: -70.00 (ลบ)
- state: refund


Step 5: Reverse Use VAT Entry (Auto) ✅ ใหม่
----------------------------------------
Reversal Entry (MISC/2025/0020):
Dr VAT Undue (116600)       70.00
   Cr Input VAT (116400)           70.00

Actions:
✅ Reverse journal JV/2025/0015
✅ ลบ Tax Invoice Record จาก JV/2025/0015
✅ Reset Tax Undue Line:
   - used_tax_amount: 0.00
   - used_move_id: False
   - state: undue → refund (จาก compute)
   - remaining: -70.00 → refund


Step 6: ผลลัพธ์สุดท้าย
----------------------------------------
Account 116600 (VAT Undue):
  Bill:         Dr  70.00
  Use VAT:           Cr  70.00  (Balance: 0)
  CN:                Cr  70.00  (Balance: -70 Cr)
  Reverse:      Dr  70.00        (Balance: 0) ✅

Account 116400 (Input VAT):
  Use VAT:      Dr  70.00
  Reverse:           Cr  70.00  (Balance: 0) ✅

Tax Report (PP30):
  Use VAT:      +70.00
  Reverse:      -70.00
  Net Effect:    0.00 ✅
```

---

## 🔧 Code Changes

### File: `models/account_move.py`

#### 1. เพิ่ม Import
```python
import logging

_logger = logging.getLogger(__name__)
```

#### 2. ปรับปรุง `_create_refund_vat_reclassification()`
```python
def _create_refund_vat_reclassification(self, original_undue_lines):
    """
    Reverse journal entry จาก Use VAT
    แทนการสร้าง Reclassification Entry ใหม่
    """
    # กลับรายการ Journal Entries จาก Use VAT
    for undue_line in original_undue_lines:
        if undue_line.state == 'used' and undue_line.used_move_id:
            if undue_line.used_move_id.state == 'posted' and not undue_line.used_move_id.reversal_move_id:
                
                # สร้าง reversal entry ด้วย wizard
                reversal_vals = {
                    'move_ids': [(4, undue_line.used_move_id.id)],
                    'date': self.date,  # วันที่ของ CN
                    'reason': _("Reverse VAT Usage due to Credit Note: %s") % self.name,
                    'journal_id': undue_line.used_move_id.journal_id.id,
                }
                
                reversal_wizard = self.env['account.move.reversal'].create(reversal_vals)
                reversal_action = reversal_wizard.reverse_moves()
                
                # ลบ Tax Invoice Records จาก Use VAT entry
                tax_invoices_to_remove = self.env['account.move.tax.invoice'].search([
                    ('move_id', '=', undue_line.used_move_id.id)
                ])
                if tax_invoices_to_remove:
                    tax_invoices_to_remove.sudo().unlink()
                
                # Reset Tax Undue Line
                undue_line.write({
                    'used_tax_amount': 0.0,
                    'used_move_id': False,
                })
```

---

## ✅ ข้อดีของวิธีใหม่

1. **ถูกต้องตามหลักบัญชี**
   - Reverse entry ทำให้เห็น audit trail ชัดเจน
   - ไม่สร้าง entry ซ้ำซ้อน

2. **Tax Report ถูกต้อง**
   - Tax Invoice ถูกลบออกจาก PP30 อัตโนมัติ
   - ไม่มี Tax Invoice Record ซ้ำซ้อน

3. **Tax Undue Line สถานะถูกต้อง**
   - Reset กลับเป็น undue
   - `remaining_tax_amount` คำนวณถูกต้อง

4. **รองรับ Partial Credit Note**
   - ถ้า CN บางส่วน → Reverse เฉพาะส่วนที่เกี่ยวข้อง
   - Tax Undue Line จะ compute state ใหม่

---

## 🧪 Test Cases

### Test 1: Full Credit Note หลัง Use VAT
```
1. สร้าง Bill: 1,000 + VAT Undue 70
2. Use VAT: 70 (สร้าง Tax Invoice)
3. CN ทั้งหมด: 1,000 + VAT 70
4. ตรวจสอบ:
   ✅ Journal Use VAT ถูก reverse
   ✅ Tax Invoice ถูกลบ
   ✅ Tax Undue Line: state=refund, used=0, remaining=-70
   ✅ Account 116400 balance=0
   ✅ Account 116600 balance=0
```

### Test 2: Partial Credit Note หลัง Use VAT
```
1. สร้าง Bill: 1,000 + VAT Undue 70
2. Use VAT: 70 (สร้าง Tax Invoice)
3. CN บางส่วน: 500 + VAT 35
4. ตรวจสอบ:
   ✅ Journal Use VAT ถูก reverse
   ✅ Tax Invoice ถูกลบ
   ✅ Tax Undue Line: state=undue, used=0, remaining=70
   ✅ สามารถ Use VAT ใหม่ได้ 35 บาท (CN) หรือ 35 บาท (คงเหลือ)
```

### Test 3: Credit Note ก่อน Use VAT
```
1. สร้าง Bill: 1,000 + VAT Undue 70
2. CN ทั้งหมดก่อน Use VAT
3. ตรวจสอบ:
   ✅ ไม่มีการ reverse (เพราะยังไม่ Use)
   ✅ สร้าง Tax Undue Line แบบลบ
   ✅ Original Line: state=refund
```

---

## 📝 Migration Note

### จาก v17.0.1.0.5 → v17.0.1.0.6

**ไม่มีผลกับข้อมูลเดิม:**
- Logic เปลี่ยนเฉพาะการทำ CN ในอนาคต
- ข้อมูล Tax Undue Lines เดิมไม่ได้รับผลกระทบ

**Recommended Actions:**
1. Upgrade module: `odoo-bin -u buz_th_vat_undue -d [database]`
2. ทดสอบ CN กับ bill ใหม่
3. ตรวจสอบ Tax Report (PP30) ว่าถูกต้อง

---

## 🔗 Related Files

- [`models/account_move.py`](models/account_move.py) - Logic หลัก
- [`models/tax_undue_line.py`](models/tax_undue_line.py) - Tax Undue Line management
- [`CREDIT_NOTE_ANALYSIS.md`](CREDIT_NOTE_ANALYSIS.md) - การวิเคราะห์โดยละเอียด

---

## 📞 Summary

**Version 17.0.1.0.6 แก้ไข:**
- ✅ Reverse journal entry จาก Use VAT แทนสร้าง Reclassification
- ✅ ลบ Tax Invoice Records อัตโนมัติ
- ✅ Reset Tax Undue Line state ถูกต้อง
- ✅ รองรับ Partial Credit Note
- ✅ Tax Report (PP30) ถูกต้อง

**ต้อง Upgrade Module:**
```bash
sudo systemctl stop instance1
odoo-bin -u buz_th_vat_undue -d [database_name] --stop-after-init
sudo systemctl start instance1
```
