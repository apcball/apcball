# คู่มือการติดตั้งและอัพเกรดโมดูล Dispatch Report Config

## การอัพเกรดโมดูล

### วิธีที่ 1: ผ่าน UI
1. เข้าสู่ระบบ Odoo ด้วยผู้ใช้ Admin
2. ไปที่ Apps
3. ค้นหา "Inventory Delivery Report"
4. คลิกปุ่ม "Upgrade"

### วิธีที่ 2: ผ่าน Command Line
```bash
# หยุดระบบ Odoo
sudo systemctl stop instance1

# อัพเกรดโมดูล
/opt/instance1/odoo17/venv/bin/python /opt/instance1/odoo17/odoo-bin \
  -c /opt/instance1/instance1.conf \
  -d your_database_name \
  -u buz_inventory_delivery_report \
  --stop-after-init

# เริ่มระบบ Odoo อีกครั้ง
sudo systemctl start instance1
```

### วิธีที่ 3: Restart Odoo Service
```bash
# Restart service (รีสตาร์ทและโหลดโมดูลใหม่)
sudo systemctl restart instance1

# ตรวจสอบสถานะ
sudo systemctl status instance1
```

## การตรวจสอบการติดตั้ง

### 1. ตรวจสอบว่าโมดูลถูกโหลด
```bash
cd /opt/instance1/odoo17/custom-addons/buz_inventory_delivery_report
ls -la models/dispatch_report_config.py
```

คาดหวังผลลัพธ์:
```
-rw-r--r-- 1 user user 17000+ /path/to/dispatch_report_config.py
```

### 2. ตรวจสอบ Syntax Error
```bash
python3 -m py_compile models/dispatch_report_config.py
echo $?  # ต้องได้ 0 (ไม่มี error)
```

### 3. ตรวจสอบใน Odoo
1. ไปที่ Settings → Technical → Models
2. ค้นหา "dispatch.report.config"
3. ตรวจสอบว่ามี fields ใหม่ครบถ้วน

## การใช้งานครั้งแรก

### ขั้นตอนที่ 1: สร้าง Configuration
```
เมนู: Inventory → Configuration → Dispatch Report Config
คลิก: Create

ตั้งค่า:
- Name: "A4 Full Coverage"
- Paper Size: A4
- Margin Top: 0
- Margin Bottom: 0
- Margin Left: 0
- Margin Right: 0
- Default Configuration: ✓ (เลือก)
```

### ขั้นตอนที่ 2: ปรับใช้ Full Page Layout
```
1. เปิด Configuration ที่สร้างไว้
2. คลิกปุ่ม "Action" → "Apply Full Page Layout"
3. Save
```

### ขั้นตอนที่ 3: ทดสอบการพิมพ์
```
1. ไปที่ Inventory → Operations → Transfers
2. เปิด Transfer ที่ต้องการ
3. คลิก Print → Dispatch Report
4. ตรวจสอบตัวอย่าง
```

## Files ที่ถูกเพิ่ม/แก้ไข

### ✅ แก้ไข
- `models/dispatch_report_config.py` (อัพเดทเป็น 431 บรรทัด)
- `report/dispatch_report.xml` (ปรับ CSS และ page settings)

### ✅ เพิ่มใหม่
- `README_FULL_A4_CONFIG.md` (เอกสารภาษาอังกฤษ)
- `README_TH_SUMMARY.md` (เอกสารภาษาไทย)
- `INSTALLATION_GUIDE.md` (ไฟล์นี้)

## Troubleshooting

### ปัญหา: โมดูลไม่แสดงใน Apps
**แก้ไข:**
```bash
# อัพเดท Apps List
เข้า Apps → คลิก "Update Apps List"
ค้นหาโมดูลใหม่
```

### ปัญหา: Field ใหม่ไม่แสดง
**แก้ไข:**
```bash
# อัพเกรดโมดูลใหม่
/opt/instance1/odoo17/venv/bin/python /opt/instance1/odoo17/odoo-bin \
  -c /opt/instance1/instance1.conf \
  -d database_name \
  -u buz_inventory_delivery_report \
  -i buz_inventory_delivery_report \
  --stop-after-init
```

### ปัญหา: พิมพ์ออกมาไม่เต็มหน้า
**แก้ไข:**
```
1. ตรวจสอบ Paper Format ใน report settings
2. ตรวจสอบว่า margins = 0 ทั้งหมด
3. เลือก Configuration ที่ถูกต้อง
4. ใช้ "Apply Full Page Layout" อีกครั้ง
```

### ปัญหา: ฟอนต์ไทยแสดงผิด
**แก้ไข:**
```bash
# ตรวจสอบว่ามีไฟล์ฟอนต์
ls -la /opt/instance1/odoo17/custom-addons/buz_inventory_delivery_report/static/fonts/

# ต้องมี:
# - Sarabun-Regular.ttf
# - Sarabun-Bold.ttf
```

## การ Backup ก่อนอัพเกรด

```bash
# Backup database
pg_dump -U odoo -d database_name > backup_$(date +%Y%m%d).sql

# Backup module folder
tar -czf buz_inventory_delivery_report_backup_$(date +%Y%m%d).tar.gz \
  /opt/instance1/odoo17/custom-addons/buz_inventory_delivery_report/
```

## ข้อมูลเพิ่มเติม

- **Module Name:** buz_inventory_delivery_report
- **Version:** 17.0.1.0.0
- **Odoo Version:** 17.0
- **License:** LGPL-3
- **Dependencies:** stock

## ติดต่อสอบถาม

หากพบปัญหาในการติดตั้งหรือใช้งาน กรุณาติดต่อทีมพัฒนา

---
**Last Updated:** December 2025
