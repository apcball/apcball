# การแก้ไขปัญหา Negative Valuation และ Product Duplication

## ปัญหาที่พบ

### 1. Product ที่มี Valuation ติดลบไม่ถูกดึงขึ้นมา
- เมื่อกด "Compute Plan" พร้อม Auto-detect Products
- Product ที่มี valuation ติดลบ เช่น `[3FG-PSS106-PM470-05]` ที่มี:
  - Quantity: -1.0000
  - Value: -43,455.32
- ไม่ถูกดึงเข้ามาใน product selection

### 2. Product ที่ Re-compute แล้วยังถูกดึงขึ้นมาอีก
- หลังจากกดสร้าง SVL สำเร็จแล้ว
- สามารถกดสร้างได้เรื่อยๆ
- Product รายการที่ทำแล้วยังถูกดึงขึ้นมาด้วย
- ทั้งๆ ที่ควรจะไม่แสดงอีกเพราะ regenerate เสร็จแล้ว

## การแก้ไข

### 1. เพิ่มการตรวจจับ Negative Valuation
**ไฟล์:** `models/valuation_regenerate_wizard.py`

#### เพิ่มการตรวจสอบ 2 กรณี:

```python
# Check for negative valuation (ค่า value ติดลบ)
# This checks the cumulative value across all SVLs
total_value = sum(svls.mapped('value'))
total_qty = sum(svls.mapped('quantity'))

if total_qty != 0 and total_value < 0:
    _logger.info(
        f"Product {product.display_name}: "
        f"Found negative valuation - Qty: {total_qty}, Value: {total_value}"
    )
    products_with_issues |= product
    continue

# Check for individual SVLs with negative value when quantity is positive
negative_value_svls = svls.filtered(lambda s: s.quantity > 0 and s.value < 0)
if negative_value_svls:
    _logger.info(
        f"Product {product.display_name}: "
        f"Found {len(negative_value_svls)} SVLs with negative value but positive quantity"
    )
    products_with_issues |= product
    continue
```

**อธิบาย:**
- **การตรวจสอบแบบรวม (Cumulative):** ตรวจสอบว่า total value ของ product ติดลบหรือไม่
- **การตรวจสอบรายตัว (Individual):** ตรวจสอบ SVL แต่ละตัวที่มี quantity เป็นบวกแต่ value เป็นลบ
- ถ้าพบปัญหาใดปัญหาหนึ่ง จะเพิ่ม product เข้า `products_with_issues`

### 2. เพิ่มการกรอง Product ที่ทำ Regenerate ไปแล้ว
**ไฟล์:** `models/valuation_regenerate_wizard.py`

#### เพิ่ม Import:
```python
from datetime import datetime, timedelta
```

#### เพิ่มการตรวจสอบ Log ล่าสุด:
```python
# Get products that have been recently regenerated (within last 5 minutes) to exclude them
recent_logs = self.env['valuation.regenerate.log'].search([
    ('company_id', '=', self.company_id.id),
    ('executed_at', '>=', fields.Datetime.now() - timedelta(minutes=5)),
    ('dry_run', '=', False),
])
recently_processed_products = recent_logs.mapped('scope_products')

for product in products_with_moves:
    # Skip products that were recently processed
    if product in recently_processed_products:
        _logger.info(f"Product {product.display_name}: Skipping - recently processed")
        continue
```

**อธิบาย:**
- ค้นหา log ของการ regenerate ที่ทำภายใน 5 นาทีที่ผ่านมา
- ดึงรายการ product ที่ถูก process แล้ว
- ข้ามการตรวจสอบ product เหล่านั้นใน auto-detect

### 3. เพิ่มปุ่ม "Clear Selection"
**ไฟล์:** `views/wizard_views.xml`

```xml
<button name="action_clear_selection" 
        string="Clear Selection" 
        type="object" 
        class="btn-secondary" 
        invisible="not product_ids"/>
```

**ไฟล์:** `models/valuation_regenerate_wizard.py`

```python
def action_clear_selection(self):
    """Clear selected products and preview lines"""
    self.ensure_one()
    self.write({
        'product_ids': [(5, 0, 0)],  # Clear all products
        'line_preview_ids': [(5, 0, 0)],  # Clear all preview lines
    })
    return {
        'type': 'ir.actions.client',
        'tag': 'display_notification',
        'params': {
            'title': 'Selection Cleared',
            'message': 'Product selection and preview have been cleared. You can now run Compute Plan again.',
            'type': 'success',
            'sticky': False
        }
    }
```

**อธิบาย:**
- ปุ่มสำหรับล้างการเลือก product และ preview lines
- แสดงเฉพาะเมื่อมี product ถูกเลือกอยู่
- ช่วยให้ user สามารถเริ่มใหม่ได้ง่าย

### 4. ปรับปรุงการแจ้งเตือนใน Compute Plan
**ไฟล์:** `models/valuation_regenerate_wizard.py`

#### เพิ่มฟิลด์ติดตาม auto-detect:
```python
auto_detect_ran = fields.Boolean(
    'Auto-detect Has Run',
    default=False,
    help='Internal flag to track if auto-detect has already run'
)
```

#### ปรับปรุง logic เพื่อแก้ไข JavaScript error:
```python
# Auto-detect products with valuation issues if enabled
if self.auto_detect_products and self.location_ids and not self.auto_detect_ran:
    detected_products = self._auto_detect_products_with_issues()
    if detected_products:
        self.write({
            'product_ids': [(6, 0, detected_products.ids)],
            'auto_detect_products': False,
            'auto_detect_ran': True,
        })
        _logger.info(f"Auto-detected {len(detected_products)} products with potential valuation issues")
        
        # Continue with normal compute plan flow
        # This allows the preview to be generated in the same action
```

