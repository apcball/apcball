# คู่มือการตั้งค่าตำแหน่งแบบเต็มหน้ากระดาษ A4
# Full Page A4 Positioning Guide

## ภาพรวม (Overview)

โมดูล Dispatch Report รองรับการปรับตำแหน่งฟิลด์ต่างๆ ได้เต็มหน้ากระดาษ A4 โดยไม่มีข้อจำกัด 
The Dispatch Report module supports positioning fields anywhere on the full A4 page without limitations.

## ขนาดหน้ากระดาษ A4 (A4 Page Dimensions)

### ที่ DPI 96 (มาตรฐานหน้าจอ)
- **ความกว้าง (Width)**: 794 pixels = 210mm
- **ความสูง (Height)**: 1123 pixels = 297mm
- **ช่วงตำแหน่งแนวนอน (Horizontal Range)**: 0 - 794px
- **ช่วงตำแหน่งแนวตั้ง (Vertical Range)**: 0 - 1123px

### การคำนวณ (Calculation)
```
1 มิลลิเมตร (mm) = 3.78 pixels ที่ 96 DPI
210mm × 3.78 = 794px (ความกว้าง)
297mm × 3.78 = 1123px (ความสูง)
```

## วิธีการตั้งค่าตำแหน่ง (How to Position Fields)

### 1. การใช้พิกัด Pixels
ทุก field มีพิกัดสองค่า:
- **Top (px)**: ระยะจากด้านบนของกระดาษ (0-1123)
- **Left (px)**: ระยะจากด้านซ้ายของกระดาษ (0-794)

#### ตัวอย่าง (Examples):
```
มุมซ้ายบน (Top Left):     top=0,    left=0
มุมขวาบน (Top Right):    top=0,    left=794
ตรงกลาง (Center):        top=561,  left=397
มุมซ้ายล่าง (Bottom Left): top=1123, left=0
```

### 2. การใช้ Background Image เพื่อช่วยวางตำแหน่ง

1. สแกนหรือถ่ายรูปแบบฟอร์มที่พิมพ์ไว้แล้ว
2. ไปที่ **Inventory > Configuration > Dispatch Report Config**
3. เปิด Configuration ที่ต้องการ
4. ไปที่แท็บ **Background Image**
5. อัพโหลดรูปแบบฟอร์ม
6. คลิก **Preview Layout** เพื่อดูตำแหน่งที่ตั้งค่าไว้ทับกับรูปพื้นหลัง
7. ปรับค่า Top และ Left ของแต่ละ field ให้ตรงตามแบบฟอร์ม
8. ทดสอบซ้ำจนกว่าจะพอใจ

### 3. การใช้ Grid Overlay ใน Preview

Preview mode จะแสดง:
- **Grid lines**: เส้นตารางช่วงละ 50px เพื่อให้ง่ายต่อการวัดตำแหน่ง
- **Corner markers**: เครื่องหมายมุมสีแดง 4 มุมแสดงขอบเขตของหน้ากระดาษ
- **Position labels**: กล่องข้อความสีเหลืองแสดงตำแหน่งที่ตั้งค่าไว้
- **Dimension info**: ข้อมูลขนาดหน้าและการตั้งค่าที่มุมล่างซ้าย

## ส่วนประกอบต่างๆ และตำแหน่งเริ่มต้น (Components and Default Positions)

### Header Section (ส่วนหัว)
| Field | Default Top | Default Left | Description |
|-------|-------------|--------------|-------------|
| Document Number | 130px | 240px | เลขที่เอกสาร |
| Document Date | 130px | 580px | วันที่เอกสาร |

### Customer Information (ข้อมูลลูกค้า)
| Field | Default Top | Default Left | Description |
|-------|-------------|--------------|-------------|
| Customer Name | 193px | 210px | ชื่อลูกค้า |
| Customer Address | 225px | 210px | ที่อยู่ลูกค้า |
| Customer Phone | 257px | 587px | เบอร์โทรศัพท์ |

### Vehicle Information (ข้อมูลยานพาหนะ)
| Field | Default Top | Default Left | Description |
|-------|-------------|--------------|-------------|
| Vehicle Type | 220px | 560px | ประเภทรถ |
| Vehicle Plate | 225px | 660px | ทะเบียนรถ |
| Driver Name | 257px | 50px | ชื่อพนักงานขับรถ |
| Dispatch Location | 275px | 210px | สถานที่จัดส่ง |

### Product Table (ตารางสินค้า)
| Setting | Default Value | Description |
|---------|---------------|-------------|
| Table Top | 350px | ตำแหน่งบนของตาราง |
| Table Left | 35px | ตำแหน่งซ้ายของตาราง |
| Line Height | 28px | ความสูงแต่ละแถว |
| Max Lines | 15 | จำนวนแถวสูงสุด |

