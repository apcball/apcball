# การแก้ไข Exchange Rate - ดึงจากระบบ Odoo ณ วันที่ของ Bill

## สรุปปัญหาที่พบ

เมื่อ Bill **ไม่ได้เปิด Manual Exchange Rate** (checkbox "Apply Manual Exchange" ไม่ได้ติ๊ก) ระบบควรดึง Exchange Rate จากระบบ Odoo **ณ วันที่ของ Bill** แต่โค้ดเดิมมีจุดที่อาจ fallback ไปใช้ `fields.Date.today()` แทน ซึ่งไม่ถูกต้อง

## การแก้ไขที่ทำ

### 1. ปรับปรุง `_onchange_vendor_bill_id()` (บรรทัด ~135-145)

**เดิม:**
```python
rate = usd_currency._convert(1.0, thb_currency, self.env.company, vendor_bill.date or fields.Date.today())
```

**ใหม่:**
```python
# Get exchange rate from currency rate table for bill's date (ใช้วันที่ของ bill เสมอ)
bill_date = vendor_bill.date if vendor_bill.date else fields.Date.context_today(self)
rate = usd_currency._convert(1.0, thb_currency, self.env.company, bill_date)
```

**เหตุผล:** 
- ใช้วันที่ของ Bill ในการดึง exchange rate เสมอ
- ถ้า Bill ไม่มี date (กรณีผิดปกติ) จะใช้วันที่ปัจจุบันจาก context แทน

---

### 2. ปรับปรุง `_recompute_preview()` (บรรทัด ~245-275)

**เดิม:**
```python
bill_rate = 0.0
# Search for bills linked through invoice lines (proper Odoo way)
vendor_bill = wizard.env['account.move'].search([...], limit=1)
...
bill_rate = src_currency._convert(1.0, company_currency, company, vendor_bill.date or fields.Date.today())
```

**ใหม่:**
```python
bill_rate = 0.0
vendor_bill = wizard.vendor_bill_id  # ใช้ bill ที่ผู้ใช้เลือกก่อน

# If no bill selected, try to find one
if not vendor_bill:
    # Search for bills linked through invoice lines
    vendor_bill = wizard.env['account.move'].search([...], limit=1)
    ...

if vendor_bill:
    if hasattr(vendor_bill, 'is_exchange') and vendor_bill.is_exchange and vendor_bill.rate > 0:
        bill_rate = vendor_bill.rate  # ใช้ manual rate
    else:
        # Calculate from bill's currency conversion using BILL DATE
        bill_rate = src_currency._convert(1.0, company_currency, company, vendor_bill.date)
```

**เปลี่ยนแปลงสำคัญ:**
1. ✅ ใช้ `wizard.vendor_bill_id` (bill ที่ผู้ใช้เลือก) แทนการ search ใหม่เสมอ
2. ✅ ลบ `or fields.Date.today()` ออก - ใช้ `vendor_bill.date` โดยตรง
3. ✅ ถ้าไม่มี bill เลือก ถึงจะ search หา bill

---

### 3. ปรับปรุง `action_create()` (บรรทัด ~390-420)

**เดิม:**
```python
bill_rate = 0.0
vendor_bill = self.env['account.move'].search([...], limit=1)
...
bill_rate = src_currency._convert(1.0, company_currency, company, vendor_bill.date or fields.Date.today())
```

**ใหม่:**
```python
bill_rate = 0.0
vendor_bill = self.vendor_bill_id  # ใช้ bill ที่ผู้ใช้เลือกก่อน

# If no bill selected, try to find one
if not vendor_bill:
    # Search for bills linked through invoice lines
    vendor_bill = self.env['account.move'].search([...], limit=1)
    ...

if vendor_bill:
    if hasattr(vendor_bill, 'is_exchange') and vendor_bill.is_exchange and vendor_bill.rate > 0:
        bill_rate = vendor_bill.rate  # ใช้ manual rate
    else:
        # Calculate from bill's currency conversion using BILL DATE
        bill_rate = src_currency._convert(1.0, company_currency, company, vendor_bill.date)
```

