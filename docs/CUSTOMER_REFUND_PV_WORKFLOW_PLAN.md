# Customer Refund PV แบบแยกฝั่ง Customer

## Summary

สร้าง Customer Refund PV เป็นโมเดลแยก แต่ให้ workflow และหน้าตาใกล้เคียง Vendor PV เดิม เพื่อให้ User ใช้งานได้โดยไม่ต้องเรียนรู้ใหม่:

`Customer Credit Note → Create Refund PV → Draft → Confirmed → Register Payment → In Payment → Paid`

ใช้เฉพาะส่วนของ PV ที่เกี่ยวข้อง โดยไม่แชร์ WHT หรือ payable reconciliation และทำ PDF ภายหลังจาก workflow สมบูรณ์

## Workflow และหน้าจอ

- เพิ่มปุ่ม `Create Refund PV` บน Customer Credit Note ที่ Posted และมียอดคงเหลือ
- หนึ่ง Refund PV รองรับ Credit Note หนึ่งใบ
- Draft Form ใช้โครงและลำดับข้อมูลใกล้เคียง PV เดิม:
  - Header: เลขที่ วันที่ สถานะ และ Customer
  - Source Document: Credit Note หนึ่งใบและยอดคงเหลือ
  - Payment Planning: Cash/Transfer/Check, Journal, Payment Method และข้อมูลเช็คตามประเภท
  - Amount Summary: ยอด Credit Note, ยอดคืนจริง และรายได้อื่น
  - บัญชีรายได้อื่น เหตุผล หมายเหตุ ไฟล์แนบ และ Chatter
- ไม่แสดง WHT และ Bank Fee เพราะไม่อยู่ในขอบเขต Customer Refund รอบแรก
- ใช้ sequence ชุดเดียวกับ Vendor PV ออกเลขที่ตั้งแต่สร้าง Draft แก้ได้ขณะ Draft และล็อกหลัง Confirm
- `Confirm` ตรวจสอบและล็อกข้อมูล แล้วเปลี่ยนเป็น `Confirmed` โดยยังไม่ลงบัญชี
- หลังได้รับอนุมัติจากเอกสาร User กด `Register Payment` เพื่อเปิดหน้าต่างยืนยันเหมือน PV เดิม
- ในหน้าต่าง Register Payment ให้แก้ได้เฉพาะวันที่จ่าย Journal และ Payment Method โดยยอดคืนและส่วนต่างเป็น readonly
- มี Payments smart button และ Payment Status ในรูปแบบใกล้เคียง PV เดิม
- เตรียมตำแหน่งสำหรับ Print action แต่ยังไม่สร้างหรือปรับ PDF ในรอบนี้

## Accounting Behavior

- ยอดจ่ายจริงต้องมากกว่า 0 และไม่เกินยอดคงเหลือ Credit Note
- ระบบคำนวณส่วนต่างอัตโนมัติ: `ยอด Credit Note คงเหลือ - ยอดจ่ายจริง`
- ถ้ามีส่วนต่าง ต้องเลือกบัญชีประเภทรายได้ของบริษัทเดียวกันและกรอกเหตุผลทุกครั้ง
- `Register Payment` ใช้กลไกมาตรฐานของ Odoo เพื่อ:
  - สร้างและ Post Customer Outbound Payment
  - ลงส่วนต่างเข้าบัญชีที่ User เลือก
  - Reconcile Payment และส่วนต่างกับ Credit Note
  - ทำให้ยอดคงเหลือ Credit Note เป็นศูนย์
- Refund PV เปลี่ยนเป็น `In Payment` หลัง Register Payment และเป็น `Paid` เมื่อ Bank Statement ถูก reconcile ตามสถานะมาตรฐานของ Odoo
- ตรวจยอดคงเหลือซ้ำก่อน Confirm และ Register Payment พร้อมป้องกัน Credit Note ถูกใช้งานซ้ำ
- Draft และ Confirmed ยกเลิกได้โดยไม่เกิดรายการบัญชี
- In Payment หรือ Paid ห้าม Cancel ตรง ต้องย้อน Payment และ reconciliation ผ่านกระบวนการบัญชีก่อน

## Interfaces และขอบเขต

