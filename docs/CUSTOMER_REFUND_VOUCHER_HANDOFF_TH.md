## อัปเดตงาน Local รอบล่าสุด (2026-09-01)

สถานะรอบนี้: บันทึกข้อตกลง workflow ใหม่สำหรับรอบถัดไป โดย MOG_DEV ยังเป็น implementation รอบก่อนหน้า และยังไม่รวม Browser/PDF/accounting UAT ของข้อตกลงใหม่นี้

ข้อตกลงใหม่สำหรับการปรับปรุง CV รอบถัดไป:
- CV ต้องสร้างจาก Posted Customer Credit Note โดยระบบดึง Customer, CN Amount และ CN Residual มาให้อัตโนมัติ
- Refund Amount ที่ Header คือยอดจ่ายจริงที่ฝ่ายบัญชีกำหนดเอง และ Payment Line เป็น Readonly พร้อม Sync จาก Header
- หากยอดจ่ายจริงต่ำกว่า CN ให้ฝ่ายบัญชีเลือกได้ว่าจะคงยอดคงเหลือไว้ หรือปิด CN ด้วย Adjustment/Write-off
- Adjustment/Write-off ต้องเลือกบัญชีและระบุเหตุผลเองทุกครั้ง ไม่กำหนดเป็น Other Income อัตโนมัติ
- Customer Account ดึงจาก Receivable Line ของ CN และ Readonly
- Payment Journal และ Outbound Payment Method ต้องครบ อยู่บริษัทเดียวกัน และ Method ต้องอยู่ใน Journal ที่เลือก
- ซ่อน Bank Fee จากฟอร์ม CV ระยะแรก เพราะยังไม่มี Logic ลงบัญชี
- เพิ่ม guard ป้องกัน Refund Amount เป็นศูนย์/ติดลบ/เกิน CN Residual, Payment ซ้ำ และ Journal Entry Number ซ้ำ
- CV Number ให้ผู้ใช้บัญชีกรอกเองตั้งแต่สร้าง CV จาก CN ไม่บังคับ Prefix หรือลักษณะรูปแบบ และห้ามเว้นว่าง
- CV Number แก้ไขได้เฉพาะ Draft และต้องไม่ซ้ำภายในบริษัทเดียวกัน; บริษัทต่างกันใช้เลขเดียวกันได้ตามกติกา multi-company
- ยกเลิกการเรียก `ir.sequence` อัตโนมัติสำหรับ CV ใหม่ โดยคง sequence configuration เดิมไว้เพื่อไม่ลบหรือเปลี่ยนข้อมูลเดิม
- ย้ายการตรวจ Duplicate Journal Entry ไปก่อน standard `action_post()` ของ Payment โดยใช้ Payment Journal/sequence เดิม และไม่แก้ข้อมูลบัญชีเดิมอัตโนมัติ
- CV เท่านั้นที่ถูกแก้ไข ไม่เปลี่ยน Model/View/Logic ของ Vendor PV และไม่ลบข้อมูลหรือโครงสร้าง Revision เดิม

ผลตรวจสอบของ implementation รอบก่อนหน้า:
- Python AST ผ่าน
- XML parse ผ่าน
- Isolated Docker Odoo test: `0 failed, 0 error(s)` จาก 12 tests
- `git diff --check` ผ่าน
- MOG_DEV module state: `installed`, version `17.0.3.0.0`
- MOG_DEV container: `odoo Up`; HTTP health check: `303`
- ยังไม่มี Browser/PDF/accounting UAT จริง
# Customer Refund Voucher (CV) — Handoff และข้อตกลงล่าสุด

เอกสารนี้สรุปขอบเขตและเงื่อนไขที่ตกลงกันล่าสุดสำหรับ Customer Refund Voucher (CV) หากขัดกับข้อความเก่าในเอกสารหรือโค้ดเดิม ให้ถือข้อตกลงล่าสุดด้านล่างเป็นหลัก

**สถานะล่าสุด (2026-09-01):** ข้อตกลง workflow ล่าสุดด้านล่างเป็น requirement สำหรับรอบถัดไป; implementation ปัจจุบันบน MOG_DEV ยังไม่ถือว่ารองรับข้อตกลงใหม่นี้จนกว่าจะพัฒนาและทดสอบเพิ่มเติม

## Latest update (2026-09-01)

สถานะปัจจุบัน: ได้ข้อสรุป workflow ใหม่สำหรับ CV ที่สร้างจาก Customer Credit Note, ใช้ manual CV Number, กำหนด actual refund amount และรองรับการเลือก Adjustment/Write-off โดยยังรอการพัฒนาและทดสอบตามข้อตกลงนี้

