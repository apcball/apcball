# การติดตั้งและใช้งาน buz_tax_report พร้อม Tax ID

## สรุปการพัฒนา

Module `buz_tax_report` ได้รับการพัฒนาและปรับปรุงเพื่อเพิ่มฟีเจอร์การแสดง Tax ID (เลขประจำตัวผู้เสียภาษี) ในรายงานภาษี

## การปรับปรุงที่ทำ

### 1. เพิ่มคอลัมน์ Tax ID/VAT ในรายงานแบบละเอียด
- เพิ่มคอลัมน์ "Tax ID/VAT" ในรายงาน Excel
- แสดงเลขประจำตัวผู้เสียภาษี (VAT) ของ Partner
- ปรับขนาดคอลัมน์ให้เหมาะสม

### 2. ปรับปรุงการจัดรูปแบบ Excel
- เพิ่มคอลัมน์ใหม่โดยไม่กระทบต่อรูปแบบเดิม
- ปรับการ merge cells ให้ครอบคลุมคอลัมน์ใหม่
- รักษาการจัดรูปแบบที่มีอยู่

### 3. อัพเดตเอกสารประกอบ
- README.md มีข้อมูลการใช้งานที่ครบถ้วน
- CHANGELOG.md บันทึกการเปลี่ยนแปลง
- เพิ่มคำอธิบายฟีเจอร์ใหม่

## โครงสร้างไฟล์ที่สำคัญ

```
buz_tax_report/
├── __manifest__.py              # ข้อมูล module และ dependencies
├── __init__.py                  # นำเข้า models, wizard, report
├── models/
│   ├── __init__.py
│   └── tax_report_config.py     # Model สำหรับจัดการการตั้งค่า
├── wizard/
│   ├── __init__.py
│   └── tax_report_wizard.py     # Wizard สำหรับการสร้างรายงาน
├── report/
│   ├── __init__.py
│   └── tax_report_xlsx.py       # *** ไฟล์หลักที่ถูกปรับปรุง ***
├── views/
│   ├── tax_report_wizard_view.xml
│   ├── tax_report_config_view.xml
│   ├── tax_report_actions.xml
│   └── menu.xml
├── security/
│   └── ir.model.access.csv      # สิทธิ์การใช้งาน
└── README.md                    # เอกสารการใช้งาน
```

## การใช้งาน

1. **ติดตั้ง Module**
   - อัปเดต Apps List
   - ค้นหา "Tax Report Excel"
   - กดติดตั้ง

2. **สร้างรายงาน**
   - ไปที่ Accounting > Reports > Tax Report (Excel)
   - เลือกช่วงวันที่และการตั้งค่า
   - เลือก "Display Details" เพื่อดู Tax ID
   - กด "Generate Excel Report"

3. **รายงานที่ได้**
   - คอลัมน์ Tax ID/VAT จะแสดงเลขประจำตัวผู้เสียภาษีของ Partner
   - ข้อมูลครบถ้วนพร้อมการจัดรูปแบบที่เป็นมืออาชีพ

## ฟีเจอร์เด่น

- ✅ แสดง Tax ID/VAT ในรายงานภาษี
- ✅ รองรับทั้งภาษีขายและภาษีซื้อ
- ✅ กรองข้อมูลตามช่วงเวลา
- ✅ การจัดรูปแบบ Excel แบบมืออาชีพ
- ✅ รองรับหลายบริษัท (Multi-company)
- ✅ เมนูการตั้งค่าสำหรับจัดการรายงาน

## การทดสอบ

Module ผ่านการตรวจสอบ:
- ✅ Python syntax validation
- ✅ File structure validation  
- ✅ Dependencies check
- ✅ XML structure validation