**อธิบาย:**
- เพิ่มฟิลด์ `auto_detect_ran` เพื่อติดตามว่า auto-detect ทำงานไปแล้วหรือไม่
- แก้ไข JavaScript error โดยไม่ return notification ที่มี `next` property
- ทำ auto-detect และสร้าง preview ในครั้งเดียว
- ไม่ต้องกด Compute Plan ซ้ำอีก

### 5. แก้ไข JavaScript Error
**ปัญหา:** `TypeError: Cannot read properties of undefined (reading 'map')`

**สาเหตุ:**
- Odoo 17 ไม่รองรับ `next` property ใน notification action
- การ return notification พร้อม `next` ทำให้เกิด error

**วิธีแก้:**
- เปลี่ยนจากการ return notification และเปิด wizard ใหม่
- เป็นการทำงานต่อเนื่องในครั้งเดียว (auto-detect → create preview)
- ใช้ฟิลด์ `auto_detect_ran` เพื่อป้องกันการ detect ซ้ำ

## การใช้งาน

### ขั้นตอนการใช้งานหลังแก้ไข:

1. **เปิด Valuation Regenerate Wizard**
   - เลือก Company และ Location ที่ต้องการตรวจสอบ
   - เปิดใช้ "Auto-detect Products with Valuation Issues"

2. **กด "Compute Plan" ครั้งแรก**
   - ระบบจะค้นหา product ที่มีปัญหา valuation รวมถึง valuation ติดลบ
   - Product จะถูกเลือกอัตโนมัติใน field "Products"
   - ระบบจะสร้าง preview ให้อัตโนมัติในครั้งเดียว
   - ไม่จำเป็นต้องกด Compute Plan ซ้ำอีก

3. **ตรวจสอบ Preview**
   - ไปที่แท็บ "Preview" เพื่อดูรายการ SVL และ Journal Entry ที่จะถูกลบและสร้างใหม่
   - ตรวจสอบรายการ product ที่ถูกเลือก

4. **Apply Regeneration**
   - ปิด "Dry Run Mode"
   - กด "Apply Regeneration" เพื่อทำการ regenerate จริง

5. **กด Clear Selection (ถ้าต้องการเริ่มใหม่)**
   - Product ที่ regenerate ไปแล้วจะไม่ถูกดึงขึ้นมาอีก (ภายใน 5 นาที)
   - หากต้องการเริ่มใหม่หรือตรวจสอบ product อื่น กด "Clear Selection"

## สรุปการปรับปรุง

### Features ใหม่:
1. ✅ **ตรวจจับ Negative Valuation** - ดึง product ที่มี value ติดลบมาให้
2. ✅ **กรอง Product ที่ทำแล้ว** - ป้องกันการดึง product ที่ regenerate ไปแล้วกลับมาอีก
3. ✅ **ปุ่ม Clear Selection** - ล้างการเลือกและเริ่มใหม่ได้ง่าย
4. ✅ **ข้อความแจ้งเตือนที่ชัดเจน** - แจ้งผลการ auto-detect และแนะนำขั้นตอนถัดไป

### การตรวจสอบที่เพิ่มขึ้น:
- ✅ Total valuation เป็นลบ
- ✅ Individual SVL มี value เป็นลบขณะที่ quantity เป็นบวก
- ✅ SVL ที่ขาดหายไป
- ✅ SVL ที่มี value = 0 แต่ quantity ≠ 0
- ✅ SVL ที่ไม่มี account move (ถ้าเปิดใช้)

## ข้อควรระวัง

1. **ระยะเวลา 5 นาที:** Product ที่ regenerate ไปแล้วจะไม่ถูกดึงกลับมาภายใน 5 นาที
   - ถ้าต้องการ regenerate ซ้ำภายในเวลานี้ ต้องเลือก product ด้วยตนเอง
   - หรือรอให้ครบ 5 นาทีแล้ว auto-detect ใหม่

2. **การล้างข้อมูล:** ปุ่ม "Clear Selection" จะล้างทั้ง product selection และ preview
   - ต้องกด Compute Plan ใหม่เพื่อดู preview อีกครั้ง

3. **Dry Run Mode:** อย่าลืมปิด Dry Run Mode ก่อนกด Apply Regeneration
   - ถ้าเปิดอยู่จะไม่มีการเปลี่ยนแปลงข้อมูลจริง

## การทดสอบ

### Test Case 1: Product มี Negative Valuation
```
Product: [3FG-PSS106-PM470-05]
Quantity: -1.0000
Value: -43,455.32
Expected: ถูกดึงเข้ามาใน auto-detect
```

### Test Case 2: Product ที่ Regenerate แล้ว
```
1. Regenerate product A
2. กด Compute Plan อีกครั้งภายใน 5 นาที
Expected: Product A ไม่ถูกดึงกลับมาใน auto-detect
```

### Test Case 3: Clear Selection
```
1. Auto-detect product
2. กด Clear Selection
Expected: Product selection และ preview ถูกล้าง
```

## Log และ Monitoring

### Log Messages:
```
# เมื่อพบ negative valuation
Product [3FG-PSS106-PM470-05]: Found negative valuation - Qty: -1.0, Value: -43455.32

# เมื่อข้าม product ที่ทำแล้ว
Product [3FG-PSS106-PM470-05]: Skipping - recently processed

# เมื่อ auto-detect เสร็จ
Auto-detection complete: Found 5 products with issues
```

### การตรวจสอบ Log:
```bash
# ดู log ของ valuation regenerate
grep -i "valuation\|negative\|auto-detect" /var/log/odoo17/instance1.log
```

## Version
- **Version:** 1.1.0
- **Date:** October 25, 2024
- **Author:** Odoo Development Team
- **Module:** buz_valuation_regenerate
