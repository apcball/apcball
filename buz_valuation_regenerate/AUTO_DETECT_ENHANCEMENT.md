# Auto-Detect Products Enhancement - Valuation Regenerate Module

## Overview
เพิ่มฟีเจอร์ตรวจจับสินค้าที่มีปัญหา valuation โดยอัตโนมัติ เมื่อเลือก location แล้วกด "Compute Plan"

## Version
- Updated from: `17.0.1.1.0`
- Updated to: `17.0.1.2.0`

## Changes Made

### 1. Wizard Model (`models/valuation_regenerate_wizard.py`)

#### เพิ่ม Field ใหม่
- `auto_detect_products`: Boolean field เพื่อเปิด/ปิดการตรวจจับอัตโนมัติ
  - Default: `False`
  - แสดงเฉพาะเมื่อมีการเลือก `location_ids`
  - Help text: "Automatically find and select products with potential valuation issues in selected locations"

- `check_missing_account_moves`: Boolean field เพื่อเปิด/ปิดการตรวจสอบ Missing Account Moves
  - Default: `False`
  - แสดงเฉพาะเมื่อเปิดใช้ `auto_detect_products`
  - Help text: "Include check for SVLs without account moves (disable for manual valuation)"
  - **สำคัญ**: ปิดไว้สำหรับระบบที่ใช้ manual valuation

#### เพิ่ม Method ใหม่
- `_auto_detect_products_with_issues()`: ค้นหาสินค้าที่มีปัญหา valuation
  
  **การทำงาน:**
  1. ค้นหา stock moves ทั้งหมดใน locations ที่เลือก (ภายในช่วงวันที่ที่กำหนด)
  2. ดึงรายการสินค้าที่มี moves ใน locations เหล่านั้น
  3. ตรวจสอบแต่ละสินค้าหาปัญหา:
  
  **ปัญหาที่ตรวจจับได้:**
  
  a) **Missing SVLs (SVL หายไป)**
     - Stock moves ที่ไม่มี SVL ที่เกี่ยวข้อง
     - เกิดเมื่อระบบไม่สร้าง valuation layer ให้กับการเคลื่อนไหวสินค้า
  
  b) **Zero Value SVLs (SVL มีมูลค่าเป็น 0)**
     - SVLs ที่มี quantity ไม่เท่ากับ 0 แต่ value = 0
     - ไม่ถูกต้องเพราะควรมีมูลค่าตาม cost ของสินค้า
  
  c) **Missing Account Moves (ไม่มี Journal Entry)** - OPTIONAL
     - SVLs ที่มีมูลค่าแต่ไม่มี account_move_id
     - เกิดเมื่อมี valuation layer แต่ไม่สร้าง journal entry ในบัญชี
     - ตรวจสอบเฉพาะสินค้าที่ใช้ real_time valuation
     - **ต้องเปิดใช้ "Check Missing Account Moves" เท่านั้น**
     - **ไม่แนะนำสำหรับระบบที่ใช้ manual valuation**

#### แก้ไข Method
- `action_compute_plan()`: เพิ่ม logic ตรวจจับสินค้าอัตโนมัติ
  ```python
  if self.auto_detect_products and self.location_ids:
      detected_products = self._auto_detect_products_with_issues()
      if detected_products:
          self.product_ids = [(6, 0, detected_products.ids)]
  ```

### 2. Wizard View (`views/wizard_views.xml`)

#### เพิ่มในหน้า Form
- เพิ่มฟิลด์ `auto_detect_products` ข้างล่าง `location_ids`
- ใช้ `invisible="not location_ids"` เพื่อแสดงเฉพาะเมื่อมีการเลือก location

### 3. Manifest (`__manifest__.py`)

#### อัพเดท
- Version: เปลี่ยนเป็น `17.0.1.2.0`
- Description: เพิ่มบรรทัด "Auto-detect products with valuation issues in selected locations (new in v1.2.0)"

## วิธีใช้งาน

### ขั้นตอนการใช้งาน Auto-Detect

1. **เปิด Wizard**: Inventory → Operations → Re-Generate Valuation Layers

2. **ตั้งค่าเบื้องต้น**:
   - Company: เลือกบริษัท
   - Mode: เลือก "Products" (ไม่ต้องเลือกสินค้า)

3. **เลือก Location**: 
   - คลิกที่ฟิลด์ "Locations"
   - เลือก location(s) ที่ต้องการตรวจสอบ เช่น "WH/Stock"