**เปลี่ยนแปลงสำคัญ:**
1. ✅ ใช้ `self.vendor_bill_id` (bill ที่ผู้ใช้เลือก) แทนการ search ใหม่เสมอ
2. ✅ ลบ `or fields.Date.today()` ออก - ใช้ `vendor_bill.date` โดยตรง
3. ✅ ถ้าไม่มี bill เลือก ถึงจะ search หา bill

---

## ลำดับความสำคัญในการดึง Exchange Rate

หลังจากแก้ไข ระบบจะดึง exchange rate ตามลำดับนี้:

### กรณีที่ 1: Bill เปิด Manual Exchange Rate
```
✓ ใช้ vendor_bill.rate (manual rate ที่ user กรอกเอง)
```

### กรณีที่ 2: Bill ไม่ได้เปิด Manual Exchange Rate
```
✓ ใช้ System Rate จาก Odoo Currency Rate Table ณ วันที่ของ Bill
  → src_currency._convert(1.0, company_currency, company, vendor_bill.date)
```

### กรณีที่ 3: ไม่มี Bill
```
✓ Fallback ไปใช้ System Rate ณ วันที่ปัจจุบัน
```

---

## ตัวอย่างการใช้งาน

### Scenario: Bill วันที่ 08/12/2025 ไม่ได้เปิด Manual Exchange

**สถานการณ์:**
- Bill Date: 08/12/2025
- Apply Manual Exchange: ❌ ไม่ติ๊ก
- System Rate วันที่ 08/12/2025: 1 USD = 32.50 THB
- System Rate วันที่ 23/12/2025 (วันนี้): 1 USD = 33.00 THB

**ผลลัพธ์ (หลังแก้ไข):**
```
✓ ระบบจะดึง rate = 32.50 (ณ วันที่ของ Bill: 08/12/2025)
✓ ไม่ใช้ rate = 33.00 (วันนี้)
```

**ผลลัพธ์ (ก่อนแก้ไข - ผิด!):**
```
✗ อาจดึง rate = 33.00 (วันนี้) ในบางกรณี
```

---

## ประโยชน์ของการแก้ไข

1. ✅ **ความถูกต้อง**: ใช้ Exchange Rate ณ วันที่ของ Bill เสมอ
2. ✅ **ความสอดคล้อง**: เมื่อ user เลือก bill ระบบจะใช้ bill นั้นตลอด ไม่ search ใหม่
3. ✅ **ความชัดเจน**: ไม่มี fallback ที่ซ่อนเร้น ใช้วันที่ bill โดยตรง
4. ✅ **ประสิทธิภาพ**: ไม่ต้อง search bill ซ้ำ เพราะใช้ `wizard.vendor_bill_id` ที่ user เลือกไว้แล้ว

---

## ไฟล์ที่แก้ไข
- `/wizards/advance_bill_wizard.py`
  - `_onchange_vendor_bill_id()` - บรรทัด ~120-145
  - `_recompute_preview()` - บรรทัด ~245-275
  - `action_create()` - บรรทัด ~390-420

---

## การทดสอบที่แนะนำ

1. **ทดสอบกับ Bill ที่ไม่เปิด Manual Exchange**
   - สร้าง Bill วันที่ในอดีต
   - ไม่ติ๊ก "Apply Manual Exchange"
   - สร้าง Advance Accrual
   - ตรวจสอบว่า exchange rate ตรงกับวันที่ของ Bill

2. **ทดสอบกับ Bill หลายตัว**
   - PO มี 2-3 bills วันที่ต่างกัน
   - เลือก bill แต่ละตัว
   - ตรวจสอบว่า rate เปลี่ยนตามวันที่ของ bill ที่เลือก

3. **ทดสอบกับ Manual Exchange**
   - Bill เปิด Manual Exchange และกรอก rate เอง
   - ตรวจสอบว่าใช้ manual rate ที่กรอก ไม่ใช้ system rate
