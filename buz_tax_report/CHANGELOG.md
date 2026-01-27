# Changelog

## [17.0.1.0.0] - 2024-08-04

### Added
- เพิ่มคอลัมน์ Tax ID/VAT ในรายงานภาษีแบบละเอียด
- เพิ่ม model `tax.report.config` สำหรับจัดการการตั้งค่ารายงานภาษี
- เพิ่มเมนูการตั้งค่าการรายงานภาษี
- การแสดงเลขประจำตัวผู้เสียภาษีของ Partner ในรายงาน Excel
- **เชื่อมโยง Tax Config กับ Wizard**
- **ปุ่ม "Generate Report" ใน Tax Config form**
- **ปุ่ม "Save as Configuration" ใน Wizard**
- **Quick Configuration dropdown ใน Wizard**
- **Auto-fill ข้อมูลเมื่อเลือก Configuration**

### Changed
- ปรับปรุงการจัดรูปแบบคอลัมน์ใน Excel เพื่อรองรับข้อมูล Tax ID
- อัพเดตเอกสาร README.md ให้มีข้อมูลการใช้งาน Tax ID
- **ปรับปรุง Wizard ให้รองรับการเลือก Tax Configuration**
- **เพิ่มฟิลด์ tax_config_id ใน Tax Report Wizard**
- **ปรับปรุง UI เพื่อแสดง Quick Configuration section**

### Technical Details
- เพิ่มฟิลด์ `partner_vat` ในข้อมูลที่ส่งออกรายงาน
- ปรับขนาดคอลัมน์ Excel ให้เหมาะสมกับการแสดงข้อมูล Tax ID
- เพิ่มการจัดการ header และ footer ของรายงานให้ครอบคลุมคอลัมน์ใหม่
- **เพิ่ม @api.onchange method สำหรับ tax_config_id**
- **เพิ่ม action_save_as_config method ใน Wizard**
- **เพิ่ม action_generate_report method ใน Tax Config**
- **ปรับปรุง default_get method ใน Wizard สำหรับ default dates**

### Installation Notes
- ต้องติดตั้ง module dependencies: `account`, `report_xlsx`
- รองรับ Odoo version 17.0
- ใช้งานได้กับทั้ง Community และ Enterprise Edition

### Fixed Issues
- แก้ไขปัญหา "External ID not found" โดยการปรับปรุงไฟล์ XML
- เพิ่มไฟล์ TROUBLESHOOTING.md สำหรับแก้ไขปัญหาที่อาจเกิดขึ้น
- ปรับปรุงการกำหนด ir.actions.report ให้ถูกต้อง

### Upgrade Instructions
1. ไปที่ Apps > Apps
2. ค้นหา "buz_tax_report" หรือ "Tax Report Excel"  
3. คลิกปุ่ม "Upgrade" หรือ "Update"
4. รอให้การอัปเดตเสร็จสิ้น
