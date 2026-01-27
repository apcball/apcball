# Version 17.0.1.0.5 - เพิ่ม Wizard เลือกวันที่ลงบัญชี

## การเปลี่ยนแปลง

### ปัญหาเดิม
เมื่อกด "Use VAT" ระบบจะสร้าง Journal Entry โดยใช้วันที่จาก:
- `tax_invoice_date` (วันที่ใบกำกับภาษีของ Vendor)
- หรือวันที่ปัจจุบัน ถ้าไม่มี

**ปัญหา:** บางครั้งต้องการลงบัญชีในวันที่อื่น (เช่น วันที่จ่ายเงินจริง)

### การแก้ไข

#### 1. เพิ่ม Wizard: `vat.undue.use.wizard`

**ฟีเจอร์:**
- 📅 เลือกวันที่ลงบัญชี (Accounting Date)
- 📊 แสดงสรุปรายการที่เลือก
- 💰 แสดงยอดรวม
- 📋 แสดงรายละเอียด Tax Undue Lines

**ไฟล์:**
- `wizard/vat_undue_use_wizard.py` - Model
- `wizard/vat_undue_use_wizard_views.xml` - View

#### 2. แก้ไข `tax_undue_line.py`

**เปลี่ยนแปลง:**
- `action_use_vat()` - เปลี่ยนจากสร้าง JE ทันที → เปิด wizard
- `_process_use_vat()` - แยก logic การสร้าง JE ออกมา (ถูกเรียกจาก wizard)
- รับ `accounting_date` จาก context

```python
# เดิม: action_use_vat() สร้าง JE ทันที
def action_use_vat(self):
    # ... validation ...
    # สร้าง JE ทันที
    move = self.env['account.move'].create(...)

# ใหม่: เปิด wizard
def action_use_vat(self):
    # ... validation ...
    return {
        'type': 'ir.actions.act_window',
        'res_model': 'vat.undue.use.wizard',
        'view_mode': 'form',
        'target': 'new',
        'context': {
            'default_undue_line_ids': [(6, 0, self.ids)],
        },
    }

# Logic แยกออกมา
def _process_use_vat(self):
    accounting_date = self.env.context.get('accounting_date')
    # ... สร้าง JE ...
    move_vals['date'] = accounting_date
```

## UI Flow

### เดิม:
```
Tax Undue Lines (Tree) → เลือก Lines → กด "Use VAT" 
→ สร้าง JE ทันที → แสดง JE
```

### ใหม่:
```
Tax Undue Lines (Tree) → เลือก Lines → กด "Use VAT"
→ เปิด Wizard → เลือกวันที่ → กด "Confirm Use VAT"
→ สร้าง JE → แสดง JE
```

## ตัวอย่าง Wizard

```
╔════════════════════════════════════════════════════╗
║  Use VAT - Select Accounting Date                 ║
╠════════════════════════════════════════════════════╣
║  จำนวนรายการ:  3                                  ║
║  ยอดรวม:       210.00 THB                         ║
║                                                    ║
║  วันที่ลงบัญชี:  [📅 18/01/2026]  *Required       ║
║                                                    ║
║  ┌─────────────────────────────────────────────┐  ║
║  │ Tax Undue Lines                             │  ║
║  ├─────────────────────────────────────────────┤  ║
║  │ Invoice No  │ Partner  │ Date  │ Amount    │  ║
║  │ INV-001     │ ABC Ltd  │ 15/01 │ 70.00     │  ║
║  │ INV-002     │ XYZ Co   │ 16/01 │ 70.00     │  ║
║  │ INV-003     │ DEF Inc  │ 17/01 │ 70.00     │  ║
║  │                         Total:  │ 210.00    │  ║
║  └─────────────────────────────────────────────┘  ║
║                                                    ║
║  [Confirm Use VAT]  [Cancel]                      ║
╚════════════════════════════════════════════════════╝
```

## ผลลัพธ์

### Journal Entry
- **Date:** ใช้วันที่ที่เลือกใน wizard
- **Ref:** Clear Undue VAT: [Tax Invoice Number]
- **Lines:**
  - Dr 116400 (Input VAT)
  - Cr 116600 (VAT Undue)

