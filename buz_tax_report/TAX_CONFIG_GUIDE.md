# คู่มือการใช้งาน Tax Config กับ Tax Report

## การเชื่อมโยง Tax Config กับ Wizard

ตอนนี้ Tax Config ได้รับการเชื่อมโยงกับ Tax Report Wizard แล้ว ทำให้สามารถใช้งานได้หลายวิธี:

## 1. การสร้าง Tax Configuration

### ขั้นตอนการสร้าง:
1. ไปที่ **Accounting > Configuration > Tax Report Configurations**
2. คลิก **Create**
3. กรอกข้อมูล:
   - **Report Name**: ชื่อการตั้งค่า เช่น "รายงานภาษีขาย-ประจำเดือน"
   - **Report Type**: เลือกประเภท (Sales/Purchase/Both)
   - **Company**: เลือกบริษัท
   - **Taxes**: เลือกภาษีที่ต้องการ
   - **Description**: คำอธิบาย

### ตัวอย่างการตั้งค่า:

**Configuration 1: รายงานภาษีขาย**
```
Name: รายงานภาษีขาย-ประจำเดือน
Type: Sales Tax Report
Taxes: VAT 7%, VAT 0%
Description: รายงานภาษีขายสำหรับยื่น ภ.พ.30
```

**Configuration 2: รายงานภาษีซื้อ**
```
Name: รายงานภาษีซื้อ-ประจำเดือน  
Type: Purchase Tax Report
Taxes: Input VAT 7%, Withholding Tax 3%
Description: รายงานภาษีซื้อสำหรับยื่น ภ.พ.30
```

## 2. วิธีการใช้งาน

### วิธีที่ 1: สร้างรายงานจาก Tax Config
1. ไปที่ **Accounting > Configuration > Tax Report Configurations**
2. เลือก Configuration ที่ต้องการ
3. คลิกปุ่ม **Generate Report** ในหน้า form
4. ระบบจะเปิด Wizard พร้อมการตั้งค่าที่บันทึกไว้
5. เลือกวันที่และคลิก **Generate Excel Report**

### วิธีที่ 2: ใช้ Configuration ใน Wizard
1. ไปที่ **Accounting > Reports > Tax Report (Excel)**
2. ในส่วน **Quick Configuration** เลือก Configuration ที่ต้องการ
3. ระบบจะอัปเดตการตั้งค่าอัตโนมัติ
4. เลือกวันที่และคลิก **Generate Excel Report**

### วิธีที่ 3: บันทึกการตั้งค่าใหม่จาก Wizard
1. ไปที่ **Accounting > Reports > Tax Report (Excel)**
2. ตั้งค่าต่างๆ ตามต้องการ
3. คลิกปุ่ม **Save as Configuration**
4. ระบบจะเปิดหน้าสร้าง Configuration พร้อมข้อมูลที่กรอกไว้
5. แก้ไขชื่อและคำอธิบาย แล้วบันทึก

## 3. ฟีเจอร์ที่เพิ่มขึ้น

### ใน Tax Report Wizard:
- **Quick Configuration**: เลือก Configuration ที่บันทึกไว้
- **Save as Configuration**: บันทึกการตั้งค่าปัจจุบันเป็น Configuration ใหม่
- **Auto-fill**: เมื่อเลือก Configuration ระบบจะเติมข้อมูลอัตโนมัติ

### ใน Tax Config Form:
- **Generate Report**: ปุ่มสำหรับสร้างรายงานโดยตรง
- **Sequence**: กำหนดลำดับการแสดง
- **Active**: เปิด/ปิดการใช้งาน

## 4. ประโยชน์ของการเชื่อมโยง

### สำหรับผู้ใช้ทั่วไป:
- **ประหยัดเวลา**: ไม่ต้องเลือกภาษีใหม่ทุกครั้ง
- **ลดข้อผิดพลาด**: ใช้การตั้งค่าที่ทดสอบแล้ว
- **ความสะดวก**: เข้าถึงการตั้งค่าได้ 2 ทาง

### สำหรับองค์กร:
- **มาตรฐานเดียวกัน**: ทีมงานใช้การตั้งค่าเดียวกัน
- **การจัดการง่าย**: แก้ไขการตั้งค่าในที่เดียว
- **การควบคุม**: Admin สามารถสร้างการตั้งค่ามาตรฐาน

## 5. ตัวอย่างการใช้งานจริง

### สถานการณ์: บริษัทต้องยื่นรายงานภาษีประจำเดือน

**ขั้นตอนการเตรียมการ (ครั้งแรก):**
1. สร้าง Configuration "ภาษีขาย-ประจำเดือน"
2. สร้าง Configuration "ภาษีซื้อ-ประจำเดือน"
3. สร้าง Configuration "รายงานรวม-ประจำเดือน"

**การใช้งานประจำ:**
1. เลือก Configuration ที่ต้องการ
2. คลิก Generate Report
3. เลือกวันที่ของเดือนที่ต้องการ
4. ได้รายงาน Excel พร้อม Tax ID

## 6. Tips การใช้งาน

1. **ตั้งชื่อให้ชัดเจน**: ใช้ชื่อที่บอกจุดประสงค์ เช่น "VAT-Sale-Monthly"
2. **ใช้ Sequence**: กำหนดลำดับให้ Configuration ที่ใช้บ่อยขึ้นก่อน
3. **เขียน Description**: อธิบายจุดประสงค์การใช้งาน
4. **ทดสอบก่อนใช้**: สร้างรายงานทดสอบก่อนใช้งานจริง
5. **อัปเดตเป็นระยะ**: ตรวจสอบและอัปเดต Configuration เมื่อมีการเปลี่ยนแปลงภาษี
