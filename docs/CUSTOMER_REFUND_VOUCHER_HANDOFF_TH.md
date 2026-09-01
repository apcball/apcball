# Customer Refund Voucher (CV) — Handoff และข้อตกลงล่าสุด

เอกสารนี้สรุปขอบเขตและเงื่อนไขที่ตกลงกันล่าสุดสำหรับ Customer Refund Voucher (CV) หากขัดกับข้อความเก่าในเอกสารหรือโค้ดเดิม ให้ถือข้อตกลงล่าสุดด้านล่างเป็นหลัก

**สถานะ:** ตกลงขอบเขตสำหรับพัฒนาใช้งานขั้นต่ำ (MVP) แล้ว ยังไม่อนุญาตให้ติดตั้งหรืออัปเกรดบนระบบจริง

## 1. เป้าหมายและขอบเขต MVP

- User นำ **Customer Credit Note (CN)** ที่ผ่านการ Post แล้วมาออกเลข **CV** เพื่อจ่ายเงินคืนให้ลูกค้า
- CV เป็นเอกสารภายใน ใช้ประกอบการขออนุมัติและบันทึกการจ่ายเงิน ไม่ใช่เอกสารส่งให้ลูกค้า
- ใช้กลไกมาตรฐานของ Odoo (`account.payment.register`) และ Reconcile ไม่สร้าง Journal Entry เอง
- CV หนึ่งใบอ้างอิง CN หนึ่งใบ และคืนเงินเต็มยอดคงเหลือของ CN เท่านั้น
- ต้องไม่กระทบข้อมูลหรือ workflow เดิมของ Vendor Payment Voucher (PV) และการจ่ายเงินเดิม

## 2. Workflow ที่ตกลง

```text
Posted Customer CN (out_refund, residual > 0)
    → Create CV → Draft → Confirm → Register Refund
    → Post Customer Outbound Payment → Reconcile → Registered
```

- สร้าง CV ได้จาก CN ที่เป็น `out_refund`, Posted และมียอดคงเหลือมากกว่า 0 เท่านั้น
- CN เดียวกันมี CV ที่ยังใช้งานอยู่ได้เพียงหนึ่งใบ
- หลัง Confirm แล้วจะแก้ข้อมูลสำคัญไม่ได้
- Register Refund ต้องสร้าง Customer Outbound Payment และเชื่อมกับ CN เดิม
- Payment ถูก Post และ Reconcile สำเร็จแล้ว CV เป็น `Registered`
- หาก Payment ถูกยกเลิก ให้เป็น `Payment Cancelled` และไม่ถือว่าสำเร็จ

## 3. เลขเอกสาร

- รูปแบบ `CV/<ปี>/<เลข 4 หลัก>` เช่น `CV/2026/0001`
- Sequence แยกตามบริษัทและรีเซ็ตตามปี
- ออกเลขเมื่อสร้าง CV ในสถานะ Draft
- เลขที่ยกเลิกแล้วไม่ใช้ซ้ำ

## 4. รูปแบบหน้าจอ

ฟอร์ม CV ใช้ layout และลำดับการกรอกใกล้เคียง Vendor PV เพื่อลดความสับสน แต่เป็นฟอร์มและโมเดลแยกกัน

- Header: CV Number, Status, Confirm, Register Refund, Cancel, Print
- ข้อมูลลูกค้าและ CN: Customer, CN Number/Date/Total/Residual (อ่านอย่างเดียว)
- รายละเอียดคืนเงิน: Refund Date, Refund Method, Journal, Payment Method
- รายละเอียดเช็คเมื่อเลือก Cheque: เลขที่เช็ค วันที่เช็ค และ Pay To
- Notes: Refund Reason และ Note
- Smart buttons สำหรับเปิด CN และ Payment

### Payment Lines

- มีแท็บ **Payment Lines** ให้รูปแบบสอดคล้องกับ PV และรองรับการขยายในอนาคต
- MVP สร้างบรรทัดอัตโนมัติจาก CN หนึ่งบรรทัดต่อหนึ่ง CV
- บรรทัดเป็น Readonly ห้าม Add, Delete หรือแก้ไขยอดเอง
- ไม่เพิ่ม WHT, Bank Fee, Other Income หรือหลายบิลแบบ PV ใน MVP
- ใช้โมเดลบรรทัดของ CV แยกจาก `account.payment.voucher.line`

### Notes

- คงแท็บ **Notes** สำหรับเหตุผลและหมายเหตุภายใน
- ไม่ต้องมี `Internal Notes > Revisions` ใน workflow ใหม่

## 5. โครงสร้างข้อมูลและความปลอดภัย