### Tax Invoice Record
- **Tax Invoice Date:** ยังคงใช้วันที่จาก Vendor Bill (tax_invoice_date)
- **Move Date:** ใช้วันที่ที่เลือกใน wizard

## ไฟล์ที่เปลี่ยนแปลง

### ใหม่:
1. ✨ `wizard/vat_undue_use_wizard.py`
2. ✨ `wizard/vat_undue_use_wizard_views.xml`

### แก้ไข:
1. 🔧 `wizard/__init__.py` - Import wizard ใหม่
2. 🔧 `models/tax_undue_line.py` - แยก logic, เปิด wizard
3. 🔧 `security/ir.model.access.csv` - เพิ่ม access rights
4. 🔧 `__manifest__.py` - Version 17.0.1.0.5, เพิ่ม view file
5. 📝 `README.md` - อัพเดท usage

## การทดสอบ

### Test Case 1: เลือกวันที่ปัจจุบัน
```
1. เลือก Tax Undue Lines
2. กด "Use VAT"
3. Wizard แสดงวันที่ default = วันนี้
4. กด "Confirm"
5. ตรวจสอบ JE → date = วันนี้
```

### Test Case 2: เลือกวันที่ในอดีต
```
1. เลือก Tax Undue Lines
2. กด "Use VAT"
3. เปลี่ยนวันที่เป็น 15/01/2026
4. กด "Confirm"
5. ตรวจสอบ JE → date = 15/01/2026
```

### Test Case 3: เลือกหลายรายการ
```
1. เลือก 3 Tax Undue Lines
2. กด "Use VAT"
3. Wizard แสดง:
   - จำนวนรายการ: 3
   - ยอดรวม: 210.00
4. กด "Confirm"
5. ตรวจสอบ → สร้าง 3 JE ด้วยวันที่เดียวกัน
```

## SQL Validation

```sql
-- ตรวจสอบว่า JE ใช้วันที่ที่เลือก
SELECT 
    am.name,
    am.date as accounting_date,
    am.ref,
    ati.tax_invoice_date,
    ati.tax_invoice_number
FROM account_move am
JOIN account_move_tax_invoice ati ON ati.move_id = am.id
WHERE am.ref LIKE '%Clear Undue VAT%'
ORDER BY am.id DESC
LIMIT 5;

-- Expected:
-- accounting_date = วันที่ที่เลือกใน wizard
-- tax_invoice_date = วันที่จาก Vendor Bill
```

## Backward Compatibility

✅ **รักษา backward compatibility**
- Logic การสร้าง JE ยังเหมือนเดิม
- เพียงแต่แยก UI ออกมาเป็น wizard
- Tax Invoice ยังคงใช้วันที่เดิม (tax_invoice_date)

## Upgrade Notes

```bash
# Upgrade module
odoo-bin -u buz_th_vat_undue -d [database_name]

# หรือ restart service
sudo systemctl restart instance1
```

ไม่จำเป็นต้อง migrate data เพราะ:
- ไม่มีการเปลี่ยน database schema
- เพิ่มเฉพาะ wizard (transient model)
- Logic เดิมยังทำงานได้

## User Manual Update

**คู่มือการใช้งาน:**

1. ไปที่ **Accounting → Taxes Undue**
2. เลือก Tax Undue Lines ที่ต้องการ (ที่จ่ายเงินแล้ว)
3. กดปุ่ม **"Use VAT"**
4. **Wizard จะเปิดขึ้น**:
   - จำนวนรายการและยอดรวมจะแสดง
   - เลือก **วันที่ลงบัญชี** (default = วันนี้)
   - ดูรายละเอียด Tax Undue Lines ในแท็บ
5. กด **"Confirm Use VAT"**
6. ระบบจะ:
   - สร้าง Journal Entry ด้วยวันที่ที่เลือก
   - สร้าง Tax Invoice record
   - แสดงรายการ Journal Entries ที่สร้าง

**หมายเหตุ:**
- วันที่ลงบัญชีสามารถเลือกเป็นวันใดก็ได้
- แต่วันที่ Tax Invoice จะคงเป็นวันที่จาก Vendor Bill เดิม
- ควรเลือกวันที่ที่จ่ายเงินจริง เพื่อความถูกต้องของรายงาน