4. **เปิดใช้งาน Auto-Detect**:
   - เมื่อเลือก location แล้ว จะเห็นช่อง "Auto-detect Products with Valuation Issues"
   - ✅ เปิดใช้งานช่องนี้
   - ✅ (Optional) เปิด "Check Missing Account Moves" ถ้าต้องการตรวจสอบ journal entries
     - **ข้อควรระวัง**: ปิดไว้ถ้าใช้ manual valuation (แนะนำให้ปิด)

5. **กำหนดช่วงวันที่ (Optional)**:
   - Date From: วันที่เริ่มต้น
   - Date To: วันที่สิ้นสุด

6. **กด "Compute Plan"** (ไม่ต้องเลือกสินค้า):
   - ระบบจะค้นหาสินค้าที่มีปัญหาโดยอัตโนมัติ
   - สินค้าที่พบปัญหาจะถูกเติมในฟิลด์ "Products" โดยอัตโนมัติ
   - แสดง notification พร้อมจำนวนสินค้าที่พบ
   - สามารถดูรายละเอียดใน Log

7. **ตรวจสอบผลลัพธ์**:
   - ดูรายการสินค้าที่ถูกเลือก (ใน Products field)
   - ดู Preview ของ SVLs และ Journal Entries ที่จะถูกลบและสร้างใหม่

8. **Apply (ถ้าต้องการ)**:
   - ปิด "Dry Run Mode"
   - กด "Apply Regeneration"

## ตัวอย่างการใช้งาน

### Scenario 1: ค้นหาสินค้าที่มีปัญหาใน WH/Stock (ไม่เลือกสินค้า)

```
1. Company: "Your Company"
2. Mode: "Products" (ไม่เลือกสินค้าใดๆ)
3. Locations: "WH/Stock"
4. Auto-detect: ✅ เปิดใช้งาน
5. Check Missing Account Moves: ❌ ปิด (เพราะใช้ manual valuation)
6. Date Range: 2024-01-01 ถึง 2024-12-31
7. กด "Compute Plan" (โดยไม่เลือกสินค้า)

ผลลัพธ์:
- ระบบพบ 150 stock moves ใน WH/Stock
- ค้นพบ 45 สินค้าที่มี moves
- ตรวจจับได้ 5 สินค้าที่มีปัญหา:
  * Product A: 3 moves ไม่มี SVL
  * Product B: 2 SVLs มีมูลค่า 0
  * Product C: 1 SVL ไม่มี account move
  * Product D: 5 moves ไม่มี SVL
  * Product E: 1 SVL มีมูลค่า 0
  
สินค้าทั้ง 5 รายการจะถูกเลือกอัตโนมัติในฟิลด์ "Products"
```

### Scenario 2: ตรวจสอบหลาย Location พร้อมกัน

```
1. Company: "Your Company"
2. Locations: "WH/Stock", "WH/Stock/Shelf 1", "WH/Stock/Shelf 2"
3. Auto-detect: ✅ เปิดใช้งาน
4. Date Range: ไม่กำหนด (ทั้งหมด)
5. กด "Compute Plan"

ผลลัพธ์:
- ค้นหาสินค้าที่มีปัญหาในทุก location ที่เลือก
- ตรวจสอบ moves ที่เกี่ยวข้องกับ location ใดๆ ที่เลือก (source หรือ destination)
```

## การตรวจจับปัญหา (Detection Logic)

### 1. Missing SVLs (SVL หายไป)

**เงื่อนไข:**
```python
moves_without_svl = product_moves - moves_with_svl
if moves_without_svl:
    # สินค้ามีปัญหา
```

**ตัวอย่างปัญหา:**
- มี Receipt (รับสินค้า) แต่ไม่มี SVL
- มี Delivery (ส่งสินค้า) แต่ไม่มี SVL
- มี Internal Transfer แต่ไม่มี SVL

### 2. Zero Value SVLs

**เงื่อนไข:**
```python
zero_value_svls = svls.filtered(lambda s: s.quantity != 0 and s.value == 0)
if zero_value_svls:
    # สินค้ามีปัญหา
```

**ตัวอย่างปัญหา:**
- รับสินค้า 10 ชิ้น แต่มูลค่า = 0 (ควรมีมูลค่าตาม cost)
- ส่งสินค้า 5 ชิ้น แต่มูลค่า = 0 (ควรตัดมูลค่าสต็อก)

### 3. Missing Account Moves (OPTIONAL)

