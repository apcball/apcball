# คู่มือการใช้งานระบบตั้งค่าการพิมพ์ใบเสร็จ
# Receipt Print Configuration - Thai Quick Guide

## สรุปการพัฒนา

โมดูล `buz_receipt_preprint` ได้รับการพัฒนาโดยนำแนวคิดจากโมดูล `buz_inventory_delivery_report` มาประยุกต์ใช้ โดยเพิ่มระบบการตั้งค่าตำแหน่งการพิมพ์แบบละเอียด (Configurable Print Positions) เพื่อรองรับการพิมพ์บนฟอร์มพรีพริ้นท์

## ✨ ฟีเจอร์หลัก

### 1. 📋 Receipt Print Configuration Model
**ไฟล์**: `models/receipt_print_config.py`

จัดเก็บการตั้งค่าตำแหน่งการพิมพ์ทั้งหมด ประกอบด้วย:

#### ส่วนหัวใบเสร็จ (Receipt Header)
- `receipt_number_top/left`: ตำแหน่งเลขที่ใบเสร็จ
- `receipt_date_top/left`: ตำแหน่งวันที่ออกใบเสร็จ

#### ข้อมูลผู้จ่ายเงิน (Payer Information)
- `payer_name_top/left/width`: ชื่อผู้จ่ายเงิน
- `payer_address_top/left/width`: ที่อยู่ผู้จ่ายเงิน

#### รายละเอียดการชำระเงิน (Payment Details)
- `payment_description_top/left/width`: รายละเอียดการชำระ
- `amount_numbers_top/left`: จำนวนเงิน (ตัวเลข)
- `amount_words_top/left/width`: จำนวนเงิน (ตัวอักษร)
- `payment_method_top/left`: วิธีการชำระเงิน

#### รายละเอียดเช็ค/โอนเงิน (Check/Transfer)
- `check_number_top/left`: เลขที่เช็ค
- `bank_name_top/left`: ชื่อธนาคาร
- `check_date_top/left`: วันที่เช็ค

#### ลายเซ็น (Signatures)
- `signature_payer_top/left`: ลายเซ็นผู้จ่ายเงิน
- `signature_receiver_top/left`: ลายเซ็นผู้รับเงิน
- `signature_line_height`: ระยะสำหรับลายเซ็น
- `signature_date_offset`: ระยะห่างวันที่ใต้ลายเซ็น

#### การตั้งค่าตัวอักษร (Font Settings)
- `font_size`: ขนาดตัวอักษรพื้นฐาน (16px)
- `font_size_header`: ขนาดตัวอักษรหัวข้อ (18px)
- `font_size_small`: ขนาดตัวอักษรเล็ก (14px)
- `font_family`: ชนิดตัวอักษร (THSarabunNew)
- `line_spacing`: ระยะห่างระหว่างบรรทัด (1.2)

#### การตั้งค่ากระดาษ (Page Settings)
- `paper_size`: ขนาดกระดาษ (Letter = 216x279mm)
- `page_width/height`: ขนาดในหน่วย pixels (816x1056px)
- `margin_top/bottom/left/right`: ระยะขอบ (3mm)
- `dpi`: ความละเอียด (96 DPI)

#### รูปพื้นหลัง (Background Template)
- `background_image`: รูปแบบฟอร์มพรีพริ้นท์
- `show_background`: เปิด/ปิดการแสดงพื้นหลัง
- `background_opacity`: ความโปร่งแสง (0.3)

### 2. 🎯 Quick Setup Wizard
**ไฟล์**: `wizard/receipt_print_quick_setup.py`

ปรับตำแหน่งทั้งหมดพร้อมกันได้ด้วย:
- **Move Horizontally**: เลื่อนซ้าย-ขวา (+/- pixels)
- **Move Vertically**: เลื่อนขึ้น-ลง (+/- pixels)
- **Adjust Font Size**: เพิ่ม/ลดขนาดตัวอักษร (+/- pixels)

### 3. 🎨 Dynamic Receipt Template
**ไฟล์**: `reports/receipt_templates.xml`

Template ที่ปรับตำแหน่งอัตโนมัติตามการตั้งค่า:
- ใช้ค่าจาก `receipt.print.config`
- รองรับรูปพื้นหลัง
- Responsive กับการตั้งค่าต่างๆ

## 📁 โครงสร้างไฟล์

