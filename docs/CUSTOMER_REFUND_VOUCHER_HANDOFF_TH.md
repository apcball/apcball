# ข้อตกลงการพัฒนา Customer Refund Voucher (CV) บน Odoo 17

เอกสารฉบับนี้เป็น handoff ใหม่สำหรับการพัฒนา CV และแทนที่แนวทางเดิม โดยไม่ลบหรือแก้ไขธุรกรรมเดิมในฐานข้อมูล

## ขอบเขต

CV เป็นเอกสารควบคุมการขอจ่ายคืนจาก Posted Customer Credit Note (account.move, move_type=out_refund, state=posted) เท่านั้น CV ไม่สร้าง Journal Entry เอง

อยู่ในขอบเขต:
- สร้าง CV จาก Customer Credit Note ที่ Posted และมี Residual
- เลข CV แยกจากเลข Payment/Journal Entry และเสนอจาก Odoo Sequence
- แก้เลข CV และข้อมูลการจ่ายได้เฉพาะ Draft
- เลือก Payment Journal เฉพาะ Bank/Cash
- ระบุ Actual Refund Amount
- รองรับ partial refund ด้วย standard payment register write-off
- ผูก CV กับหนึ่ง Credit Note และหนึ่ง Payment
- พิมพ์ CV เพื่อขออนุมัติภายนอก

อยู่นอกขอบเขต:
- Vendor PV, Receipt Voucher และ Payment workflow เดิม
- WHT, Bank Fee, Approval status ใน Odoo และเอกสารส่งลูกค้า
- การลบหรือแก้ไขธุรกรรมเก่า
- การสร้างหลาย Payment หรือผูกหลาย CN ต่อ CV

## Workflow

1. เปิด Customer Credit Note
2. กด Create CV
3. ระบบสร้าง CV Draft พร้อมเลขจาก Sequence
4. บัญชีแก้เลข CV ได้ใน Draft และเลือก Payment Journal
5. กรอก Actual Refund Amount
6. หากจ่ายต่ำกว่า CN Residual ต้องเลือก Adjustment/Write-off Account ประเภท Income/Expense และกรอก Reason
7. กด Confirm
8. พิมพ์ CV เพื่อขออนุมัติภายนอก
9. กด Register Payment
10. ระบบเปิด standard account.payment.register โดยส่ง CN, Journal, Amount และ write-off เข้า wizard
11. Odoo สร้าง Customer Outbound Payment, Post และ Reconcile กับ CN
12. เมื่อสำเร็จ CV จะเป็น Registered และเก็บ Payment ที่สร้างไว้

## หลักการบัญชีและ validation

- CV ไม่สร้าง account.move และไม่เรียก custom Journal Entry logic
- Standard Odoo payment register เป็นผู้สร้าง Payment, เลข Payment/JE และ reconcile
- จ่ายเต็มจำนวนแล้ว CN Residual ต้องเป็นศูนย์
- จ่ายบางส่วน เช่น CN 950 จ่าย 900 ต้อง write-off 50 เพื่อปิด CN เป็นศูนย์
- Write-off account ต้องมี internal_group เป็น income หรือ expense
- ห้ามจ่ายเกิน Residual, ศูนย์ หรือติดลบ
- ห้าม Register Payment ซ้ำจาก CV เดิม
- Journal ต้องเป็น Bank/Cash และอยู่บริษัทเดียวกับ CV
- เลข CV ห้ามว่างและห้ามซ้ำภายในบริษัทเดียวกัน
- หากเลข Journal Entry ชน ให้ Odoo หยุดด้วยข้อผิดพลาดตาม standard sequence ห้ามแก้ชื่อ JE เดิมหรือเลื่อน Sequence ด้วย custom logic

## ไฟล์หลัก

- models/customer_refund_voucher.py: CV fields, sequence, validation, Draft/Confirm และเปิด standard wizard
- models/account_payment_register.py: เติมค่า CV ให้ standard wizard และผูก Payment หลัง standard workflow สำเร็จ
- models/account_move.py: ปุ่ม Create CV จาก Posted Customer Credit Note
- views/customer_refund_voucher_views.xml: ฟอร์มและปุ่มตามลำดับงาน
- tests/test_customer_refund_voucher.py: regression tests ของยอดเงิน เลข CV และ write-off rules
- reports/customer_refund_voucher_report.xml: แบบพิมพ์ CV

## Test plan

ต้องผ่านอย่างน้อย:
- สร้างจาก Posted Customer Credit Note ได้ และปฏิเสธ Invoice, Vendor Credit Note, Draft หรือ CN ที่ไม่มี Residual
- ได้เลข CV อัตโนมัติ แก้ได้เฉพาะ Draft และปฏิเสธเลขว่าง/ซ้ำในบริษัทเดียวกัน
- ปฏิเสธ Journal ที่ไม่ใช่ Bank/Cash
- Full refund reconcile แล้ว Residual เป็นศูนย์
- CN 950 จ่าย 900 พร้อม write-off 50 แล้ว Residual เป็นศูนย์
- ขาด write-off account หรือ reason แล้ว Register ไม่ได้
- ปฏิเสธ account ประเภท Receivable/Payable/Bank/Cash
- ปฏิเสธจำนวนศูนย์ ติดลบ เกิน Residual และ Register ซ้ำ
- Confirm แล้วแก้เลข CV, Journal, CN, Amount และข้อมูล adjustment ไม่ได้
- Payment/JE ใช้ Odoo standard sequence และไม่มี JE ซ้ำจาก CV
- Vendor PV, Receipt Voucher และ workflow เดิมยังทำงาน
- ผ่าน XML parse, Python checks และ isolated Docker test

## Deployment boundary

รอบนี้แก้เฉพาะ source และ local tests เท่านั้น การ Deploy, Upgrade และ Restart ต้องได้รับคำสั่งแยกต่างหาก