**เงื่อนไข:**
```python
if self.check_missing_account_moves and product.valuation == 'real_time':
    svls_without_accounting = svls.filtered(
        lambda s: s.value != 0 and not s.account_move_id
    )
    if svls_without_accounting:
        # สินค้ามีปัญหา
```

**ตัวอย่างปัญหา:**
- มี SVL มูลค่า 1,000 บาท แต่ไม่สร้าง journal entry ในบัญชี
- เกิดเมื่อมีปัญหาในการสร้าง accounting entries

**หมายเหตุสำคัญ:**
- ❌ **ปิดการตรวจสอบนี้** ถ้าใช้ manual valuation
- ✅ เปิดเฉพาะระบบที่ใช้ automated (real-time) valuation
- การตรวจสอบนี้จะทำงานก็ต่อเมื่อเปิด "Check Missing Account Moves" เท่านั้น

## Logging

ระบบจะบันทึก log ทุกขั้นตอน:

```python
_logger.info("Auto-detecting products with valuation issues in 2 location(s)...")
_logger.info("Found 150 stock moves in selected locations")
_logger.info("Found 45 products with moves in selected locations")
_logger.info("Product [ABC123] Widget A: Found 3 moves without SVL")
_logger.info("Product [XYZ789] Gadget B: Found 2 SVLs with zero value but non-zero quantity")
_logger.info("Auto-detection complete: Found 5 products with issues")
```

## ข้อดี

1. **ประหยัดเวลา**: ไม่ต้องค้นหาสินค้าที่มีปัญหาด้วยตนเอง
2. **ความแม่นยำ**: ตรวจจับปัญหาแบบครอบคลุม (missing SVL, zero value, missing accounting)
3. **ยืดหยุ่น**: สามารถเลือกใช้หรือไม่ใช้ auto-detect ได้
4. **กรองตาม Location**: ตรวจสอบเฉพาะ location ที่สนใจ
5. **Audit Trail**: มี log บันทึกทุกขั้นตอนการตรวจจับ
6. **รองรับทั้ง Manual และ Automated Valuation**: สามารถปิดการตรวจสอบ account moves สำหรับ manual valuation

## ข้อจำกัด

1. **ต้องเลือก Location**: Auto-detect ทำงานเฉพาะเมื่อมีการเลือก location
2. **Real-time Valuation Only**: ตรวจสอบเฉพาะสินค้าที่ใช้ automated valuation (real_time)
3. **Performance**: หาก location มีสินค้าและ moves เยอะมาก อาจใช้เวลาในการตรวจสอบ

## Compatibility

- ✅ ทำงานร่วมกับ location filter
- ✅ ทำงานร่วมกับ date range filter
- ✅ ทำงานร่วมกับทั้ง FIFO และ AVCO costing
- ✅ Backward compatible: ไม่กระทบการทำงานเดิม

## Testing Recommendations

1. ทดสอบกับ location เดียว
2. ทดสอบกับหลาย locations
3. ทดสอบกับ date range ต่างๆ
4. ทดสอบกับสินค้าที่มีปัญหาจริง:
   - สินค้าที่ไม่มี SVL
   - สินค้าที่มี SVL มูลค่า 0
   - สินค้าที่ไม่มี account moves
5. ทดสอบการปิด auto-detect (ยังเลือกสินค้าเองได้ตามเดิม)
6. ตรวจสอบ log files

## Notes

- Auto-detect จะค้นหาสินค้าที่มี moves ใน location ที่เลือก (source OR destination)
- ระบบจะเลือกเฉพาะสินค้าที่ใช้ real-time valuation
- ผลลัพธ์จะเห็นได้ทันทีในฟิลด์ "Products"
- สามารถแก้ไขรายการสินค้าที่เลือกได้หลังจาก auto-detect แล้ว
- Log จะแสดงรายละเอียดว่าพบปัญหาอะไรในสินค้าแต่ละรายการ

### สำหรับระบบ Manual Valuation
- ❌ **อย่าเปิด** "Check Missing Account Moves"
- ระบบ manual valuation ไม่สร้าง journal entries อัตโนมัติ
- การตรวจสอบ account moves จะให้ผลลัพธ์ false positive
- ยังสามารถใช้การตรวจสอบ Missing SVLs และ Zero Value SVLs ได้ตามปกติ

### สำหรับระบบ Automated (Real-time) Valuation
- ✅ สามารถเปิด "Check Missing Account Moves" เพื่อหาปัญหาครบถ้วน
- ระบบจะตรวจสอบ SVLs ที่ไม่มี journal entries
- ช่วยหาปัญหาการสร้าง accounting entries ที่ผิดพลาด