- เพิ่มโมเดล Customer Refund PV แยกจาก Vendor PV พร้อมลิงก์ไปยัง `account.move` และ `account.payment`
- เพิ่ม action และ smart button บน Credit Note สำหรับสร้างและเปิด Refund PV
- มีเมนูรายการ Refund PV สำหรับค้นหาและติดตาม แต่เริ่มสร้างจาก Credit Note
- Accounting User สามารถสร้าง Confirm และ Register Payment ได้ เพราะการอนุมัติทำบนเอกสารภายนอกระบบ
- ไฟล์เอกสารอนุมัติแนบได้แต่ไม่บังคับ
- คัดลอกเฉพาะประสบการณ์ใช้งานและโครงหน้าจอที่เกี่ยวข้อง ไม่สืบทอดหรือใช้ logic บัญชีของ Vendor PV โดยตรง
- ไม่เปลี่ยน logic, WHT, report, payable reconciliation หรือข้อมูลเดิมของ Vendor PV และไม่แก้ `account_ar_settlement`
- รอบแรกจำกัดสกุลเงินเดียวกับบริษัทและยังไม่รองรับผลต่างอัตราแลกเปลี่ยน
- การพัฒนาและตรวจสอบทั้งหมดเป็น Local-only ห้าม deploy, SSH, upload ไฟล์ขึ้น Server, upgrade module หรือ restart service/container
- ห้ามทดสอบหรือดำเนินการใด ๆ กับฐานข้อมูล DEV, PROD และฐานข้อมูลเดิมหรือฐานข้อมูลอื่น
- ห้ามแก้ไข ลบ ย้าย หรือทำ migration กับข้อมูลเดิมทุกประเภท
- การทดสอบที่ต้องใช้ฐานข้อมูลให้ใช้เฉพาะ isolated test database ที่สร้างใหม่และไม่มีข้อมูลธุรกรรมเดิม

## Test Plan

- ตรวจ flow และโครง Draft Form เทียบกับ Vendor PV
- คืนเต็ม 980: Payment 980 ไม่มีรายได้อื่น และ Credit Note ปิด
- คืน 700 จาก 980: Payment 700 รายได้อื่น 280 และ Credit Note ปิด
- ตรวจ Cash, Transfer และ Check พร้อมเงื่อนไขแสดงข้อมูลที่เกี่ยวข้อง
- ปฏิเสธยอด 0 ยอดติดลบ ยอดเกิน และส่วนต่างที่ไม่มีบัญชีหรือเหตุผล
- ตรวจ sequence ร่วมกับ Vendor PV การแก้เลขใน Draft และการล็อกหลัง Confirm
- ตรวจหน้าต่าง Register Payment ว่ายอดและส่วนต่างถูกล็อก แต่แก้วันที่ Journal และ Payment Method ได้
- ตรวจสถานะ Draft, Confirmed, In Payment และ Paid ตาม Bank Reconciliation
- ตรวจ Payment เป็น `outbound/customer`, partner และ journal ถูกต้อง
- ตรวจการป้องกัน Credit Note ซ้ำ การ Cancel และ regression ของ Vendor PV

## Progress Update Requirement

- หลังการแก้ไขหรือทดสอบทุกครั้งที่เกี่ยวข้องกับ `CUSTOMER_REFUND_PV` ต้องอัปเดตไฟล์นี้ด้วย
- ระบุรายการที่แก้ไข ไฟล์หรือส่วนของระบบที่ได้รับผลกระทบ การทดสอบที่ดำเนินการ และผลลัพธ์จริง
- ระบุปัญหาที่พบ ข้อจำกัด และงานที่ยังไม่เสร็จอย่างชัดเจน
- ห้ามเปลี่ยนสถานะงานหรือการทดสอบเป็นเสร็จสมบูรณ์ หากยังไม่มีผลตรวจสอบรองรับ

## Assumptions

- การอนุมัติทำบนเอกสารที่พิมพ์ออกจากระบบ ไม่มีปุ่ม Manager Approve ใน Odoo
- ระหว่างที่รายงานยังไม่พร้อม ปุ่ม `Confirm` จะยืนยันและล็อกข้อมูลเท่านั้น
- แบบฟอร์ม PDF และรายละเอียด Print action จะดำเนินการหลัง workflow สมบูรณ์
- ไฟล์เอกสารอนุมัติแนบได้แต่ไม่บังคับ
- บัญชีรายได้อื่นเลือกได้ในแต่ละ Refund PV
- ยอดจ่ายจริงเป็นศูนย์ไม่ได้
- เลขที่เอกสารถูกกำหนดตอนสร้าง Draft จาก sequence ชุดเดียวกับ Vendor PV แก้ได้ใน Draft และล็อกหลัง Confirm
- การแก้ไขในอนาคตต้องรักษา uncommitted changes ที่มีอยู่ และจำกัดขอบเขตไว้ใน `buz_accounting_addon`
- งานตามแผนนี้ไม่รวมการ deploy, module upgrade, service restart หรือการเข้าถึงฐานข้อมูลที่มีอยู่
