# Receipt Print Configuration Module

## Overview
โมดูลนี้เพิ่มความสามารถในการตั้งค่าตำแหน่งการพิมพ์สำหรับใบเสร็จแบบพรีพริ้นท์ โดยนำแนวคิดจาก `buz_inventory_delivery_report` มาปรับใช้

## Features (คุณสมบัติ)

### 1. Receipt Print Configuration (การตั้งค่าการพิมพ์ใบเสร็จ)
- ตั้งค่าตำแหน่งของแต่ละฟิลด์บนใบเสร็จได้อย่างละเอียด (ในหน่วย pixels)
- รองรับกระดาษขนาด Letter (216mm x 279mm)
- ปรับขนาดตัวอักษร (Font Size) ได้ 3 ระดับ:
  - Base Font (ตัวอักษรพื้นฐาน): 16px
  - Header Font (หัวข้อ): 18px
  - Small Font (ตัวอักษรเล็ก): 14px

### 2. Configurable Fields (ฟิลด์ที่สามารถตั้งค่าได้)

#### Receipt Header (ส่วนหัวใบเสร็จ)
- เลขที่ใบเสร็จ (Receipt Number)
- วันที่ออกใบเสร็จ (Receipt Date)

#### Payer Information (ข้อมูลผู้จ่ายเงิน)
- ชื่อผู้จ่ายเงิน (Payer Name)
- ที่อยู่ผู้จ่ายเงิน (Payer Address)

#### Payment Details (รายละเอียดการชำระเงิน)
- รายละเอียดการชำระ (Payment Description)
- จำนวนเงิน (ตัวเลข) (Amount Numbers)
- จำนวนเงิน (ตัวอักษร) (Amount Words)
- วิธีการชำระเงิน (Payment Method)

#### Check/Transfer Details (รายละเอียดเช็ค/โอนเงิน)
- เลขที่เช็ค (Check Number)
- ชื่อธนาคาร (Bank Name)
- วันที่เช็ค (Check Date)

#### Signatures (ลายเซ็น)
- ลายเซ็นผู้จ่ายเงิน (Payer Signature)
- ลายเซ็นผู้รับเงิน (Receiver Signature)

### 3. Quick Setup Wizard (วิซาร์ดตั้งค่าแบบรวดเร็ว)
สามารถปรับตำแหน่งทั้งหมดพร้อมกันได้ด้วย:
- Move Horizontally (เลื่อนซ้าย-ขวา): +/- pixels
- Move Vertically (เลื่อนขึ้น-ลง): +/- pixels
- Adjust Font Size (ปรับขนาดตัวอักษร): +/- pixels

### 4. Background Template Support (รองรับรูปพื้นหลัง)
- อัพโหลดรูปแบบฟอร์มพรีพริ้นท์เป็นพื้นหลัง
- ปรับความโปร่งแสง (Opacity) ได้
- ช่วยในการจัดวางตำแหน่งให้ตรงกับฟอร์มจริง

### 5. Validation & Safety (การตรวจสอบและความปลอดภัย)
- ตรวจสอบขนาดตัวอักษรให้อยู่ในช่วง 6-72 pixels
- ตรวจสอบค่า opacity ให้อยู่ในช่วง 0.0-1.0
- รองรับการตั้งค่าหลายชุด (Multiple Configurations)
- มี Default Configuration เพียงหนึ่งเดียว

## Installation (การติดตั้ง)

1. คัดลอกโมดูลไปยังโฟลเดอร์ custom-addons
2. Update Apps List ใน Odoo
3. ค้นหา "Pre-printed Receipt"
4. คลิก Install

## Configuration (การตั้งค่า)

### วิธีที่ 1: ผ่าน Menu
1. ไปที่ **Accounting > Configuration > Receipt Print Config**
2. เลือก "Default Receipt Layout" หรือสร้าง Configuration ใหม่
3. ปรับค่าในแท็บต่างๆ:
   - **Font Settings**: ตั้งค่าขนาดตัวอักษร
   - **Receipt Header**: ตำแหน่งเลขที่และวันที่
   - **Payer Information**: ตำแหน่งข้อมูลผู้จ่าย
   - **Payment Details**: ตำแหน่งรายละเอียดการชำระ
   - **Signatures**: ตำแหน่งลายเซ็น
   - **Background Template**: อัพโหลดรูปฟอร์มพรีพริ้นท์

### วิธีที่ 2: ใช้ Quick Setup Wizard
1. สร้างหรือเลือก Configuration
2. กรอกค่าปรับตำแหน่ง:
   - ต้องการเลื่อนทุกอย่างไปทางขวา 10px → กรอก +10 ใน "Move Horizontally"
   - ต้องการเลื่อนทุกอย่างลง 5px → กรอก +5 ใน "Move Vertically"
   - ต้องการเพิ่มขนาดตัวอักษร 2px → กรอก +2 ใน "Adjust Font Size"
