# Customer Refund PV — Workflow Plan

เอกสารนี้อธิบาย workflow ปัจจุบันของ Customer Refund PV ใน `buz_accounting_addon`
และใช้เป็นบันทึกสำหรับการทดสอบและส่งมอบระบบ

## สถานะปัจจุบัน

Customer Refund PV ใช้ flow มาตรฐานของ Odoo ดังนี้:

```text
Posted Credit Note
    → Create Refund PV
    → Confirm PV
    → Register Refund Payment
    → Payment Posted และ Reconcile
```

- การ Confirm เปลี่ยนเฉพาะสถานะ PV เป็น Posted; ยังไม่สร้าง Payment หรือ Journal Entry
- Payment และ Journal Entry จะเกิดเมื่อผู้ใช้กด Register Refund Payment เท่านั้น
- Payment ใช้ `Refund Amount` ที่อนุมัติบน PV และใช้เลขจาก Odoo Standard Sequence
- Credit Note ต้องเป็น Customer Credit Note (`out_refund`) และอยู่ในสถานะ Posted
- Refund Amount ต้องมากกว่า 0 และไม่เกินยอดคงเหลือของ Credit Note
- Invoice ต้นทางทุกใบต้องเป็น Customer Invoice ที่ Posted, Paid และ residual เป็นศูนย์
- เมื่อมี Payment ที่ Active แล้ว จะ Register ซ้ำไม่ได้

## Other Income และ Write-Off

ระบบใช้ Write-Off มาตรฐานของ Odoo เพียงชุดเดียว โดยส่งค่าเข้า Payment Register:

- `payment_difference_handling = reconcile`
- `writeoff_account_id = Other Income Account` ที่ผู้ใช้เลือกบน PV
- `writeoff_label = Other Income - <PV Number>`

โค้ด Customer Refund PV จะไม่เพิ่ม Journal Line ของ Other Income เองอีกต่อไป

ตัวอย่าง Credit Note 1,000 บาท, Refund Amount 860 บาท และส่วนต่าง 140 บาท:

```text
Dr ลูกหนี้                         1,000
    Cr ธนาคาร                       860
    Cr บัญชี Other Income            140
```

ผลที่ต้องได้คือ Journal Entry มี Other Income เพียง 1 บรรทัด และต้องไม่มีทั้ง
`Write-Off 140` กับ `Other Income - PV 140` ซ้ำกัน

กรณีคืนเต็มจำนวน จะไม่มี Payment Difference และไม่มี Write-Off

### Other Income Account

- ฟิลด์ยังคงแสดงบนหน้า PV และรายงาน
- บัญชีต้อง Active และอยู่บริษัทเดียวกับ PV
- ไม่จำกัดเฉพาะ account type Income เพื่อให้ใช้ตามผังบัญชีของบริษัทได้
- หากมีส่วนต่างแต่ไม่ได้เลือกบัญชี ระบบจะบล็อก Confirm/Register

## การควบคุมความปลอดภัยของ PV

- Reset to Draft และ Cancel ใช้ได้เฉพาะ Accounting Manager ผ่าน Reason Wizard
- เหตุผลและผู้ดำเนินการถูกบันทึกใน Chatter
- ห้ามเปลี่ยน State ผ่าน `write()` โดยตรง
- PV ที่ Posted หรือ Cancelled และรายการของ PV จะถูกล็อกไม่ให้แก้ไขหรือลบ
- ระบบไม่ลบ ยกเลิก หรือแก้ Payment/Journal Entry อัตโนมัติ
- ก่อน Reset หรือ Cancel ต้องจัดการ Payment และ reconciliation ที่เกี่ยวข้องผ่าน workflow ของ Payment ก่อน

## Source SO/Invoice

- ระบบค้น Invoice ต้นทางจากความสัมพันธ์ `Credit Note line.sale_line_ids → SO line`
- ค้น Invoice line แบบ batch และนำผลชุดเดียวกันไปใช้แสดงรายการ จำนวน และสถานะ
- ไม่ใช้ `invoice_origin` หรือการเดาจากชื่อ/ยอดเงินเป็น fallback
- หากหา SO/Invoice ไม่ครบ หรือ Invoice ยังไม่ Paid จะบล็อกทั้ง Confirm และ Register

## สิ่งที่ไม่อยู่ในขอบเขต

- ไม่แก้ Vendor PV, Payment Voucher, Receipt Voucher หรือ Batch Payment flow อื่น
- ไม่สร้าง Payment ตอน Confirm
- WHT ยังไม่รวมใน Customer Refund PV flow นี้
- Bank Fee แสดงใน Draft ได้ แต่ยังบล็อกการ Post หากมียอด เพราะยังไม่มี Journal Entry รองรับ
- ไม่ทำ mass update/backfill ข้อมูล Credit Note เดิม
- ไม่ deploy ไป Production จาก workflow นี้

## ผลการทดสอบล่าสุด

ทดสอบใน Docker isolated database `MOG_TEST`:

- AST และ XML syntax: ผ่าน
- `git diff --check`: ผ่าน
- Odoo module tests: `0 failed, 0 error(s) of 2 tests`
- ทดสอบการส่งค่า Standard Write-Off context และยืนยันว่า `account.payment` ไม่มี custom move-line injection ของ Refund PV

การทดสอบ Browser/PDF และ accounting UAT แบบ end-to-end ยังต้องดำเนินการโดยผู้ใช้งาน
เช่น ตรวจ Payment, Journal Entry, จำนวน Other Income line และยอด Credit Note หลัง Reconcile

## ประวัติการ Deploy DEV

### รอบแก้ Other Income ซ้ำ — 2026-09-06 เวลาไทย

- Target: DEV database `MOG_DEV`
- Module: `buz_accounting_addon` เท่านั้น
- Upload: สำเร็จ (`scp`); ไม่ upload เอกสารนี้และไม่แตะโมดูลอื่น
- Upgrade: สำเร็จด้วย `-u buz_accounting_addon --stop-after-init --no-http`
  - Odoo รายงาน `Module buz_accounting_addon loaded in 4.90s`
  - Odoo รายงาน `Modules loaded` และ `Registry loaded in 29.697s`
- Restart: สำเร็จด้วย `docker restart odoo`
- Health check: container รายงาน `odoo Up` และ HTTP `/web/database/selector` ได้ `200`
- Module state: `buz_accounting_addon | installed | 17.0.2.1.0`
- หมายเหตุ: พบ warning เดิมของโมดูลอื่น เช่น `office_supply_requisition` และ Odoo field warnings
  แต่ไม่ทำให้การ upgrade ของ target module ล้มเหลว

### ขอบเขตการส่งมอบ

การ deploy รอบนี้ไม่รวมเอกสาร, โมดูลอื่น, DEV database migration, Production deployment
หรือการปรับข้อมูลย้อนหลัง
