# แก้ไขปัญหา Font Size ปรับไม่ได้
# Fix for Font Size Cannot be Adjusted

## ปัญหา (Problem)
ไม่สามารถปรับขนาด Font Size ในหน้า Dispatch Report Print Config ได้

Cannot adjust Font Size in the Dispatch Report Print Config form.

## สาเหน่ของปัญหา (Root Cause)
- Field definition ไม่มีการระบุว่าเป็น required
- ไม่มี validation ที่ชัดเจนสำหรับ font size
- UI ไม่มีการแสดงข้อมูลที่ชัดเจนเกี่ยวกับขนาดตัวอักษร

- Field was not marked as required
- No clear validation for font sizes
- UI didn't provide clear information about font sizing

## การแก้ไข (Solution)

### 1. อัพเดท Model (models/dispatch_report_config.py)

**เปลี่ยนแปลง:**
- เพิ่ม `required=True` ให้กับ font_size fields
- เพิ่ม validation constraint เพื่อตรวจสอบขนาด font (6-72px)
- ปรับปรุง help text ให้ชัดเจนขึ้น

**Changes:**
- Added `required=True` to font_size fields
- Added validation constraint to check font sizes (6-72px range)
- Improved help text for clarity

**Code Changes:**
```python
font_size = fields.Integer(
    string='Font Size (px)', 
    default=14,
    required=True,  # NEW
    help='ขนาดตัวอักษรพื้นฐาน (Base font size for report text)'
)

# Added new constraint method
@api.constrains('font_size', 'font_size_header', 'font_size_small')
def _check_font_sizes(self):
    """Validate font sizes are within reasonable range"""
    for record in self:
        if record.font_size and (record.font_size < 6 or record.font_size > 72):
            raise ValidationError(...)
```

### 2. อัพเดท View (views/dispatch_report_config_views.xml)

**เปลี่ยนแปลง:**
- เพิ่ม page "Font Settings" ใหม่ในหน้าแรกของ notebook
- แสดงคำแนะนำขนาด font ที่เหมาะสม
- ปรับปรุง UI ให้ใช้งานง่ายขึ้น

**Changes:**
- Added new "Font Settings" page as first tab in notebook
- Display recommended font sizes
- Improved UI for better usability

**Features:**
- แยก Font Settings เป็นหน้าเฉพาะ
- แสดงค่าแนะนำสำหรับ Preprint Forms และ Blank Paper
- ระบุ valid range (6-72px)
- แสดงค่า default ที่แนะนำ

## วิธีการอัพเกรด Module (How to Upgrade)

### Option 1: ผ่าน UI (Via Odoo Interface)
1. เข้าสู่ระบบ Odoo ด้วย Admin
2. ไปที่เมนู Apps
3. ลบ filter "Apps" ออก
4. ค้นหา "buz_inventory_delivery_report"
5. คลิกปุ่ม "Upgrade"
6. รอจนกว่า upgrade จะเสร็จสมบูรณ์

### Option 2: ผ่าน Command Line
```bash
# รัน script อัพเกรด
./upgrade_module.sh

# หรือรันคำสั่ง Odoo โดยตรง
python3 /opt/instance1/odoo17/odoo-bin -c /path/to/odoo.conf \
    -d YOUR_DATABASE \
    -u buz_inventory_delivery_report \
    --stop-after-init
```

### Option 3: Restart Odoo Server (แนะนำ)
```bash
# หยุด Odoo service
sudo systemctl stop odoo17

# เริ่ม Odoo service ใหม่
sudo systemctl start odoo17

# ตรวจสอบสถานะ
sudo systemctl status odoo17
```

## การใช้งานหลังอัพเกรด (Usage After Upgrade)

### 1. เข้าถึง Font Settings
- ไปที่ Inventory > Configuration > Dispatch Report Config
- เปิด configuration ที่ต้องการแก้ไข
- คลิกที่ tab "Font Settings" (แท็บแรก)

### 2. ปรับขนาด Font
**Base Font Size (ขนาดตัวอักษรพื้นฐาน):**
- ใช้สำหรับข้อมูลทั่วไป
- แนะนำ: 12-16px (Preprint), 14-16px (Blank Paper)

**Header Font Size (ขนาดตัวอักษรหัวข้อ):**
- ใช้สำหรับหัวข้อเอกสาร
- แนะนำ: 14-16px (Preprint), 16-20px (Blank Paper)

**Small Font Size (ขนาดตัวอักษรเล็ก):**
- ใช้สำหรับหมายเหตุ
- แนะนำ: 10-12px (Preprint), 12-14px (Blank Paper)

### 3. ทดสอบการตั้งค่า
1. บันทึกการเปลี่ยนแปลง
2. ไปที่ Stock Picking
3. เลือก picking ที่ต้องการพิมพ์
4. คลิก Print > Dispatch Report
5. ตรวจสอบว่า font size ถูกต้องหรือไม่

## ค่าที่แนะนำ (Recommended Values)

### For Preprint Forms (สำหรับแบบฟอร์มพิมพ์ล่วงหน้า):
```
Base Font Size: 12-14px
Header Font Size: 14-16px
Small Font Size: 10-12px
```

### For Blank Paper (สำหรับกระดาษเปล่า):
```
Base Font Size: 14-16px
Header Font Size: 16-20px
Small Font Size: 12-14px
```

## การ Validate (Validation Rules)
- **ช่วงที่อนุญาต:** 6-72px
- **ค่า Default:** Base=14, Header=16, Small=12
- **Required:** ต้องระบุค่าทุกครั้ง

## หมายเหตุ (Notes)
- หลังจากอัพเกรด ค่า font size เดิมจะยังคงอยู่
- ถ้าต้องการ reset เป็นค่า default ให้คลิก "Reset to A4 Defaults"
- Font Family สามารถใช้ font หลายตัว เช่น "Sarabun, Arial, sans-serif"
- สามารถใช้ "Quick Adjust" เพื่อปรับ font size แบบรวดเร็ว

## การแก้ปัญหา (Troubleshooting)

### ปัญหา: Font size ยังปรับไม่ได้หลัง upgrade
**วิธีแก้:**
1. Clear browser cache (Ctrl+Shift+Delete)
2. Logout และ Login ใหม่
3. ตรวจสอบว่า module upgrade สำเร็จหรือไม่

### ปัญหา: ข้อผิดพลาด "Font size is invalid"
**วิธีแก้:**
- ตรวจสอบว่าขนาดอยู่ระหว่าง 6-72px
- ห้ามใส่ค่าเป็น 0 หรือค่าลบ

### ปัญหา: Font ไม่แสดงผลตามที่ตั้งค่า
**วิธีแก้:**
1. ตรวจสอบว่า Font Family มีใน system
2. ลองใช้ font มาตรฐาน เช่น Arial, sans-serif
3. ตรวจสอบ browser font settings

## เวอร์ชั่น (Version History)
- **v17.0.1.0.1** - แก้ไขปัญหา font size ปรับไม่ได้
- **v17.0.1.0.0** - เวอร์ชั่นเริ่มต้น

## ผู้พัฒนา (Developer)
- Module: buz_inventory_delivery_report
- Odoo Version: 17.0
- License: LGPL-3

## การสนับสนุน (Support)
หากพบปัญหาหรือต้องการความช่วยเหลือ:
1. ตรวจสอบ log file ของ Odoo
2. ตรวจสอบ user permissions (ต้องเป็น Stock Manager)
3. ติดต่อผู้ดูแลระบบ