3. คลิก "Apply Adjustments"

## Usage (การใช้งาน)

1. ไปที่ **Accounting > Customers > Payments** หรือ **Vendors > Payments**
2. เลือก Payment record ที่ต้องการพิมพ์
3. คลิก **Print > Pre-printed Receipt**
4. ใบเสร็จจะถูกสร้างตามการตั้งค่าใน Default Configuration

## Tips & Best Practices (เคล็ดลับและข้อแนะนำ)

### การปรับตำแหน่ง
1. **ใช้รูปพื้นหลัง**: อัพโหลดรูป scan ของฟอร์มพรีพริ้นท์เพื่อดูตำแหน่งที่ถูกต้อง
2. **เริ่มจากค่า Default**: แก้ไขจากค่า Default แทนการสร้างใหม่ทั้งหมด
3. **ใช้ Quick Setup**: สำหรับการปรับตำแหน่งครั้งละน้อย
4. **ทดสอบก่อนพิมพ์**: ใช้ Preview เพื่อตรวจสอบก่อนพิมพ์จริง

### ขนาดตัวอักษร
- **Preprint Form**: ใช้ขนาด 14-16px (เพราะฟอร์มมีข้อความอยู่แล้ว)
- **Blank Paper**: ใช้ขนาด 16-18px (ต้องการความชัดเจนมากกว่า)

### การจัดการหลาย Configuration
- สร้าง Configuration แยกสำหรับฟอร์มแต่ละแบบ
- ตั้งชื่อให้ชัดเจน เช่น "Receipt Form A", "Receipt Form B"
- เลือก Default Configuration ที่ใช้บ่อยที่สุด

## Technical Details (รายละเอียดทางเทคนิค)

### Models
- `receipt.print.config`: เก็บการตั้งค่าตำแหน่งการพิมพ์
- `receipt.print.quick.setup`: Wizard สำหรับปรับค่าแบบรวดเร็ว

### Key Fields in receipt.print.config
- Position fields: `*_top`, `*_left` (Integer, pixels)
- Size fields: `*_width`, `*_height` (Integer, pixels)
- Font fields: `font_size`, `font_size_header`, `font_size_small` (Integer, 6-72px)
- Display toggles: `show_*` (Boolean)

### Report Template
- Template ID: `buz_receipt_preprint.report_receipt_preprint_document`
- Uses dynamic positioning based on config values
- Supports background image overlay for alignment

## Comparison with Dispatch Report Module

| Feature | Dispatch Report | Receipt Print |
|---------|----------------|---------------|
| Target Document | Stock Picking / Delivery | Payment Receipt |
| Paper Size | A4 (210x297mm) | Letter (216x279mm) |
| Main Use Case | Delivery notes | Payment receipts |
| Complex Table | Yes (product lines) | No (single payment) |
| Config Fields | ~70+ fields | ~30 fields |
| Wizard Support | Yes | Yes |
| Background Template | Yes | Yes |

## Troubleshooting (การแก้ไขปัญหา)

### ปัญหา: ตำแหน่งไม่ตรง
- ตรวจสอบว่าใช้ Configuration ที่ถูกต้อง
- ตรวจสอบขนาดกระดาษในการตั้งค่าเครื่องพิมพ์
- ลองใช้ Quick Setup เพื่อปรับเล็กน้อย

### ปัญหา: ตัวอักษรเล็ก/ใหญ่เกินไป
- ปรับ `font_size`, `font_size_header`, `font_size_small` ใน Font Settings
- ค่าที่แนะนำ: 14-18px

### ปัญหา: รูปพื้นหลังไม่แสดง
- ตรวจสอบว่าเปิด `show_background` แล้ว
- ตรวจสอบว่าอัพโหลดรูปแล้ว
- ลองปรับ `background_opacity` ให้มากขึ้น

## Support & Development

### Module Information
- **Module Name**: buz_receipt_preprint
- **Version**: 17.0.1.0.0
- **Odoo Version**: 17.0
- **Depends**: base, account
- **License**: LGPL-3

### Development Notes
- Based on concept from `buz_inventory_delivery_report`
- Uses absolute positioning with pixel precision
- Template uses Qweb with dynamic style attributes
- Configuration stored in database (not hardcoded)

## Future Enhancements (การพัฒนาในอนาคต)
- [ ] Preview mode with live background overlay
- [ ] Import/Export configurations
- [ ] Multi-language support for field labels
- [ ] Mobile-responsive configuration interface
- [ ] Template library with pre-configured layouts
- [ ] Coordinate helper tool (visual editor)

---

**Last Updated**: December 2024  
**Implemented By**: Analysis and implementation based on dispatch report module concept
