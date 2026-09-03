# Customer Refund PV — Phase 1

## สรุป

สร้างส่วนแรกของ Customer Refund PV จากหน้า Customer Credit Note:

```text
Posted Customer Credit Note
→ กด Create Refund PV
→ เปิดฟอร์ม Customer Refund PV แบบ Draft
→ กรอกและบันทึกข้อมูล
```

Customer Refund PV ต้องเป็นเอกสารคนละโมเดลกับ Vendor PV แต่ใช้โครงสร้างและ layout ของ Vendor PV เป็นต้นแบบโดยตรง เพื่อไม่กระทบ Vendor PV เดิม

## การเปลี่ยนแปลงหลัก

- เพิ่มปุ่ม `Create Refund PV` บนฟอร์ม `account.move`
- ปุ่มแสดงเฉพาะเอกสารที่:
  - `move_type = 'out_refund'`
  - `state = 'posted'`
- เมื่อกดปุ่ม:
  - สร้าง Customer Refund PV ใหม่สถานะ `Draft`
  - เติม Customer, Company, Currency และ Credit Note ต้นทาง
  - เปิดฟอร์ม Refund PV ที่สร้างทันที
- Credit Note ต้นทางใน Refund PV ต้องอ่านอย่างเดียวและเปลี่ยนไม่ได้
- เพิ่ม smart button บน Credit Note สำหรับแสดงจำนวนและเปิด Refund PV ที่เชื่อมโยง
- รองรับการเปิดรายการ Refund PV ที่เชื่อมโยงได้หลายรายการ

## โมเดลและฟอร์ม

สร้างโมเดลแยก เช่น:

- `buz.customer.refund.pv`
- `buz.customer.refund.pv.line`

ฟอร์มใช้ layout และลำดับส่วนข้อมูลเหมือน Vendor PV ได้แก่:

- Header และ Status bar
- เลขที่ วันที่ Customer และ Company
- Payment Type
- Journal
- Payment Method
- ข้อมูล Check ตามประเภทการจ่าย
- รายละเอียดรายการ
- ยอดรวม
- Note
- Attachment
- Chatter

สำหรับ Phase 1 ให้ใช้ field และโครงสร้างที่แสดงใน Vendor PV เป็น baseline ทั้งหมด เพื่อให้หน้าตาเหมือนกันก่อน ส่วน behavior ทางบัญชีจะยังไม่ทำงาน

## ไฟล์ที่เกี่ยวข้อง

- `buz_accounting_addon/models/`
  - เพิ่มโมเดล Customer Refund PV
  - ขยาย `account.move` เพื่อสร้างและเปิด Refund PV
- `buz_accounting_addon/views/`
  - เพิ่มฟอร์ม Refund PV
  - เพิ่มปุ่มและ smart button บน Credit Note
- `buz_accounting_addon/security/ir.model.access.csv`
  - เพิ่มสิทธิ์โมเดลใหม่
- `buz_accounting_addon/__manifest__.py`
  - โหลดโมเดล, security และ views ตามลำดับ

ก่อนแก้ XML ต้องตรวจสอบโครงสร้างจริงของ `account_payment_voucher_views.xml`, `account_move_views.xml` และ manifest เพื่อเลือก XPath และลำดับโหลดให้ถูกต้องตาม Odoo 17

## สิ่งที่ไม่รวมใน Phase 1

- ไม่สร้าง `account.payment`
- ไม่ Register Payment
- ไม่ Confirm หรือ Post Refund PV
- ไม่ Reconcile Credit Note
- ไม่ตัดหรือเปลี่ยนยอดคงเหลือของ Credit Note
- ไม่สร้างหรือแก้ไขรายงาน Payment Voucher
- ไม่แก้ logic ของ Vendor PV
- ไม่ deploy, upgrade module หรือ restart server

## Test และเกณฑ์ยอมรับ

1. Posted Customer Credit Note แสดงปุ่ม `Create Refund PV`
2. Draft Invoice หรือเอกสารประเภทอื่นไม่แสดงปุ่มนี้
3. กดปุ่มแล้วสร้าง Refund PV ใหม่สถานะ Draft
4. ฟอร์มเปิดขึ้นและเติมข้อมูล Customer, Company, Currency และ Credit Note ถูกต้อง
5. Credit Note ต้นทางเปลี่ยนไม่ได้
6. ฟอร์มมี layout และลำดับส่วนข้อมูลเหมือน Vendor PV
7. บันทึก Draft ได้โดยไม่สร้าง Payment
8. Credit Note ไม่ถูกเปลี่ยนยอดหรือสถานะ
9. Smart button แสดงจำนวนและเปิด Refund PV ที่เชื่อมโยงได้
10. Vendor PV เดิมยังทำงานเหมือนเดิม
11. ตรวจ Python import, XML syntax, XML ID, XPath และ access CSV ได้ครบ
12. ทดสอบบน isolated test environment ก่อนใช้งานจริง

## สมมติฐาน

- ใช้ Posted Customer Credit Note เป็นเอกสารต้นทางเท่านั้น
- สร้าง Refund PV จากหน้า Credit Note โดยตรง
- Customer Refund PV เป็นโมเดลแยกจาก Vendor PV
- Phase 1 เน้นการสร้างเอกสารและหน้าจอเท่านั้น
- การ Confirm, Register Payment และการพิมพ์รายงานจะทำใน Phase ถัดไป