```
buz_receipt_preprint/
├── __init__.py                              # Import modules
├── __manifest__.py                          # Module manifest (updated)
├── README.md                                # English documentation
├── README_TH.md                            # Thai documentation
│
├── models/
│   ├── __init__.py                         # Import models
│   ├── receipt.py                          # Account Payment extension (updated)
│   └── receipt_print_config.py             # ✨ NEW: Print config model
│
├── views/
│   ├── receipt_views.xml                   # Original views
│   └── receipt_print_config_views.xml      # ✨ NEW: Config form & tree views
│
├── wizard/
│   ├── __init__.py                         # ✨ NEW: Import wizard
│   ├── receipt_print_quick_setup.py        # ✨ NEW: Quick setup wizard
│   └── receipt_print_quick_setup_views.xml # ✨ NEW: Wizard views
│
├── data/
│   └── receipt_print_config_data.xml       # ✨ NEW: Default configuration
│
├── reports/
│   └── receipt_templates.xml               # Updated to use config
│
└── security/
    └── ir.model.access.csv                 # Updated with new models
```

## 🚀 วิธีการใช้งาน

### ขั้นตอนที่ 1: ติดตั้งโมดูล
1. Upgrade โมดูล `buz_receipt_preprint`
2. ระบบจะสร้าง Default Configuration อัตโนมัติ

### ขั้นตอนที่ 2: ตั้งค่าตำแหน่งการพิมพ์

#### วิธีที่ 1: ใช้ Menu Configuration
```
Accounting > Configuration > Receipt Print Config
```

1. เปิด "Default Receipt Layout"
2. ไปที่แท็บ **Background Template**
3. อัพโหลดรูป scan ของฟอร์มพรีพริ้นท์
4. เปิด "Show Background in Preview"
5. ปรับ Opacity ให้เห็นทั้งพื้นหลังและข้อมูล
6. ปรับตำแหน่งในแท็บต่างๆ ให้ตรงกับฟอร์ม

#### วิธีที่ 2: ใช้ Quick Setup Wizard
เหมาะสำหรับปรับค่าเล็กน้อย:

```
เลื่อนทั้งหมดไปทางขวา 5 pixels:
Move Horizontally: +5

เลื่อนทั้งหมดลง 10 pixels:
Move Vertically: +10

เพิ่มขนาดตัวอักษร 2 pixels:
Adjust Font Size: +2
```

### ขั้นตอนที่ 3: พิมพ์ใบเสร็จ
1. ไปที่ Payment ที่ต้องการพิมพ์
2. คลิก **Print > Pre-printed Receipt**
3. ตรวจสอบ Preview
4. พิมพ์บนฟอร์มพรีพริ้นท์

## 🎓 เทคนิคการตั้งค่า

### 1. การใช้รูปพื้นหลัง
```
1. Scan ฟอร์มพรีพริ้นท์ความละเอียดสูง (300 DPI)
2. Save เป็นไฟล์ PNG หรือ JPG
3. อัพโหลดใน Background Image
4. ตั้ง Opacity = 0.3-0.5 เพื่อเห็นทั้งสองส่วน
5. ปรับตำแหน่งให้ตรงกับช่องในรูป
```

### 2. การปรับขนาดตัวอักษร
```
ฟอร์มพรีพริ้นท์:
- Base: 14-16px (ข้อมูลทั่วไป)
- Header: 16-18px (หัวข้อ)
- Small: 12-14px (หมายเหตุ)

กระดาษเปล่า:
- Base: 16-18px
- Header: 18-22px
- Small: 14-16px
```

### 3. การวัดตำแหน่ง
```
หน่วยที่ใช้: pixels (px)
ต้นทางการวัด: มุมซ้ายบนของกระดาษ

ตัวอย่าง:
- Top = 100px หมายถึง ห่างจากขอบบน 100 pixels
- Left = 50px หมายถึง ห่างจากขอบซ้าย 50 pixels

ขนาดกระดาษ Letter ที่ 96 DPI:
- Width = 816px (216mm)
- Height = 1056px (279mm)
```

## 🔧 Validation & Safety Features

### 1. Font Size Validation
```python
@api.constrains('font_size', 'font_size_header', 'font_size_small')
def _check_font_sizes(self):
    # ตรวจสอบว่าขนาดตัวอักษรอยู่ในช่วง 6-72 pixels
```

### 2. Unique Default Configuration
```python
@api.constrains('is_default')
def _check_default_unique(self):
    # ตรวจสอบให้มี Default Configuration เพียงหนึ่งเดียว
```

### 3. Background Opacity Validation
```python
@api.constrains('background_opacity')
def _check_opacity(self):
    # ตรวจสอบค่า opacity อยู่ในช่วง 0.0-1.0
```

## 📊 เปรียบเทียบกับ Dispatch Report

| ส่วนประกอบ | Dispatch Report | Receipt Print |
|-----------|----------------|---------------|
| **Model** | dispatch.report.config | receipt.print.config |
| **Wizard** | dispatch.report.quick.setup | receipt.print.quick.setup |
| **เอกสาร** | ใบส่งของ/Delivery | ใบเสร็จรับเงิน/Receipt |
| **ความซับซ้อน** | สูง (มีตารางสินค้า) | ต่ำ (ข้อมูลเดียว) |
| **จำนวนฟิลด์** | ~70+ fields | ~30 fields |
| **กระดาษ** | A4 (210x297mm) | Letter (216x279mm) |

