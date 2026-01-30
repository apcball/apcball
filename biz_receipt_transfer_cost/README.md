# Receipt Transfer with Cost Price

## ภาพรวม / Overview

โมดูลนี้ใช้สำหรับกำหนดราคาต้นทุนสินค้าบน Receipt Transfer และสร้าง Inventory Valuation ตามราคาที่กำหนด

This module allows you to set custom cost price on receipt transfer and generate inventory valuation based on the specified price.

## คุณสมบัติ / Features

- ✅ เพิ่มฟิลด์ **Cost Price** บน Stock Move
- ✅ **Receipt จาก PO** → ดึงราคาจาก Purchase Order โดยอัตโนมัติ (ไม่สามารถแก้ไขได้)
- ✅ **Receipt แบบ Manual** → ดึงราคาจาก Product's Standard Price เป็นค่าเริ่มต้น (แก้ไขได้)
- ✅ เมื่อ Validate Receipt จะสร้าง **Inventory Valuation** ตามราคาที่กำหนด
- ✅ รองรับ **Multi-Company** (ดึงราคาตาม Company ที่ถูกต้อง)
- ✅ รองรับทั้ง Odoo **Community** และ **Enterprise**

## Use Cases

1. **Receipt โดยไม่ผ่าน Purchase Order** - ต้องการระบุราคาต้นทุนเอง
2. **ปรับราคาต้นทุนสินค้าขณะรับเข้า** - กรณีราคาจริงต่างจากราคามาตรฐาน
3. **Landed Cost / Additional Cost** - ที่ต้องการรวมเข้าต้นทุน

## วิธีใช้งาน / How to Use

### กรณี Receipt จาก Purchase Order
1. สร้าง Purchase Order และ Confirm
2. คลิก **Receipt** จาก PO
3. ราคาต้นทุนจะถูกดึงมาจาก PO โดยอัตโนมัติ (readonly)
4. Validate Receipt

### กรณี Receipt แบบ Manual (ไม่มี PO)
1. ไปที่ Inventory > Operations > Receipts
2. สร้าง Receipt ใหม่
3. เพิ่มสินค้า - ราคา **Cost Price** จะแสดงจาก Product's Standard Price
4. แก้ไขราคาได้ตามต้องการ
5. Validate Receipt

### ตรวจสอบ Inventory Valuation
- ไปที่ Inventory > Reporting > Stock Valuation
- จะเห็น Unit Value และ Total Value ตามราคาที่กำหนด

## Dependencies

- `stock` - Stock Management
- `stock_account` - Stock Accounting
- `purchase_stock` - Purchase Stock Integration

## Technical Details

### Models Extended
- `stock.move` - เพิ่ม fields:
  - `custom_cost_price` - ราคาต้นทุนที่กำหนดเอง
  - `use_custom_cost` - Flag เปิดใช้ custom cost
  - `is_from_purchase` - Computed field ระบุว่ามาจาก PO หรือไม่

### Key Methods Override
- `_get_default_cost_price()` - ดึงราคาจาก PO หรือ Product Standard Price
- `_get_price_unit()` - Return custom cost price if set
- `_get_in_svl_vals()` - สร้าง Stock Valuation Layer ด้วยราคาที่กำหนด
- `create()` - Set default cost price เมื่อสร้าง record

### Views Modified
- Stock Picking Form - เพิ่มคอลัมน์ Cost Price ใน Operations tab
- Stock Move Form - เพิ่มฟิลด์ Custom Cost Price
- Stock Move Tree - เพิ่มคอลัมน์ Cost Price (optional)

## Version History

- **17.0.1.1.0** - เพิ่มการดึงราคาจาก PO และ readonly เมื่อรับจาก PO
- **17.0.1.0.0** - Initial release

## Author



## License

LGPL-3