สิ่งที่ต้องพัฒนาในรอบถัดไป:

- Refund Amount กรอกได้มากกว่า 0 และไม่เกิน CN Residual
- Actual Refund Amount แยกจาก CN Amount/CN Residual และฝ่ายบัญชีกำหนดเองได้ โดยห้ามเกิน CN Residual
- ส่วนต่างระหว่าง CN Residual กับ Actual Refund Amount ให้เลือกได้ว่าจะคงยอด CN ไว้ หรือใช้ Adjustment/Write-off
- กรณีใช้ Adjustment/Write-off ฝ่ายบัญชีต้องเลือกบัญชีและระบุเหตุผลเอง ระบบไม่กำหนดบัญชีเป็น Other Income อัตโนมัติ
- Payment Line เป็น readonly และใช้ยอดเดียวกับ Refund Amount
- Register Refund ใช้ Odoo account.payment.register สร้าง Customer Outbound Payment และ standard write-off/reconcile
- จ่ายเต็ม CN จะ Reconcile ได้เต็มจำนวนโดยไม่ต้องใช้ Write-off; จ่ายบางส่วนจะเหลือ CN Residual เว้นแต่ฝ่ายบัญชีเลือก Adjustment/Write-off เพื่อปิดยอด
- เพิ่ม regression tests: full refund, partial refund calculation, zero amount rejection และ over-residual rejection
- ทดสอบ isolated Docker ใหม่ให้ครอบคลุม workflow และกติกา Adjustment/Write-off
- หลังพัฒนาแล้วให้หยุดรอคำสั่งแยกต่างหากก่อน Upgrade/Restart หรือทำ UAT บน MOG_DEV

ข้อจำกัดที่ยังคงเดิม: ยังไม่รวมหลาย CN ต่อ CV, WHT, Bank Fee, approval หลายระดับ, การส่งเอกสารให้ลูกค้า และการลบ/ย้ายข้อมูล Revision เก่า

หมายเหตุ: ข้อความเดิมที่ระบุว่ายังไม่รองรับ Partial Refund หรือยังไม่ Deploy ให้ถือว่าถูกแทนที่ด้วย Latest update นี้

## 1. เป้าหมายและขอบเขต MVP

- User นำ **Customer Credit Note (CN)** ที่ผ่านการ Post แล้วมาออกเลข **CV** เพื่อจ่ายเงินคืนให้ลูกค้า
- CV เป็นเอกสารภายใน ใช้ประกอบการขออนุมัติและบันทึกการจ่ายเงิน ไม่ใช่เอกสารส่งให้ลูกค้า
- ใช้กลไกมาตรฐานของ Odoo (`account.payment.register`) และ Reconcile ไม่สร้าง Journal Entry เอง
- CV หนึ่งใบอ้างอิง CN หนึ่งใบ และรองรับการกำหนดยอดจ่ายจริงเต็มจำนวนหรือบางส่วนภายใน CN Residual
- ต้องไม่กระทบข้อมูลหรือ workflow เดิมของ Vendor Payment Voucher (PV) และการจ่ายเงินเดิม

## 2. Workflow ที่ตกลง

```text
Posted Customer CN (out_refund, residual > 0)
    → Create CV from CN → Enter CV Number and Actual Refund Amount
    → Draft → Confirm → Register Refund
    → Customer Outbound Payment → Reconcile payment and optional adjustment → Registered
```

- สร้าง CV ได้จาก CN ที่เป็น `out_refund`, Posted และมียอดคงเหลือมากกว่า 0 เท่านั้น โดยไม่ควรสร้าง CV ลอยจากเมนูทั่วไป
- CN เดียวกันมี CV ที่ยังใช้งานอยู่ได้เพียงหนึ่งใบ
- หลัง Confirm แล้วจะแก้ข้อมูลสำคัญไม่ได้
- Register Refund ต้องสร้าง Customer Outbound Payment ตาม Actual Refund Amount และเชื่อมกับ CN เดิม
- หากยอดจ่ายต่ำกว่า CN ระบบต้องรองรับทั้งการปล่อยยอดคงเหลือ หรือการเลือก Adjustment/Write-off เพื่อ Reconcile ให้ครบยอด CN
- Payment ถูก Post และ Reconcile ตามทางเลือกของบัญชีแล้ว CV เป็น `Registered`
- หาก Payment ถูกยกเลิก ให้เป็น `Payment Cancelled` และไม่ถือว่าสำเร็จ

## 3. เลขเอกสาร