## 🎯 ข้อดีของการออกแบบนี้

### 1. ✅ Flexible (ยืดหยุ่น)
- ปรับตำแหน่งได้ทุกฟิลด์
- รองรับฟอร์มหลายแบบ
- สร้าง Configuration ได้ไม่จำกัด

### 2. ✅ User-Friendly (ใช้งานง่าย)
- มี Quick Setup Wizard
- มีคำแนะนำในหน้าฟอร์ม
- รองรับรูปพื้นหลัง

### 3. ✅ Safe (ปลอดภัย)
- มีการ validate ค่าต่างๆ
- มี default values
- ป้องกันข้อผิดพลาด

### 4. ✅ Maintainable (ดูแลรักษาง่าย)
- แยกส่วนชัดเจน (Model, View, Wizard)
- มีเอกสารประกอบ
- ใช้ naming convention มาตรฐาน

## 🐛 Troubleshooting

### ปัญหา 1: ตำแหน่งไม่ตรงกับฟอร์ม
**วิธีแก้**:
1. ตรวจสอบว่าใช้ Configuration ที่ถูกต้อง
2. ใช้ Quick Setup เพื่อปรับตำแหน่งเล็กน้อย
3. ตรวจสอบการตั้งค่าเครื่องพิมพ์ (Paper Size, Margins)

### ปัญหา 2: ตัวอักษรเล็ก/ใหญ่เกินไป
**วิธีแก้**:
1. ปรับค่าใน Font Settings tab
2. ใช้ Quick Setup > Adjust Font Size
3. ลองค่า 14-18px สำหรับฟอร์มพรีพริ้นท์

### ปัญหา 3: รูปพื้นหลังไม่แสดง
**วิธีแก้**:
1. ตรวจสอบ "Show Background" เปิดอยู่
2. ตรวจสอบว่าอัพโหลดรูปแล้ว
3. ปรับ Background Opacity ให้มากขึ้น (0.5-0.7)

### ปัญหา 4: Error เมื่อ Install/Upgrade
**วิธีแก้**:
1. ตรวจสอบ dependencies (base, account)
2. ตรวจสอบ Python syntax ใน models
3. ดู error log ใน Odoo

## 📝 Checklist การ Implement

### ✅ Models
- [x] สร้าง `receipt_print_config.py` 
- [x] เพิ่ม method `get_print_config()` ใน `receipt.py`
- [x] เพิ่ม validation constraints
- [x] เพิ่ม default methods

### ✅ Views
- [x] สร้าง form view สำหรับ config
- [x] สร้าง tree view สำหรับ config
- [x] เพิ่ม menu item
- [x] เพิ่มคำแนะนำและ tooltips

### ✅ Wizard
- [x] สร้าง quick setup model
- [x] สร้าง wizard form view
- [x] implement adjustment logic

### ✅ Data
- [x] สร้าง default configuration
- [x] ตั้งค่า default values

### ✅ Security
- [x] เพิ่ม access rights สำหรับ user
- [x] เพิ่ม access rights สำหรับ manager
- [x] เพิ่ม access rights สำหรับ wizard

### ✅ Template
- [x] อัพเดท template ให้ใช้ config
- [x] เพิ่ม dynamic positioning
- [x] รองรับ background image
- [x] รองรับ responsive font sizes

### ✅ Documentation
- [x] สร้าง README.md (English)
- [x] สร้าง README_TH.md (Thai)
- [x] เพิ่ม comments ในโค้ด
- [x] อัพเดท __manifest__.py

## 🎉 สรุป

โมดูล `buz_receipt_preprint` ได้รับการปรับปรุงให้มีระบบการตั้งค่าการพิมพ์ที่ทันสมัยและยืดหยุ่น โดยนำแนวคิดจาก `buz_inventory_delivery_report` มาประยุกต์ใช้ ทำให้สามารถปรับตำแหน่งการพิมพ์ให้ตรงกับฟอร์มพรีพริ้นท์ได้อย่างแม่นยำ

### คุณสมบัติเด่น:
- ⚙️ ปรับตำแหน่งได้ทุกฟิลด์
- 🎨 รองรับรูปพื้นหลัง
- ⚡ Quick Setup Wizard
- 🔒 Validation & Safety
- 📱 User-friendly Interface
- 📚 เอกสารครบถ้วน

---

**วันที่อัพเดท**: ธันวาคม 2024  
**ผู้พัฒนา**: Implementation based on dispatch report module analysis