#### Column Offsets (ตำแหน่งคอลัมน์ - นับจากซ้ายของตาราง)
- No. Column: 10px
- Code Column: 55px
- Name Column: 160px
- Qty Column: 445px
- Unit Column: 520px
- Remark Column: 595px

### Footer & Signatures (ส่วนท้ายและลายเซ็น)
| Field | Default Top | Default Left | Description |
|-------|-------------|--------------|-------------|
| Total Quantity | 900px | 445px | ยอดรวมจำนวน |
| Sender Signature | 1000px | 110px | ลายเซ็นผู้ส่ง |
| Receiver Signature | 1000px | 450px | ลายเซ็นผู้รับ |

## เคล็ดลับการใช้งาน (Tips & Tricks)

### 1. การย้ายทุก Field พร้อมกัน
ใช้ Quick Setup Wizard:
- ไปที่ Configuration form
- คลิก "Quick Adjust All Positions"
- ใส่ค่า offset ที่ต้องการ (+ หรือ -)
- คลิก Apply

### 2. การเพิ่มพื้นที่สำหรับเนื้อหา
คลิกปุ่ม **Optimize for Full Page**:
- ตั้งค่า margin ทุกด้านเป็น 0
- ขยายความกว้างตารางเป็น 754px (เต็มหน้า)
- เพิ่มจำนวนแถวสูงสุดเป็น 18 แถว
- ลดระยะห่างระหว่างแถวเล็กน้อย

### 3. การรีเซ็ตค่าเริ่มต้น
คลิกปุ่ม **Reset to A4 Defaults**:
- จะรีเซ็ตทุกค่ากลับไปเป็นค่าเริ่มต้นสำหรับ A4

### 4. การใช้หลาย Configuration
สามารถสร้าง Configuration หลายชุดสำหรับแบบฟอร์มต่างๆ:
- กำหนด Configuration หนึ่งเป็น "Default"
- สร้าง Configuration อื่นๆ สำหรับฟอร์มพิเศษ
- เลือกใช้ Configuration ที่ต้องการเมื่อพิมพ์

## การแก้ปัญหา (Troubleshooting)

### ปัญหา: ตำแหน่งไม่ตรงเมื่อพิมพ์
**วิธีแก้:**
1. ตรวจสอบว่าเครื่องพิมพ์ตั้งค่าเป็น A4
2. ตรวจสอบ Scaling/Fit to Page = 100% หรือ None
3. ตรวจสอบ Margins = 0 ทุกด้าน
4. ใน Print Dialog เลือก "Actual Size" หรือ "100%"

### ปัญหา: ข้อความโดนตัด
**วิธีแก้:**
1. เพิ่มค่า `max_width` ของฟิลด์นั้นๆ
2. ลดขนาดตัวอักษร (font_size)
3. ปรับ word-wrap หรือ truncate

### ปัญหา: Preview ไม่แสดงผล
**วิธีแก้:**
1. Clear browser cache
2. Restart Odoo service
3. ตรวจสอบ static files ที่ `/static/fonts/`

## Advanced: การแปลงหน่วย (Unit Conversion)

### Pixels to Millimeters (at 96 DPI)
```python
mm = px / 3.78
```

### Millimeters to Pixels (at 96 DPI)
```python
px = mm * 3.78
```

### ตัวอย่าง Conversion Table:
| mm | px (96 DPI) | Description |
|----|-------------|-------------|
| 10mm | 38px | ~1 cm |
| 25mm | 94px | ~2.5 cm |
| 50mm | 189px | ~5 cm |
| 100mm | 378px | ~10 cm |
| 150mm | 567px | ~15 cm |
| 200mm | 756px | ~20 cm |

## การใช้งานผ่าน Code (Developer Guide)

### การสร้าง Config ใหม่
```python
config = env['dispatch.report.config'].create({
    'name': 'My Custom Layout',
    'doc_number_top': 150,
    'doc_number_left': 300,
    # ... other fields
})
```

### การดึง Config เริ่มต้น
```python
config = env['dispatch.report.config'].get_default_config()
```

### การแปลงหน่วย
```python
# MM to PX
px_value = config.get_mm_to_px(50)  # 50mm to px

# PX to MM
mm_value = config.get_px_to_mm(189)  # 189px to mm
```

## สรุป (Summary)

โมดูลนี้รองรับการปรับตำแหน่งอย่างเต็มรูปแบบบนหน้ากระดาษ A4:
- ✅ รองรับทุกตำแหน่งบนหน้ากระดาษ (0-794px horizontal, 0-1123px vertical)
- ✅ ไม่มี margins บังคับ (สามารถตั้งเป็น 0 ได้)
- ✅ Preview พร้อม Background Image overlay
- ✅ Grid และ rulers สำหรับวัดตำแหน่ง
- ✅ Quick adjustment tools
- ✅ หลาย configurations

ใช้ Preview + Background Image เป็นเครื่องมือหลักในการปรับตำแหน่งให้แม่นยำ!
