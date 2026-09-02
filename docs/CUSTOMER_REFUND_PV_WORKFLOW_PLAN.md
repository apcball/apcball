# Customer Refund PV พร้อมเอกสารอนุมัติ

## Summary

สร้าง Customer Refund PV เป็นโมเดลแยก แต่ให้ workflow หน้าจอ และรูปแบบรายงานใกล้เคียง Vendor PV เดิม:

`Customer Credit Note → Create Refund PV → Draft → Confirmed → Print → Register Payment → In Payment → Paid`

ใช้เฉพาะส่วนของ PV ที่เกี่ยวข้อง โดยไม่แชร์ WHT หรือ payable reconciliation และสร้าง QWeb report แยกสำหรับ Customer Refund PV

## Workflow และหน้าจอ

- เพิ่มปุ่ม `Create Refund PV` บน Customer Credit Note ที่ Posted และมียอดคงเหลือ
- หนึ่ง Refund PV รองรับ Credit Note หนึ่งใบ
- หาก Credit Note มี Refund PV ที่ยัง Active อยู่แล้ว ปุ่มต้องเปิดเอกสารเดิมแทนการสร้างซ้ำ
- เมนูอยู่ที่ `Accounting > Customers > Customer Refund PV`
- Draft Form ใช้โครงและลำดับข้อมูลใกล้เคียง Vendor PV เดิม:
  - Header: เลขที่ วันที่ สถานะ และ Customer
  - Source Document: Credit Note หนึ่งใบและยอดคงเหลือ
  - Payment Planning: Cash/Transfer/Check, Journal, Payment Method และข้อมูลเช็คตามประเภท
  - Amount Summary: ยอด Credit Note, ยอดคืนจริง และรายได้อื่น
  - บัญชีรายได้อื่น เหตุผล หมายเหตุ ไฟล์แนบ และ Chatter
- ไม่แสดง WHT และ Bank Fee
- ใช้ sequence ชุดเดียวกับ Vendor PV ออกเลขตอนสร้าง Draft แก้ได้ใน Draft และล็อกหลัง Confirm
- เลขที่ของ Refund PV ที่ยกเลิกต้องเก็บไว้และห้ามนำกลับมาใช้ใหม่
- `Confirm` ตรวจสอบและล็อกข้อมูล แล้วเปลี่ยนเป็น `Confirmed` โดยยังไม่ลงบัญชี
- หลัง Confirm ห้ามแก้ Journal, Payment Method, ยอด หรือข้อมูลที่ปรากฏในเอกสารอนุมัติ
- มีปุ่ม `Print Customer Refund PV` แยก แสดงเฉพาะสถานะ Confirmed, In Payment และ Paid
- หลังได้รับอนุมัติจากเอกสาร User กด `Register Payment`
- หน้าต่าง Register Payment ให้แก้ได้เฉพาะวันที่จ่าย โดย Journal, Payment Method, ยอดคืน และส่วนต่างเป็น readonly
- มี Payments smart button และ Payment Status ในรูปแบบใกล้เคียง Vendor PV เดิม
- หากข้อมูลอนุมัติผิด ต้องยกเลิกเอกสารและสร้างใหม่

## Customer Refund PV Report

- เพิ่ม `customer_refund_pv_report.xml` และ `customer_refund_pv_template.xml` โดยไม่แก้ report เดิมของ Vendor PV
- สร้าง report action และ template ID ใหม่ ผูกกับโมเดล Customer Refund PV เท่านั้น
- ใช้ paper format A4 Portrait, โลโก้, CSS, ขนาด ระยะ ตาราง และช่องลายเซ็นเหมือน `payment_voucher_template.xml`
- ใช้หัวเอกสาร:
  - `ใบสำคัญจ่ายคืนลูกค้า`
  - `CUSTOMER REFUND PAYMENT VOUCHER`
- เปลี่ยนข้อมูลเจ้าหนี้เป็นรหัสและชื่อลูกค้า
- แสดงเลขที่และวันที่ Credit Note, ยอดเดิม และยอดคงเหลือ ณ ตอน Confirm
- แสดงยอดคืนจริง รายได้อื่น บัญชีรายได้อื่น เหตุผล และข้อมูลการจ่าย
- แสดงตัวอย่างรายการบัญชี:
  - Dr. ลูกหนี้การค้า ตามยอด Credit Note ที่นำมาปิด
  - Cr. บัญชีจ่าย ตามยอดคืนจริง
  - Cr. รายได้อื่น ตามส่วนต่าง
