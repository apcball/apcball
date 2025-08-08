# WHT Tax System v2.0 - User Guide

## Overview
ระบบ WHT Tax v2.0 ใช้ระบบภาษีมาตรฐานของ Odoo 17 แทนการใช้ฟิลด์กำหนดเอง ทำให้มีความแม่นยำและบูรณาการที่ดีกว่า

## Key Features

### 1. ระบบภาษีมาตรฐาน Odoo 17
- ใช้ `account.tax` แทน custom fields
- คำนวณภาษีแม่นยำกว่าด้วย repartition lines
- บูรณาการกับระบบบัญชีโดยตรง

### 2. Auto WHT Certificate Generation
- สร้าง WHT Certificate อัตโนมัติเมื่อชำระเงิน
- ตรวจสอบภาษี WHT ในรายการชำระเงิน
- เชื่อมโยงใบหัก ณ ที่จ่ายกับ Payment โดยตรง

### 3. Enhanced Auto-Fill ใน Payment
- ตรวจสอบ Invoice ที่มี WHT Tax อัตโนมัติ
- คำนวณยอดหักภาษี ณ ที่จ่าย
- ปรับยอดชำระเงินให้ถูกต้อง

### 4. Product-Level WHT Configuration
- กำหนด WHT Tax ที่ระดับสินค้า
- กำหนด Default WHT ที่ระดับหมวดสินค้า
- Auto-assign ตามประเภทสินค้า

## Configuration

### 1. WHT Tax Types Available
```
- Service WHT 3% (การบริการ)
- Professional WHT 5% (ค่าวิชาชีพ)
- Rental WHT 5% (ค่าเช่า)
- Transport WHT 1% (ค่าขนส่ง)
```

### 2. Setting up Products
```python
# ใน Product Form
WHT Tax (Purchase): เลือก WHT Tax ที่ต้องการ
WHT Tax (Sale): เลือก WHT Tax สำหรับการขาย (ถ้าใช้)
```

### 3. Setting up Product Categories
```python
# ใน Product Category Form
Default WHT Tax (Purchase): กำหนด Default สำหรับสินค้าในหมวดนี้
Default WHT Tax (Sale): กำหนด Default สำหรับการขาย
```

## Usage Workflow

### 1. Creating Vendor Bill with WHT
1. สร้าง Vendor Bill ปกติ
2. เลือกสินค้า/บริการ → WHT Tax จะเติมอัตโนมัติ (ถ้าได้กำหนดไว้)
3. หรือเลือก Tax ใน Invoice Line โดยตรง
4. ระบบจะแสดง **Withholding Tax Summary**:
   - WHT Base Amount: ยอดฐานภาษี
   - WHT Tax Amount: ยอดภาษีหัก ณ ที่จ่าย

### 2. Payment with Auto WHT
1. ไปที่ **Register Payment** จาก Invoice
2. ระบบจะ:
   - ตรวจสอบ WHT Tax ใน Invoice อัตโนมัติ
   - คำนวณยอดหัก WHT
   - ปรับ Payment Amount = Invoice Total - WHT Amount
   - แสดง WHT Information

3. กด **Create Payment**
4. ระบบจะ:
   - สร้าง Payment Entry
   - สร้าง WHT Certificate อัตโนมัติ
   - เชื่อมโยง Certificate กับ Payment

### 3. WHT Certificate Management
- ดู Certificate: ไปที่ Payment → กด **WHT Certs** button
- Certificate จะมี:
  - เลขที่อ้างอิง
  - วันที่
  - ผู้จ่าย/ผู้รับ
  - ยอดฐานภาษีและยอดหัก
  - สถานะ

## Technical Details

### 1. Tax Configuration
```xml
<!-- Service WHT 3% -->
<record id="wht_tax_service_3" model="account.tax">
    <field name="name">WHT Service 3%</field>
    <field name="amount">-3.0</field>  <!-- ลบ = หัก -->
    <field name="type_tax_use">purchase</field>
    <field name="tag_ids" eval="[(4, ref('wht_tag_service'))]"/>
</record>
```

### 2. Auto WHT Detection
```python
def _auto_assign_wht_tax(self):
    """ตรวจสอบและกำหนด WHT Tax อัตโนมัติ"""
    for line in self.invoice_line_ids:
        if line.product_id and line.product_id.wht_tax_purchase_id:
            line.tax_ids = [(4, line.product_id.wht_tax_purchase_id.id)]
```

### 3. Payment Integration
```python
def _post(self, soft=True):
    """เมื่อ Post Payment จะสร้าง WHT Certificate อัตโนมัติ"""
    result = super()._post(soft)
    if self.has_wht_tax:
        self._auto_generate_wht_certificates()
    return result
```

## Migration from v1.0

### Automatic Migration
เมื่ออัปเกรดจาก v1.0 ระบบจะ migrate ข้อมูลอัตโนมัติ:

1. **Account Move Lines**: แปลง `wht_tax_id` → `tax_ids`
2. **Products**: แปลง custom WHT fields → `wht_tax_purchase_id`
3. **Partners**: แปลง default WHT → `property_supplier_taxes_id`
4. **Certificates**: เชื่อมโยงกับ Payments

### Manual Migration
```python
# Run manual migration if needed
env = api.Environment(cr, SUPERUSER_ID, {})
from odoo.addons.l10n_th_account_tax.migrations.post_migration import run_manual_migration
run_manual_migration(env)
```

## Troubleshooting

### 1. WHT Tax ไม่แสดงใน Invoice
- ตรวจสอบ Product มี WHT Tax ที่กำหนดไว้หรือไม่
- ตรวจสอบ Tax Type = Purchase
- ลองเลือก Tax ใน Invoice Line โดยตรง

### 2. Payment Amount ไม่ถูกต้อง
- ตรวจสอบ Invoice มี WHT Tax หรือไม่
- ระบบจะปรับ Payment Amount อัตโนมัติ
- Payment Amount = Total - WHT Amount

### 3. WHT Certificate ไม่สร้างอัตโนมัติ
- ตรวจสอบ Payment มี WHT Tax หรือไม่
- ตรวจสอบ Payment State = Posted
- ลองกด **Generate WHT Certificate** ใน Payment Form

### 4. Migration Issues
- ตรวจสอบ Log ใน Settings → Technical → Logging
- รัน Manual Migration Script
- ตรวจสอบข้อมูลเก่าใน Database

## Benefits of New System

### 1. ความแม่นยำ
- ใช้ระบบภาษีมาตรฐาน Odoo
- คำนวณแม่นยำด้วย repartition lines
- Journal entries ถูกต้องตามมาตรฐาน

### 2. การบูรณาการ
- ทำงานร่วมกับ modules อื่นได้ดี
- รองรับ Odoo standard workflows
- ไม่ต้องการ customization เพิ่มเติม

### 3. การบำรุงรักษา
- ใช้ Odoo standard models
- อัปเกรดง่ายกว่า
- มี documentation ที่ดี

### 4. Performance
- Query เร็วกว่า (ใช้ standard fields)
- Memory usage น้อยกว่า
- Better caching support

## Support and Updates
- Documentation: `/docs/` folder
- Migration scripts: `/migrations/` folder
- Test cases: `/tests/` folder
- Bug reports: ติดต่อ Development Team