- `CV Number` เป็นข้อมูลที่ผู้ใช้บัญชีกรอกเองตอนสร้าง CV จาก CN
- ระยะนี้ไม่บังคับ Prefix, ตัวย่อ, ปี, padding หรือรูปแบบใด ๆ จนกว่าฝ่ายบัญชีจะกำหนดข้อตกลงถาวร
- CV Number ต้องไม่ว่าง และต้องไม่ซ้ำภายใน `company_id` เดียวกัน
- CV Number เดียวกันในคนละบริษัทเป็นไปตามกติกา multi-company และไม่ถือว่าซ้ำกัน
- แก้ไข CV Number ได้เฉพาะสถานะ Draft; หลัง Confirm แล้วห้ามแก้
- CV เดิมต้องคงเลขเดิมทั้งหมด ไม่เปลี่ยนเลขและไม่ backfill
- ไม่เรียก `ir.sequence` อัตโนมัติสำหรับ CV ใหม่; sequence configuration เดิมคงไว้โดยไม่ลบหรือแก้ข้อมูลบัญชี

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
- Actual Refund Amount ต้องไม่เกิน CN Residual; หากต่ำกว่า CN ให้เลือกคงยอดค้าง หรือ Adjustment/Write-off
- Adjustment/Write-off ต้องเก็บบัญชีและเหตุผลที่ผู้ใช้บัญชีเลือกเอง และไม่บังคับใช้บัญชี Other Income
- ตรวจเลข Journal Entry ของ Payment ใหม่หลังสร้าง Draft Payment แต่ก่อน `action_post()` โดยตรวจตามบริษัทและ Payment Journal

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
- การ Deploy/Upgrade/Restart ทุกสภาพแวดล้อมอยู่นอกขอบเขตของแผนนี้ และต้องรอคำสั่งอย่างชัดเจนเท่านั้น; Production อยู่นอกขอบเขต

## 8. Docker gate ก่อนส่ง UAT

ตรวจสอบบน Docker เครื่องนี้ก่อน โดยใช้ isolated project/database สำหรับ `buz_accounting_addon`:

- Fresh install บนฐานข้อมูลทดสอบใหม่ และ Upgrade ซ้ำได้โดยไม่เกิด traceback
- Restart แล้วโมดูลโหลดได้และหน้า Odoo ตอบสนอง
- ตรวจ XML syntax, XML ID, XPath, manifest load order, ACL และ `git diff --check`
- ตรวจว่าไม่มี reference ของ Revision ในโค้ด/วิว/รายงาน/ACL ที่ใช้งานจริง
- ตรวจว่า Vendor PV ไม่เปลี่ยนโดยไม่เกี่ยวข้อง

Docker gate นี้ยังไม่ใช่การรับรอง workflow หรือ PDF เชิงธุรกิจ และไม่ทดสอบฐานข้อมูลจริง

## 9. UAT โดย User

หลังพัฒนาและผ่าน Docker gate แล้ว ให้ User ทดสอบเอง โดยครอบคลุมอย่างน้อย:

1. สร้าง CV จาก CN ที่เข้าเงื่อนไขโดยกรอก CV Number เอง
2. ไม่กรอก CV Number ต้องถูกปฏิเสธ และเลขซ้ำในบริษัทเดียวกันต้องถูกปฏิเสธ
3. เลขเดียวกันคนละบริษัทต้องเป็นไปตามกติกา multi-company
4. แก้ CV Number ได้เฉพาะ Draft และหลัง Confirm ต้องแก้ไม่ได้
5. ตรวจ layout และ Payment Lines ว่าข้อมูลมาจาก CN และแก้เองไม่ได้
6. Confirm แล้วข้อมูลสำคัญถูกล็อก
7. Register Refund สร้าง Customer Outbound Payment ได้ และตรวจ Duplicate Journal Entry ก่อน Payment post
8. Post/Reconcile สำเร็จ ยอด CN ถูกต้อง และ CV เป็น Registered
9. ทดสอบ Payment Cancelled และ validation กรณีข้อมูลไม่ครบ
10. ยืนยันว่า Vendor PV, Receipt Voucher และข้อมูลเดิมยังทำงานเหมือนเดิม

ผล UAT และข้อแก้ไขเพิ่มเติมให้บันทึกใน handoff นี้ก่อนขยายขอบเขต

## 10. ขอบเขตหลัง MVP

ยังไม่รวมหลาย CN ต่อหนึ่ง CV, หลาย Payment Line ที่ผู้ใช้กรอกเอง, WHT/Bank Fee, approval หลายระดับ, การส่งเอกสารให้ลูกค้า และการลบ/ย้ายข้อมูล Revision เก่า จนกว่าจะมีการตกลงใหม่