- เก็บยอด Credit Note เดิม ยอดคงเหลือ ยอดคืนจริง และส่วนต่างเป็น snapshot ตอน Confirm เพื่อให้พิมพ์ซ้ำหลังจ่ายแล้วได้ข้อมูลเดิม
- คงส่วน `Prepare By`, `Checked(1/2)`, `Approved(1/2)` และตำแหน่งลงวันที่เหมือนต้นฉบับ

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
- หากการสร้าง Payment การลงส่วนต่าง หรือการ Reconcile ขั้นตอนใดล้มเหลว ต้อง rollback ทั้งรายการและคง Refund PV ไว้ที่ `Confirmed`
- Draft และ Confirmed ยกเลิกได้โดยไม่เกิดรายการบัญชี
- In Payment หรือ Paid ห้าม Cancel ตรง ต้องย้อน Payment และ reconciliation ผ่านกระบวนการบัญชีก่อน

## Interfaces และขอบเขต

- เพิ่มโมเดล Customer Refund PV แยกจาก Vendor PV พร้อมลิงก์ไปยัง `account.move` และ `account.payment`
- เพิ่ม action และ smart button บน Credit Note สำหรับสร้างและเปิด Refund PV
- มีเมนูรายการ Refund PV ที่ `Accounting > Customers > Customer Refund PV` สำหรับค้นหาและติดตาม แต่เริ่มสร้างจาก Credit Note
- Accounting User สามารถสร้าง Confirm, Print และ Register Payment ได้ เพราะการอนุมัติทำบนเอกสารภายนอกระบบ
- ไฟล์เอกสารอนุมัติแนบได้แต่ไม่บังคับ
- คัดลอกเฉพาะประสบการณ์ใช้งาน โครงหน้าจอ และ layout report ที่เกี่ยวข้อง ไม่ใช้ logic บัญชีของ Vendor PV โดยตรง
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
- ตรวจ sequence ร่วมกับ Vendor PV การแก้เลขใน Draft การล็อกหลัง Confirm และการเก็บเลขเอกสารที่ยกเลิก
- ตรวจว่า Credit Note ที่มีรายการ Active จะเปิด Refund PV เดิม
- ตรวจหน้าต่าง Register Payment ว่าแก้ได้เฉพาะวันที่จ่าย
- ตรวจสถานะ Draft, Confirmed, In Payment และ Paid ตาม Bank Reconciliation
- ตรวจ Payment เป็น `outbound/customer`, partner และ journal ถูกต้อง
- ตรวจ rollback เมื่อ Payment หรือ Reconcile ล้มเหลว การ Cancel และ regression ของ Vendor PV
- ตรวจ PDF A4 เทียบ layout ต้นฉบับ รวมโลโก้ ตาราง ภาษาไทย ลายเซ็น และการไม่ล้นหน้า
- ตรวจ snapshot ยอดเดิม/ยอดคงเหลือ และการพิมพ์ซ้ำหลัง Payment
- ตรวจ Dr./Cr. preview ทั้งกรณีคืนเต็มและคืนบางส่วน
- ตรวจสิทธิ์และการซ่อนปุ่ม Print ใน Draft

## Progress Update Requirement

- หลังการแก้ไขหรือทดสอบทุกครั้งที่เกี่ยวข้องกับ `CUSTOMER_REFUND_PV` ต้องอัปเดตไฟล์นี้ด้วย
- ระบุรายการที่แก้ไข ไฟล์หรือส่วนของระบบที่ได้รับผลกระทบ การทดสอบที่ดำเนินการ และผลลัพธ์จริง
- ระบุปัญหาที่พบ ข้อจำกัด และงานที่ยังไม่เสร็จอย่างชัดเจน
- ห้ามเปลี่ยนสถานะงานหรือการทดสอบเป็นเสร็จสมบูรณ์ หากยังไม่มีผลตรวจสอบรองรับ

## Assumptions

- การอนุมัติทำบนเอกสารที่พิมพ์ออกจากระบบ ไม่มีปุ่ม Manager Approve ใน Odoo
- ปุ่ม `Confirm` ยืนยันและล็อกข้อมูล ส่วนการพิมพ์ใช้ปุ่มแยก
- ข้อมูลทางการเงินที่ปรากฏในเอกสารอนุมัติเปลี่ยนไม่ได้หลัง Confirm
- หากข้อมูลในเอกสารอนุมัติผิด ต้องยกเลิก Refund PV และสร้างใหม่
- ไฟล์เอกสารอนุมัติแนบได้แต่ไม่บังคับ
- บัญชีรายได้อื่นเลือกได้ในแต่ละ Refund PV
- ยอดจ่ายจริงเป็นศูนย์ไม่ได้
- เลขที่เอกสารถูกกำหนดตอนสร้าง Draft จาก sequence ชุดเดียวกับ Vendor PV แก้ได้ใน Draft และล็อกหลัง Confirm
- การแก้ไขในอนาคตต้องรักษา uncommitted changes ที่มีอยู่ และจำกัดขอบเขตไว้ใน `buz_accounting_addon`
- งานตามแผนนี้ไม่รวมการ deploy, module upgrade, service restart หรือการเข้าถึงฐานข้อมูลที่มีอยู่
