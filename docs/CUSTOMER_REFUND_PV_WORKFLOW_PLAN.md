# Customer Refund PV — Workflow Plan

เอกสารนี้อธิบาย workflow ปัจจุบันของ Customer Refund PV ใน `buz_accounting_addon`
รวมถึงขอบเขตการ deploy และผลการตรวจสอบล่าสุด

## ภาพรวม Workflow

```text
Posted Customer Credit Note
        ↓
Create Customer Refund PV (Draft)
        ↓
เลือก Invoice ต้นทางสำหรับ Refund
        ↓
Confirm Refund PV (Posted)
        ↓
Register Refund Payment
        ↓
Post Payment และ Reconcile กับ Credit Note
```

## กติกาหลัก

- Confirm เปลี่ยนเฉพาะสถานะ Refund PV เป็น `Posted` ยังไม่สร้าง Payment หรือ Journal Entry
- Payment จะถูกสร้างเมื่อผู้ใช้กด `Register Refund Payment` เท่านั้น
- Payment ใช้ยอด `Refund Amount` ที่อนุมัติบน Refund PV
- Credit Note ต้องเป็น Customer Credit Note (`out_refund`) และอยู่สถานะ `Posted`
- Refund Amount ต้องมากกว่า 0 และไม่เกินยอดคงเหลือของ Credit Note
- เมื่อมี Payment ที่ยัง Active แล้ว จะ Register Payment ซ้ำไม่ได้

## Invoice ต้นทางสำหรับ Refund

การจับคู่ Credit Note กับ Invoice ต้นทางเป็นการตัดสินใจของฝ่ายบัญชีในสถานะ Draft
ระบบจะไม่เลือก Invoice ให้อัตโนมัติ เพราะ Sales Order เดียวกันอาจมีหลาย Invoice

รายการที่เลือกได้ต้องมีเงื่อนไขทั้งหมดต่อไปนี้:

- อยู่ภายใต้ Source SO ที่เชื่อมจาก Credit Note ผ่าน `sale_line_ids`
- เป็น Customer Invoice (`move_type = out_invoice`)
- สถานะเอกสารเป็น `Posted`
- สถานะการชำระเงินเป็น `Paid`
- ยอดคงเหลือเป็นศูนย์
- เป็นลูกค้าและบริษัทเดียวกับ Refund PV

การทำงานของฟิลด์:

- `Invoice ต้นทางสำหรับ Refund` เลือกได้หลายใบใน Draft
- ต้องเลือกอย่างน้อยหนึ่งใบก่อน Confirm
- หลัง Confirm แล้วรายการ Invoice ต้นทางจะถูกล็อก
- Source Status และ Smart Button แสดงเฉพาะ Invoice ที่เลือก
- หาก Invoice ที่เลือกเปลี่ยนสถานะภายหลัง ระบบจะแจ้งสาเหตุและบล็อก Register Payment
- Invoice อื่นใน SO เดียวกัน เช่น Invoice ที่ Reversed จะไม่มีผลต่อ Refund PV หากไม่ได้เลือก

## Other Income และ Write-Off

ระบบใช้ Standard Payment Register ของ Odoo และส่งค่า Write-Off ดังนี้:

- `payment_difference_handling = reconcile`
- `writeoff_account_id` ใช้บัญชี Other Income ที่เลือกบน Refund PV
- `writeoff_label` ใช้รูปแบบ `Other Income - <PV Number>`

ระบบไม่สร้าง Journal Line ของ Other Income เพิ่มเอง

## การควบคุมและขอบเขต

- Posted หรือ Cancelled Refund PV แก้ไขข้อมูลหลักและ Invoice ต้นทางไม่ได้
- Reset to Draft และ Cancel ใช้ได้เฉพาะ Accounting Manager ผ่าน Reason Wizard
- ไม่เปลี่ยนสถานะ Invoice หรือ Credit Note
- ไม่แก้ reconciliation เดิม
- ไม่แก้ Vendor PV, Payment Voucher เดิม, Receipt Voucher หรือ `po_so_credit_note`
- ไม่รองรับ WHT ใน flow นี้
- Bank Fee ยังบล็อกการ Post หากมียอด เพราะยังไม่มี Journal Entry รองรับ
- ไม่ทำ mass update หรือ backfill ข้อมูลเดิม
- Deploy เฉพาะ DEV (`MOG_DEV`) เท่านั้น ไม่รวม PROD

## ผลการตรวจสอบก่อน Deploy

- Python syntax: ผ่าน
- XML syntax ของ `customer_refund_pv_views.xml`: ผ่าน
- `git diff --check`: ผ่าน
- ไฟล์ที่แก้ใน source มีเฉพาะ:
  - `buz_accounting_addon/models/customer_refund_pv.py`
  - `buz_accounting_addon/views/customer_refund_pv_views.xml`
- ยังไม่ได้ทดสอบ Browser/PDF หรือ accounting UAT แบบ end-to-end

## ประวัติการ Deploy DEV

### รอบเลือก Invoice ต้นทางสำหรับ Refund — 2026-09-09 เวลาไทย

- Target: DEV database `MOG_DEV`
- Module: `buz_accounting_addon` เท่านั้น
- Upload: สำเร็จด้วย scp เฉพาะโฟลเดอร์ buz_accounting_addon
- Upgrade: สำเร็จด้วย -u buz_accounting_addon --stop-after-init --no-http บน MOG_DEV
- Restart: สำเร็จด้วย docker restart odoo
- Health check: ผ่าน — container odoo เป็น Up และ HTTP /web/database/selector ได้ 200
- Module state: buz_accounting_addon | installed | 17.0.2.1.0
- Warning ที่พบเป็น warning เดิมของ module อื่น เช่น office_supply_requisition ไม่ installable และไม่ทำให้ target upgrade ล้มเหลว
- Browser/PDF และ accounting UAT: ต้องตรวจต่อด้วยข้อมูลจริงบน DEV

เอกสารนี้อัปเดตเพื่อบันทึกแผนและผลการส่งมอบ โดยไม่รวมการเปลี่ยนข้อมูลธุรกรรมเดิม