- โมเดล CV และ CV Payment Line แยกใน `buz_accounting_addon`
- ความสัมพันธ์ไป CN ป้องกันการลบ CN ที่ถูกใช้งาน
- Payment มี backlink ไป CV แบบ nullable และมี index
- สิทธิ์แบ่งตามกลุ่มบัญชี: ผู้ใช้บัญชีจัดการ Draft และผู้จัดการบัญชีทำรายการที่ต้องอนุมัติ/ยกเลิก
- ตรวจสอบบริษัทเดียวกัน วันที่ ยอดคงเหลือ และ CV ซ้ำก่อนบันทึก/ยืนยัน

## 6. การยุติการใช้งาน Revision

ข้อตกลงล่าสุดคือ **ตัดการใช้งาน Revision ออกจาก CV ทั้งหมด** เพราะไม่จำเป็นต่อ MVP และ PV ไม่มีรูปแบบนี้

- ลบการอ้างอิง Revision จาก Python model, field, compute, smart button, view, report, security/ACL และ workflow
- ไม่สร้าง Snapshot และไม่บังคับ Print Revision ก่อน Confirm
- รายงาน CV พิมพ์จากค่าปัจจุบันของ CV โดยตรง
- หากฐานข้อมูลมีตารางหรือข้อมูล Revision เดิม ให้หยุดใช้งานและหยุดการอ้างอิงเท่านั้น
- ห้าม `DROP TABLE`, ลบข้อมูลเดิม หรือ migration ที่เปลี่ยนแปลงข้อมูล Revision อัตโนมัติ

## 7. ขอบเขตที่ต้องไม่เปลี่ยนแปลง

- ไม่แก้หรือ refactor logic ของ Vendor PV, Receipt Voucher หรือ Payment เดิมโดยไม่จำเป็น
- ไม่ backfill, recompute หรือลบธุรกรรมเดิม
- เปลี่ยน schema ได้เฉพาะส่วนเพิ่มเติมที่ CV ต้องใช้ และต้องรองรับฐานข้อมูลเดิม
- ห้ามติดตั้ง อัปเกรด รีสตาร์ต หรือ deploy ไป MOG_DEV/Production จนกว่าจะมีคำสั่งแยกต่างหาก

## 8. Docker gate ก่อนส่ง UAT

ตรวจสอบบน Docker เครื่องนี้ก่อน โดยใช้ compose สำหรับ CV แยกจากโมดูลอื่น:

- Fresh install บนฐานข้อมูลทดสอบใหม่ และ Upgrade ซ้ำได้โดยไม่เกิด traceback
- Restart แล้วโมดูลโหลดได้และหน้า Odoo ตอบสนอง
- ตรวจ XML syntax, XML ID, XPath, manifest load order, ACL และ `git diff --check`
- ตรวจว่าไม่มี reference ของ Revision ในโค้ด/วิว/รายงาน/ACL ที่ใช้งานจริง
- ตรวจว่า Vendor PV ไม่เปลี่ยนโดยไม่เกี่ยวข้อง

Docker gate นี้ยังไม่ใช่การรับรอง workflow หรือ PDF เชิงธุรกิจ และไม่ทดสอบฐานข้อมูลจริง

## 9. UAT โดย User

หลังพัฒนาและผ่าน Docker gate แล้ว ให้ User ทดสอบเอง โดยครอบคลุมอย่างน้อย:

1. สร้าง CV จาก CN ที่เข้าเงื่อนไขและตรวจเลข CV
2. ตรวจ layout และ Payment Lines ว่าข้อมูลมาจาก CN และแก้เองไม่ได้
3. Confirm แล้วข้อมูลสำคัญถูกล็อก
4. Register Refund สร้าง Customer Outbound Payment ได้
5. Post/Reconcile สำเร็จ ยอด CN ถูกต้อง และ CV เป็น Registered
6. ทดสอบ Payment Cancelled และ validation กรณีข้อมูลไม่ครบ
7. ยืนยันว่า Vendor PV และข้อมูลเดิมยังทำงานเหมือนเดิม

ผล UAT และข้อแก้ไขเพิ่มเติมให้บันทึกใน handoff นี้ก่อนขยายขอบเขต

## 10. ขอบเขตหลัง MVP

ยังไม่รวม Partial Refund, หลาย CN ต่อหนึ่ง CV, หลาย Payment Line ที่ผู้ใช้กรอกเอง, WHT/Bank Fee, approval หลายระดับ, การส่งเอกสารให้ลูกค้า และการลบ/ย้ายข้อมูล Revision เก่า จนกว่าจะมีการตกลงใหม่
