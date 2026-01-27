# การแก้ไขปัญหา buz_tax_report

## ข้อผิดพลาด: External ID not found in the system: buz_tax_report.tax_report_xlsx

### สาเหตุ
ข้อผิดพลาดนี้เกิดขึ้นเมื่อ Odoo ไม่สามารถหา External ID ของรายงานได้ ซึ่งอาจเกิดจากการที่ module ยังไม่ได้รับการอัปเดตหลังจากการแก้ไขไฟล์

### วิธีแก้ไข

#### วิธีที่ 1: อัปเดต Module (แนะนำ)
1. ไปที่ **Apps > Apps**
2. ค้นหา "Tax Report Excel" หรือ "buz_tax_report"
3. คลิกปุ่ม **Upgrade** หรือ **Update**
4. รอให้การอัปเดตเสร็จสิ้น
5. ลองใช้งานรายงานอีกครั้ง

#### วิธีที่ 2: ติดตั้งใหม่ (ถ้าวิธีแรกไม่ได้ผล)
1. ไปที่ **Apps > Apps**
2. ค้นหา "buz_tax_report"
3. คลิก **Uninstall** (ถ้าติดตั้งอยู่แล้ว)
4. **Update Apps List**
5. ค้นหาและติดตั้ง "Tax Report Excel" ใหม่

#### วิธีที่ 3: อัปเดตผ่าน Command Line (สำหรับ Admin)
```bash
# อัปเดต module ผ่าน command line
./odoo-bin -u buz_tax_report -d your_database_name

# หรือ restart Odoo service
sudo systemctl restart odoo
```

#### วิธีที่ 4: ตรวจสอบไฟล์ XML
ตรวจสอบว่าไฟล์ `views/tax_report_actions.xml` มีเนื้อหาที่ถูกต้อง:

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <data>
        <record id="tax_report_xlsx" model="ir.actions.report">
            <field name="name">Tax Report XLSX</field>
            <field name="model">tax.report.wizard</field>
            <field name="report_type">xlsx</field>
            <field name="report_name">buz_tax_report.tax_report_xlsx</field>
            <field name="report_file">buz_tax_report.tax_report_xlsx</field>
        </record>
    </data>
</odoo>
```

### การป้องกันปัญหา

1. **อัปเดต Module เสมอ** หลังจากแก้ไขไฟล์ XML หรือ Python
2. **ตรวจสอบ Dependencies** ให้แน่ใจว่าติดตั้ง `report_xlsx` แล้ว
3. **ใช้ Developer Mode** เพื่อดูรายละเอียดข้อผิดพลาดเพิ่มเติม

### ตรวจสอบการติดตั้ง

หลังจากแก้ไขแล้ว ให้ทดสอบโดย:
1. ไปที่ **Accounting > Reports > Tax Report (Excel)**
2. เลือกช่วงวันที่
3. กดปุ่ม **Generate Excel Report**
4. ควรได้ไฟล์ Excel ที่มีคอลัมน์ Tax ID/VAT

### ติดต่อสำหรับความช่วยเหลือ

หากยังมีปัญหา กรุณาตรวจสอบ:
- Odoo log files
- Module dependencies
- File permissions
- Database connections
