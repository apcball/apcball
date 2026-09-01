## อัปเดตงาน Local รอบล่าสุด (2026-09-01)

สถานะรอบนี้: ปรับปรุงและทดสอบบน Local/isolated Docker แล้ว ยังไม่ได้ Deploy, Upgrade หรือ Restart MOG_DEV ตามขอบเขตของแผนนี้ โดย MOG_DEV ยังคงเป็นเวอร์ชันที่ Deploy ในรอบก่อนหน้า จนกว่าจะมีคำสั่ง Deploy ใหม่

สิ่งที่ปรับปรุงใน CV:
- Refund Amount ที่ Header เป็นยอดจ่ายจริง และ Payment Line เป็น Readonly พร้อม Sync จาก Header
- Other Income คำนวณจาก CN Residual - Refund Amount และใช้เป็น Odoo Payment Register Write-off เพื่อ Reconcile กับ CN
- Partial Refund ต้องเลือก Other Income Account และระบุ Refund Reason; Full Refund ไม่สร้าง Write-off
- Customer Account ดึงจาก Receivable Line ของ CN และ Readonly
- Payment Journal และ Outbound Payment Method ต้องครบ อยู่บริษัทเดียวกัน และ Method ต้องอยู่ใน Journal ที่เลือก
- ซ่อน Bank Fee จากฟอร์ม CV ระยะแรก เพราะยังไม่มี Logic ลงบัญชี
- เพิ่ม guard ป้องกัน Refund Amount เป็นศูนย์/ติดลบ/เกิน CN Residual, Payment ซ้ำ และ Journal Entry Number ซ้ำ
- CV เท่านั้นที่ถูกแก้ไข ไม่เปลี่ยน Model/View/Logic ของ Vendor PV และไม่ลบข้อมูลหรือโครงสร้าง Revision เดิม

ผลตรวจสอบ:
- Python compile ผ่าน
- XML parse ผ่าน
- Isolated Docker Odoo test: 0 failed, 0 error(s) of 10 tests
- การทดสอบ Register Refund จริงกับรายการบัญชีในฐานข้อมูลใช้งานจริงยังต้องทำเป็น UAT หลัง Deploy รอบถัดไป
# Customer Refund Voucher (CV) — Handoff และข้อตกลงล่าสุด

เอกสารนี้สรุปขอบเขตและเงื่อนไขที่ตกลงกันล่าสุดสำหรับ Customer Refund Voucher (CV) หากขัดกับข้อความเก่าในเอกสารหรือโค้ดเดิม ให้ถือข้อตกลงล่าสุดด้านล่างเป็นหลัก

**สถานะล่าสุด (2026-09-01):** พัฒนาและ Deploy บน MOG_DEV แล้ว รอ User ทำ UAT เชิงธุรกิจ

## Latest update (2026-09-01)

สถานะปัจจุบัน: CV partial refund และ Other Income ถูกพัฒนา ทดสอบบน Local isolated Docker และ Deploy ไปยัง MOG_DEV แล้ว

สิ่งที่ทำแล้ว:

- Refund Amount กรอกได้มากกว่า 0 และไม่เกิน CN Residual
- Other Income = CN Residual - Refund Amount เป็น readonly และมี Other Income Account ให้เลือกต่อ CV
- Payment Line เป็น readonly และใช้ยอดเดียวกับ Refund Amount
- Register Refund ใช้ Odoo account.payment.register สร้าง Customer Outbound Payment และ standard write-off/reconcile
- จ่ายเต็ม CN ไม่สร้าง Write-off; จ่ายบางส่วนใช้ Other Income Account และตรวจ CN Residual ต้องเป็นศูนย์ก่อน CV เป็น Registered
- เพิ่ม regression tests: full refund, partial refund calculation, zero amount rejection และ over-residual rejection
- Local isolated test: 0 failed, 0 error(s) of 10 tests
- MOG_DEV upgrade: exit code 0; Module loaded, Modules loaded, Registry loaded, Stopping gracefully
- MOG_DEV restart สำเร็จ; HTTP health check = 302

ข้อจำกัดที่ยังคงเดิม: ยังไม่รวมหลาย CN ต่อ CV, WHT, Bank Fee, approval หลายระดับ, การส่งเอกสารให้ลูกค้า และการลบ/ย้ายข้อมูล Revision เก่า

หมายเหตุ: ข้อความเดิมที่ระบุว่ายังไม่รองรับ Partial Refund หรือยังไม่ Deploy ให้ถือว่าถูกแทนที่ด้วย Latest update นี้

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
- ไม่รวม WHT, Bank Fee หรือหลาย CN ต่อ CV
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
- การ Deploy/Upgrade/Restart MOG_DEV ดำเนินการแล้ว; Production ยังอยู่นอกขอบเขต

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

ยังไม่รวมหลาย CN ต่อหนึ่ง CV, หลาย Payment Line ที่ผู้ใช้กรอกเอง, WHT/Bank Fee, approval หลายระดับ, การส่งเอกสารให้ลูกค้า และการลบ/ย้ายข้อมูล Revision เก่า จนกว่าจะมีการตกลงใหม่
