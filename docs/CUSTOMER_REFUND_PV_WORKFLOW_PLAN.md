# Customer Refund PV พร้อมเอกสารอนุมัติ

## Summary

สร้าง Customer Refund PV เป็นโมเดลแยกจาก Vendor PV แต่ให้ workflow หน้าจอ และรูปแบบรายงานใกล้เคียง Vendor PV เดิม:

`Customer Credit Note → Create Refund PV → Draft → Confirmed → Print → Register Payment → In Payment → Partially Refunded / Paid`

Customer Refund PV รองรับทั้งการคืนเต็มจำนวน การคืนบางส่วนโดยคงยอด Credit Note ไว้ และการคืนบางส่วนพร้อม Write-off เพื่อปิด Credit Note โดยใช้เฉพาะกลไก Customer Outbound Payment และ Receivable reconciliation ของ Odoo ไม่แชร์ WHT, Bank Fee หรือ payable reconciliation ของ Vendor PV และมี QWeb report แยกสำหรับ Customer Refund PV

## Workflow และหน้าจอ

- เพิ่มปุ่ม `Create Refund PV` บน Customer Credit Note ที่ Posted และมียอดคงเหลือมากกว่า 0
- Refund PV หนึ่งใบอ้างอิง Customer Credit Note ได้หนึ่งใบ
- Credit Note หนึ่งใบมี Refund PV ได้หลายใบแบบเรียงลำดับ แต่มีรายการ Active ได้ครั้งละหนึ่งใบเท่านั้น
- สถานะ Active ได้แก่ Draft, Confirmed, In Payment และ Exception; สถานะ Exception ต้องปิดกั้นการสร้างใบใหม่จนกว่าจะจัดการ Payment เดิมเสร็จ
- หากมี Refund PV ที่ยัง Active ปุ่มต้องเปิดเอกสารเดิมแทนการสร้างซ้ำ
- สร้าง Refund PV ใบถัดไปได้เมื่อใบก่อนเป็น Partially Refunded, Paid, Cancelled หรือ Reversed และ Credit Note ยังมียอดคงเหลือ
- เมนูอยู่ที่ `Accounting > Customers > Customer Refund PV` และใช้สำหรับค้นหา/ติดตามเท่านั้น ต้องซ่อนปุ่ม Create ใน List/Form และตรวจฝั่ง Server ว่าการสร้างรายการใหม่เริ่มจาก Posted Customer Credit Note ที่เข้าเงื่อนไข
- Draft Form ใช้โครงและลำดับข้อมูลใกล้เคียง Vendor PV เดิม:
  - Header: เลขที่ วันที่ สถานะ Customer และบริษัท
  - Source Document: Credit Note หนึ่งใบ ยอดเดิม และยอดคงเหลือปัจจุบัน
  - Payment Planning: Cash/Transfer/Check, Planned Payment Date, Journal, Payment Method และข้อมูลเช็คตามประเภท
  - Amount Summary: ยอดคงเหลือ Credit Note ก่อนทำรายการ ยอดคืนจริง วิธีจัดการส่วนต่าง และยอดส่วนต่าง
  - Write-off: บัญชีส่วนต่างและเหตุผล แสดงและบังคับเฉพาะเมื่อเลือก Write Off
  - หมายเหตุ ไฟล์แนบ และ Chatter
- ไม่แสดง WHT และ Bank Fee โดย Bank Fee ที่เกิดจริงให้บันทึกในกระบวนการ Bank Reconciliation แยกจาก Refund PV
- ใช้ date-range sequence แยกสำหรับ Customer Refund PV ต่อบริษัท รูปแบบ `CV/%(year)s/####` ออกเลขเมื่อสร้าง Draft และเริ่มใหม่ที่ `0001` ทุกปี
- เลขที่แก้ได้เฉพาะ Accounting Manager ใน Draft โดยต้องคงรูปแบบ `CV/YYYY/NNNN`, ปีในเลขต้องตรงกับ Voucher Date และห้ามซ้ำภายในบริษัทเดียวกัน
- เมื่อ Accounting Manager แก้เป็นเลขของปีเดียวกันที่มากกว่าหรือเท่ากับเลขถัดไป ระบบต้องเลื่อน sequence เป็นเลขถัดจากเลขที่แก้โดยอัตโนมัติและห้ามเลื่อน sequence ย้อนหลัง
- หลังออกเลขแล้ว Voucher Date เปลี่ยนได้เฉพาะวันที่ภายในปีเดิม หากต้องเปลี่ยนข้ามปีให้ยกเลิกเอกสารเดิมและสร้างใหม่เพื่อไม่ให้เลขกับปีของเอกสารขัดกัน
- เลขที่ของ Refund PV ที่ยกเลิกต้องเก็บไว้และห้ามนำกลับมาใช้ใหม่
- ห้ามลบ Refund PV ทุกสถานะ ต้องใช้ Cancel/Reversal ตาม workflow เพื่อรักษาเลขเอกสารและ audit trail
- `Confirm` ตรวจข้อมูล ยอดคงเหลือ และรายการ Active ซ้ำแบบ transactional จากนั้นเก็บ confirmation snapshot และล็อกข้อมูลอนุมัติ โดยยังไม่สร้าง Payment หรือ Journal Entry ใหม่
- หลัง Confirm ห้ามแก้เลขที่, Credit Note, Customer, Journal, Payment Method, Planned Payment Date, ยอดคืน, วิธีจัดการส่วนต่าง, บัญชีส่วนต่าง, เหตุผล และข้อมูลเช็ค
- มีปุ่ม `Print Customer Refund PV` แยก แสดงเฉพาะสถานะ Confirmed, In Payment, Partially Refunded และ Paid
- หลังได้รับอนุมัติจากเอกสาร User กด `Register Payment`
- หน้าต่าง Register Payment ใช้ CV-specific wrapper wizard ที่แสดงให้แก้ได้เฉพาะ Actual Payment Date ส่วน Journal, Payment Method, ยอดคืน, วิธีจัดการส่วนต่าง และบัญชีส่วนต่างแสดงเป็น readonly; เมื่อยืนยันจึงเรียก `account.payment.register` มาตรฐานด้านหลังพร้อมตรวจซ้ำฝั่ง Server
- มี Payments smart button, Credit Note smart button และ Payment Status
- หากข้อมูลอนุมัติผิด ต้องยกเลิก Refund PV และสร้างใหม่ ห้ามย้อนเป็น Draft เพื่อแก้ข้อมูลที่ Confirm แล้ว
- ไฟล์เอกสารอนุมัติแนบได้แต่ไม่บังคับ
- ระบบต้องบันทึกผู้สร้าง ผู้ Confirm ผู้ Register Payment วันเวลา จำนวนเงิน บัญชีส่วนต่าง และทุกการเปลี่ยนสถานะใน Chatter

## Document State และ Workflow State

- แยกสถานะเอกสารออกจากสถานะการจ่ายเพื่อไม่ให้เหตุการณ์จาก Payment เขียนทับ approval lifecycle
- Document State (`state`):
  - `Draft`: จัดเตรียมและแก้ไขข้อมูลได้ตามสิทธิ์
  - `Confirmed`: ข้อมูลอนุมัติถูกล็อก และใช้เป็น state หลักระหว่าง/หลังการจ่าย
  - `Cancelled`: ยกเลิกก่อนเกิด Payment โดยเก็บเลขเอกสารและ audit trail ไว้
- Workflow State (`workflow_state`) คำนวณจาก Document State, Payment, Credit Note residual และ bank reconciliation:
  - `Draft`: เอกสารยังไม่ Confirm
  - `Confirmed`: Confirm แล้วและยังไม่มี Payment
  - `In Payment`: สร้างและ Post Payment สำเร็จ แต่ Transfer/Check ยังไม่ Bank Reconcile
  - `Partially Refunded`: Payment ของ Refund PV เสร็จสมบูรณ์แล้ว แต่ Credit Note ยังมียอดคงเหลือจาก Keep Open
  - `Paid`: Payment เสร็จสมบูรณ์และ Credit Note ที่ Refund PV ใบนี้จัดการถูกปิดครบ
  - `Exception`: Payment หรือ Receivable reconciliation ไม่สอดคล้องและยังต้องแก้ไข สถานะนี้ถือเป็น Active
  - `Reversed`: Payment และ reconciliation เดิมถูกย้อนครบแล้ว เป็นสถานะปลายทางและสร้าง Refund PV ใหม่ได้หาก Credit Note ยังมียอดคงเหลือ
  - `Cancelled`: Document State ถูกยกเลิกก่อนเกิด Payment
- Transfer และ Check ต้องอยู่ In Payment จน Payment ถูกจับคู่กับ Bank Statement
- Cash สามารถเป็น Paid หรือ Partially Refunded ได้ทันทีเมื่อ Payment ถูก Post เข้าบัญชีเงินสดและ Receivable reconciliation สำเร็จ
- สถานะต้องคำนวณจาก `account.payment` และหลักฐาน Bank reconciliation ที่ลิงก์กับ Refund PV โดยตรง ไม่อาศัย `account.move.payment_state` เพียงอย่างเดียว
- การยกเลิก Bank Statement reconciliation โดยที่ Payment ยัง Posted และยัง reconcile กับ Credit Note ให้ย้อนจาก Paid/Partially Refunded เป็น In Payment ไม่ใช่ Exception
- การ Unreconcile ระหว่าง Payment กับ Credit Note, Reset Payment เป็น Draft หรือข้อมูลบัญชีไม่สอดคล้อง ให้เป็น Exception จนกว่าจะย้อนรายการครบ; เมื่อ Payment ถูกยกเลิกและ Credit Note residual คืนครบจึงเปลี่ยนเป็น Reversed

## Difference Handling

- `Keep Open`:
  - สร้าง Payment ตามยอดคืนจริง
  - Reconcile เฉพาะยอดคืนจริงกับ Credit Note
  - คง residual ที่เหลือของ Credit Note ไว้สำหรับหัก Invoice หรือสร้าง Refund PV ใบถัดไป
  - เมื่อ Payment เสร็จสมบูรณ์และ Credit Note ยังมียอดคงเหลือ Refund PV เป็น Partially Refunded
- `Write Off`:
  - สร้าง Payment ตามยอดคืนจริง
  - ลงส่วนต่างเพื่อปิด residual ของ Credit Note ทั้งหมด
  - บังคับเลือกบัญชีส่วนต่างของบริษัทเดียวกันและกรอกเหตุผล
  - บัญชีต้อง Active, ไม่ Deprecated และมี `account_type` เป็น `income` หรือ `income_other` ที่ฝ่ายบัญชีอนุมัติให้ใช้สำหรับกรณีนี้
  - เมื่อ Payment และ reconciliation เสร็จสมบูรณ์ Credit Note ต้องมียอดคงเหลือเป็นศูนย์
- หากยอดคืนจริงเท่ากับยอดคงเหลือ วิธีจัดการส่วนต่างไม่มีผลและยอดส่วนต่างเป็นศูนย์
- การรับรู้ส่วนต่างเป็นรายได้ต้องเป็นไปตามนโยบายบัญชีและภาษีที่บริษัทอนุมัติ ระบบไม่ตัดสินเหตุผลทางภาษีแทน User

## Customer Refund PV Report

- เพิ่ม `customer_refund_pv_report.xml` และ `customer_refund_pv_template.xml` โดยไม่แก้ report เดิมของ Vendor PV
- สร้าง report action และ template ID ใหม่สำหรับโมเดล Customer Refund PV เท่านั้น แต่ไม่กำหนด `binding_model_id` เพื่อไม่ให้ Print menu ข้ามการตรวจสถานะ; ต้องพิมพ์ผ่านปุ่ม object ที่ตรวจสิทธิ์/สถานะและบันทึก Chatter
- เพิ่ม report adapter ฝั่ง Server ที่ตรวจ access rights และอนุญาตให้ render เฉพาะ Confirmed, In Payment, Partially Refunded และ Paid แม้ถูกเรียกผ่าน report URL/RPC โดยตรง; Draft, Cancelled, Exception และ Reversed ต้องถูกปฏิเสธ
- ใช้ paper format A4 Portrait แบบไม่เป็นค่า Default ของระบบ และใช้โลโก้/ฟอนต์ Sarabun จาก `buz_accounting_addon` โดยตรง; CSS, ขนาด ระยะ ตาราง และช่องลายเซ็นอ้างอิง `payment_voucher_template.xml` โดยไม่ inherit หรือแก้ template เดิม
- ใช้หัวเอกสาร:
  - `ใบสำคัญจ่ายคืนลูกค้า`
  - `CUSTOMER REFUND PAYMENT VOUCHER`
- แสดงรหัสและชื่อลูกค้าแทนข้อมูลเจ้าหนี้
- แสดงเลขที่/วันที่ Credit Note, ยอดเดิม, ยอดคงเหลือก่อนทำรายการ, ยอดคืนจริง, วิธีจัดการส่วนต่าง, ยอดส่วนต่าง, บัญชีส่วนต่าง, เหตุผล และข้อมูลการจ่าย
- ก่อนมี Payment ตารางบัญชีต้องระบุว่า `รายการบัญชีคาดการณ์ / Proposed Journal Entry`
- หลังมี Payment ให้แสดง Payment Number, Actual Payment Date, Journal Entry Number และสถานะล่าสุด
- แสดงรายการบัญชีคาดการณ์ตามวิธีจัดการส่วนต่าง:
  - Keep Open: Dr. ลูกหนี้การค้าตามยอดคืนจริง และ Cr. บัญชีจ่ายตามยอดคืนจริง
  - Write Off: Dr. ลูกหนี้การค้าตามยอดที่นำมาปิด, Cr. บัญชีจ่ายตามยอดคืนจริง และ Cr. บัญชีส่วนต่างตามยอด Write-off
- เก็บยอด Credit Note เดิม ยอดคงเหลือ ณ ตอน Confirm ยอดคืนจริง วิธีจัดการส่วนต่าง ยอดส่วนต่าง และข้อมูลอนุมัติเป็น confirmation snapshot เพื่อการตรวจสอบย้อนหลัง
- PDF ใช้ข้อมูลล่าสุด ณ เวลาพิมพ์ โดยข้อมูลอนุมัติที่ล็อกแล้วมาจาก confirmation snapshot และข้อมูล Payment/Journal Entry/สถานะมาจากรายการจริงล่าสุด
- PDF ที่พิมพ์ก่อนและหลัง Register Payment อาจแตกต่างกัน จึงต้องแสดง `Printed At` และผู้พิมพ์ทุกครั้ง
- คงส่วน `Prepare By`, `Checked(1/2)`, `Approved(1/2)` และตำแหน่งลงวันที่เหมือนต้นฉบับ

## Accounting Behavior

- ยอดคืนจริงต้องมากกว่า 0 และไม่เกินยอดคงเหลือ Credit Note ณ เวลาที่ตรวจสอบ
- ระบบคำนวณส่วนต่างอัตโนมัติ: `ยอดคงเหลือ Credit Note ก่อนทำรายการ - ยอดคืนจริง`
- `Register Payment` ใช้กลไกมาตรฐานของ Odoo เพื่อสร้างและ Post Customer Outbound Payment ประเภท `outbound/customer`
- Keep Open ต้อง Reconcile Payment กับ Credit Note เฉพาะยอดคืนจริงและคง residual ที่เหลือไว้
- Write Off ต้อง Reconcile Payment และส่วนต่างกับ Credit Note เพื่อให้ residual เป็นศูนย์
- Journal, Payment Method, Payment Account และ Write-off Account ต้องอยู่บริษัทเดียวกับ Refund PV
- ใช้สกุลเงินบริษัทเท่านั้น และเปรียบเทียบจำนวนเงินด้วย currency rounding ของ Odoo
- ตรวจ Credit Note ต้องเป็น Posted `out_refund`, Customer/Commercial Partner และบริษัทต้องตรงกัน และยอดคงเหลือต้องมากกว่า 0
- ตรวจยอดคงเหลือและ Refund PV ที่ Active ซ้ำก่อน Confirm และ Register Payment พร้อม lock แถว Credit Note เพื่อป้องกัน concurrent creation/payment
- Refund PV ต้องลิงก์ Payment และ Journal Entry ด้วย relational field ไม่ค้นหาจากข้อความ reference อย่างเดียว
- Payment, write-off และ reconciliation ต้องสำเร็จใน transaction เดียว หากขั้นตอนใดล้มเหลวต้อง rollback ทั้งรายการและคง Refund PV ไว้ที่ Confirmed
- ห้ามจับ reconciliation error แล้วบันทึกเพียง log โดยปล่อย Payment ค้างโดยไม่แจ้ง User
- Draft และ Confirmed ยกเลิกได้โดยไม่เกิดรายการบัญชี
- In Payment, Partially Refunded หรือ Paid ห้าม Cancel ตรง ต้องย้อน Payment และ reconciliation ผ่านกระบวนการบัญชีก่อน
- เมื่อยกเลิกเฉพาะ Bank Statement reconciliation ให้ workflow กลับเป็น In Payment; เมื่อ Unreconcile Payment ออกจาก Credit Note หรือ Reset Payment เป็น Draft ให้เป็น Exception; เมื่อย้อนและ Cancel Payment ครบถ้วนให้เป็น Reversed พร้อมเก็บประวัติเดิม
- Actual Payment Date ต้องไม่ก่อนวันที่ Credit Note และต้องผ่าน Accounting Lock Date/Journal validation มาตรฐานของ Odoo
- หาก Credit Note มีหลาย Receivable lines จาก Payment Terms ต้องใช้กลไกมาตรฐานของ `account.payment.register` และ reconcile ตามลำดับ maturity โดยไม่สร้าง logic หักยอดแบบ manual

## Interfaces และขอบเขต

- เพิ่มโมเดล `buz.customer.refund.voucher` แยกจาก Vendor PV พร้อมลิงก์ไปยัง `account.move` และ `account.payment`
- เพิ่ม selection สำหรับ Difference Handling: `keep_open` และ `writeoff`
- เพิ่ม confirmation snapshot, Planned Payment Date และข้อมูล audit ที่จำเป็น
- ใช้ `state` สำหรับ document lifecycle และ `workflow_state` สำหรับ payment lifecycle ตามกติกาข้างต้น
- เพิ่ม action และ smart button บน Credit Note สำหรับสร้างและเปิด Refund PV
- มีเมนูรายการ Refund PV ที่ `Accounting > Customers > Customer Refund PV` โดยปิดการ Create จากเมนูทั้งใน View และฝั่ง Server
- Accounting User สามารถสร้าง Confirm, Print และ Register Payment ได้ตามสิทธิ์บัญชีมาตรฐาน
- เฉพาะ Accounting Manager แก้เลขที่ใน Draft และยกเลิกเอกสารตามเงื่อนไขที่กำหนด
- ไฟล์เอกสารอนุมัติแนบได้แต่ไม่บังคับ เพราะการอนุมัติทำบนเอกสารภายนอกระบบ
- คัดลอกเฉพาะประสบการณ์ใช้งาน โครงหน้าจอ และ layout report ที่เกี่ยวข้อง ไม่ใช้ logic บัญชีของ Vendor PV โดยตรง
- ไม่เปลี่ยน logic, WHT, report, payable reconciliation หรือข้อมูลเดิมของ Vendor PV และไม่แก้ `account_ar_settlement`
- เพิ่ม context key เฉพาะ เช่น `buz_customer_refund_voucher_id`; ทุก override ของ `account.payment.register` ต้องทำงานเฉพาะเมื่อ context นี้ชี้ไปยัง Refund PV ที่มีสิทธิ์เข้าถึงและอยู่สถานะ Confirmed แล้วเรียก `super()` ตาม Odoo 17
- ห้ามใช้ context ทั่วไป `force_amount` ของ Vendor PV; ต้องตรวจและบังคับ Amount, Journal, Payment Method, Difference Handling และ Write-off Account จาก Refund PV ซ้ำฝั่ง Server โดยไม่เชื่อค่าจาก client context
- ส่ง `skip_wht_deduct=True` และตรวจว่า WHT fields ว่างสำหรับ CV flow เพื่อไม่ให้ `l10n_th_account_tax` หัก WHT อัตโนมัติ
- หากมี `sr_extra_bank_charges` ต้องซ่อนและบังคับ Bank Charge เป็นศูนย์ใน CV context; Bank Fee จริงบันทึกใน Bank Reconciliation เท่านั้น
- ต้องรักษา `super()` chain ของ Employee Advance, Exchange Rate และโมดูลอื่นที่ inherit `account.payment.register`; ห้ามเพิ่ม dependency ไปยังโมดูล optional เหล่านี้
- เพิ่ม relational field เฉพาะจาก `account.payment` ไปยัง Customer Refund PV โดยไม่เปลี่ยนหรือใช้ `buz_payment_voucher_id` ของ Vendor PV
- เพิ่ม access rights และ multi-company record rule `company_id in company_ids`; ทุก Many2one ทางบัญชีใช้ `check_company` และห้ามใช้ `sudo()` เพื่อข้ามสิทธิ์ใน CV-specific logic
- รอบแรกจำกัดสกุลเงินเดียวกับบริษัทและยังไม่รองรับผลต่างอัตราแลกเปลี่ยน
- การพัฒนาและตรวจสอบทั้งหมดเป็น Local-only ห้าม deploy, SSH, upload ไฟล์ขึ้น Server, upgrade module หรือ restart service/container
- ห้ามทดสอบหรือดำเนินการใด ๆ กับฐานข้อมูล DEV, PROD และฐานข้อมูลเดิมหรือฐานข้อมูลอื่น
- ห้ามแก้ไข ลบ ย้าย backfill หรือทำ migration กับข้อมูลเดิมทุกประเภท
- การทดสอบที่ต้องใช้ฐานข้อมูลให้ใช้เฉพาะ isolated test database ที่สร้างใหม่และไม่มีข้อมูลธุรกรรมเดิม

## Implementation Structure และ Load Order

- เป้าหมาย module version หลังพัฒนา: `17.0.3.0.0` จาก checkout ปัจจุบัน `17.0.2.1.0`
- Models:
  - เพิ่ม `models/customer_refund_voucher.py` สำหรับโมเดล, sequence, validation, state/workflow, snapshots, actions และ audit
  - ขยาย `models/account_move.py` เฉพาะปุ่ม/smart button และ action สร้างหรือเปิด Refund PV จาก Customer Credit Note
  - ขยาย `models/account_payment.py` ด้วย Many2one `buz_customer_refund_voucher_id` แบบ `index=True`, `copy=False` และ `ondelete='restrict'` โดยไม่แก้ `buz_payment_voucher_id` เดิม
  - ขยาย `models/account_payment_register.py` ด้วย CV-specific helper และ context guard โดยรักษา Vendor PV/Receipt branches เดิม
- Wizard:
  - เพิ่ม `wizard/customer_refund_payment_wizard.py` เป็น wrapper ที่มี `voucher_id` และ `payment_date`; ข้อมูล Journal, Payment Method, Amount, Difference Handling และ Write-off แสดง readonly จาก Voucher และไม่รับค่าการเงินจาก client
  - `action_create_payment()` ตรวจสิทธิ์และข้อมูล Voucher แล้วสร้าง `account.payment.register` ภายในด้วย CV-specific context จากนั้นเรียก `_create_payments()` มาตรฐานใน transaction เดียว
- Payment Register integration:
  - ปุ่ม Register Payment เปิด CV-specific wrapper; wrapper ส่ง `active_model='account.move'`, Credit Note ID, `buz_customer_refund_voucher_id` และ `skip_wht_deduct=True` ให้ Payment Register มาตรฐาน
  - Override `_create_payments()` ตรวจสิทธิ์, Confirmed state, active uniqueness, residual, immutable values, company, currency, journal, method และ write-off ก่อนเรียก `super()`
  - Override `_create_payment_vals_from_wizard()` และ `_create_payment_vals_from_batch()` เฉพาะ CV context เพื่อเติม relational link และบังคับค่าจาก Refund PV; ห้ามเชื่อ Amount/Journal/Write-off จาก client
  - ให้ standard Odoo ทำ `_init_payments() → _post_payments() → _reconcile_payments()` ใน transaction เดียว ห้ามสร้าง/reconcile Payment ซ้ำเอง
  - หลัง `super()._create_payments()` สำเร็จ ตรวจว่า Payment ที่คืนมาลิงก์กับ CV และ source Credit Note ถูกต้อง แล้วบันทึก Chatter; exception ใด ๆ ต้อง propagate เพื่อ rollback ทั้ง transaction
- Views/Security:
  - เพิ่ม `views/customer_refund_voucher_views.xml` และแก้ `views/account_move_views.xml` แบบ additive หลังตรวจ XPath ของ `account.view_move_form`
  - เพิ่ม `security/customer_refund_voucher_security.xml` ก่อน `security/ir.model.access.csv` เพื่อโหลด record rule ก่อน views/actions
  - เพิ่ม `views/customer_refund_payment_wizard_views.xml` เป็น form แยก จึงไม่ inherit หรือเปลี่ยน `account.view_account_payment_register_form` และไม่แสดง WHT/Bank Charge fields จากโมดูลอื่น
  - เมื่อสร้าง standard wizard ภายใน ให้กำหนด WHT เป็น False และกำหนด Bank Charge เป็นศูนย์เฉพาะเมื่อ field นั้นมีอยู่ใน `_fields`; ห้ามอ้าง optional field ใน XML หรือเพิ่ม optional module เป็น dependency
- Reports:
  - เพิ่ม `reports/customer_refund_pv_report.py`, `reports/customer_refund_pv_report.xml` และ `reports/customer_refund_pv_template.xml`
  - Report adapter เป็นชั้นบังคับ access/state สำหรับทั้งปุ่ม, report URL และ RPC; ปุ่มพิมพ์เป็นผู้บันทึก Printed At/Printed By ใน Chatter
  - โหลด paper format/report action ก่อน template และไม่ตั้ง paper format เป็น Default
- Data/Manifest:
  - เพิ่ม annual date-range sequence ใน `data/sequence.xml` แบบ additive โดยไม่แก้ code/record ของ Vendor PV
  - อัปเดต `models/__init__.py`, `wizard/__init__.py`, `reports/__init__.py` และ manifest เฉพาะรายการใหม่
  - Manifest load order: sequence → security rules → access CSV → report action/paper format → report template → Refund PV views → account.move inherited view → CV payment wrapper view
- Tests:
  - เพิ่ม `tests/test_customer_refund_voucher.py` และ import ผ่าน `tests/__init__.py`
  - สร้าง `docker-compose.accounting-refund-pv.test.yml` เป็น project/database/volume แยก ห้ามแก้ `docker-compose.test.yml` เดิมซึ่งใช้ทดสอบ `agreement_rebate`

## Test Plan

- ตรวจ flow และโครง Draft Form เทียบกับ Vendor PV โดยไม่ทำให้ Vendor PV เปลี่ยนพฤติกรรม
- คืนเต็ม 980: Payment 980 ไม่มีส่วนต่าง Credit Note ปิด และ Refund PV เป็น In Payment/Paid ตามประเภทการจ่าย
- คืน 700 จาก 980 แบบ Keep Open: Payment 700, Credit Note เหลือ 280 และ Refund PV จบเป็น Partially Refunded
- จาก Credit Note ที่เหลือ 280 สร้าง Refund PV ใบถัดไปและปิดยอดได้ โดยไม่อนุญาตให้สร้างขณะใบก่อนยัง Active
- คืน 700 จาก 980 แบบ Write Off: Payment 700, ส่วนต่าง 280, Credit Note ปิด และ Journal Entry สมดุล
- ตรวจ Cash, Transfer และ Check พร้อมเงื่อนไขแสดงข้อมูลและสถานะที่เกี่ยวข้อง
- ปฏิเสธยอด 0, ยอดติดลบ, ยอดเกิน residual, Write-off ที่ไม่มีบัญชี/เหตุผล และบัญชีผิดบริษัทหรือผิดประเภท
- ตรวจ annual date-range sequence `CV/YYYY/NNNN` แยกบริษัท เริ่ม `0001` ทุกปี การแก้เลขโดย Manager การเลื่อนเลขถัดไป การห้ามเลขซ้ำ การห้ามเปลี่ยน Voucher Date ข้ามปี และการเก็บเลขที่ยกเลิก
- ตรวจว่า Credit Note ที่มี Refund PV Active จะเปิดรายการเดิม และทดสอบการกดสร้างพร้อมกันสอง transaction
- ตรวจ CV-specific Register Payment wrapper ว่าแก้ได้เฉพาะ Actual Payment Date ทั้งใน UI และ RPC/server-side และค่าการเงินทั้งหมดถูกอ่านใหม่จาก Voucher ก่อนสร้าง standard wizard
- ตรวจ Transfer/Check เป็น In Payment จน Bank Reconcile และ Cash จบสถานะได้ทันที
- ตรวจ Payment เป็น `outbound/customer`, partner, receivable account, journal, payment method และ company ถูกต้อง
- ตรวจ Actual Payment Date, Accounting Lock Date, currency rounding และ Credit Note ที่มีหลาย maturity lines
- ตรวจ Keep Open ใน Aged Receivable ว่ายังคง residual ถูกต้อง และ Write Off ทำให้ residual เป็นศูนย์
- ตรวจ rollback เมื่อ Payment, Write-off หรือ Reconcile ล้มเหลวโดยไม่เหลือ Payment/Journal Entry บางส่วน
- ตรวจ Bank Statement unreconcile กลับ In Payment, Receivable unreconcile/Reset Payment เข้า Exception, reversal สมบูรณ์เข้า Reversed และการห้าม Cancel Refund PV โดยตรงหลังมี Payment
- ตรวจ PDF A4 ก่อนและหลัง Payment รวมโลโก้ ตาราง ภาษาไทย ลายเซ็น Print Timestamp และการไม่ล้นหน้า
- ตรวจ confirmation snapshot, PDF ข้อมูลล่าสุด, Payment Number, Actual Payment Date และ Journal Entry Number
- ตรวจ Dr./Cr. preview และ Journal Entry จริงทั้งคืนเต็ม Keep Open และ Write Off
- ตรวจสิทธิ์ Accounting User/Manager การซ่อนปุ่ม Print ใน Draft และการแก้เลขเฉพาะ Manager ใน Draft
- ตรวจว่าปุ่ม Create จากเมนู, RPC create ที่ไม่มี Credit Note context, Print menu และ direct report call ไม่สามารถข้าม workflow ได้
- ตรวจ multi-company record rule, company checks, การห้าม unlink และการสร้างพร้อมกันสอง transaction
- ตรวจ co-install regression ของ Vendor PV, Receipt Voucher และ `l10n_th_account_tax`
- ตรวจ compatibility เมื่อมี Employee Advance, `sr_extra_bank_charges`, Exchange Rate, Check Layout และ Payment Report โดย context ที่ไม่ใช่ CV ต้องให้ผลเดิม
- ตรวจว่า `account_ar_settlement` และ Inter-Customer Clearing Payment ไม่ถูกเรียกหรือเปลี่ยนพฤติกรรมจาก CV flow

## Acceptance Gates

- Static checks: Python AST, XML syntax, XML ID, XPath target, manifest load order และ `git diff --check`
- Isolated Odoo tests: module install/upgrade บนฐานข้อมูลใหม่และ test suite ผ่านโดยไม่มี failed/error
- Co-install regression: ทดสอบกับโมดูลที่เกี่ยวข้องโดยตรงและตรวจ `super()` chain/context isolation โดยไม่อ้างผลจากฐานข้อมูล DEV/PROD
- Browser UAT: สร้าง Confirm Print Register Payment และเปิด smart buttons ด้วยสิทธิ์ User/Manager
- PDF UAT: ตรวจไฟล์ PDF จริงก่อนและหลัง Payment เทียบ layout ต้นฉบับ
- Accounting UAT: ตรวจ Journal Entry, Aged Receivable, Outstanding Payments, Bank Reconciliation, Cash และ Write-off ด้วยฝ่ายบัญชี
- Tax/account policy sign-off: ฝ่ายบัญชี/ภาษีอนุมัติบัญชีและเหตุผลที่ใช้ Write-off ก่อน Production
- ผ่าน acceptance gate แต่ละประเภทแยกกัน ห้ามใช้ static/module test แทน Browser, PDF หรือ Accounting UAT

## Progress Update Requirement

- หลังการแก้ไขหรือทดสอบทุกครั้งที่เกี่ยวข้องกับ `CUSTOMER_REFUND_PV` ต้องอัปเดตไฟล์นี้ด้วย
- ระบุรายการที่แก้ไข ไฟล์หรือส่วนของระบบที่ได้รับผลกระทบ การทดสอบที่ดำเนินการ และผลลัพธ์จริง
- ระบุปัญหาที่พบ ข้อจำกัด และงานที่ยังไม่เสร็จอย่างชัดเจน
- ห้ามเปลี่ยนสถานะงานหรือการทดสอบเป็นเสร็จสมบูรณ์ หากยังไม่มีผลตรวจสอบรองรับ

### 2026-09-02 — Requirements Review

- อัปเดตข้อกำหนดให้รองรับ Keep Open และ Write Off
- เปลี่ยนเป็น sequence แยก `CV/%(year)s/####` ต่อบริษัท โดย Accounting Manager แก้ได้ใน Draft
- เพิ่ม Partially Refunded และแยก Exception ออกจาก Reversed พร้อมกติกาสถานะ Cash/Transfer/Check
- แยก Planned Payment Date และ Actual Payment Date
- กำหนด PDF เป็นข้อมูลล่าสุดพร้อม Print Timestamp และเก็บ confirmation snapshot สำหรับ audit
- เพิ่ม transaction/concurrency, reversal, lock date, actual Journal Entry และ acceptance gates
- ทบทวนความเข้ากันได้กับ Odoo 17 และโมดูลที่เกี่ยวข้อง พบว่าต้องแยก document/workflow state, scope Payment Register ด้วย CV context, ป้องกัน WHT/Bank Charge และปิดช่อง Create/Print/RPC bypass
- กำหนด sequence ให้เริ่ม `0001` ใหม่ทุกปีและห้ามเปลี่ยน Voucher Date ข้ามปีหลังออกเลข
- แยก Exception ออกจาก Reversed และกำหนด Bank Statement unreconcile ให้กลับ In Payment
- แก้โครง bullet ของ Write Off, เพิ่ม Reversed ในเงื่อนไขสร้างใบถัดไป และเพิ่ม server-side report validation
- ระบุ Payment Register integration hooks, module version, ไฟล์/manifest load order และ isolated Compose แยกโดยไม่แก้ test profile กลาง
- เปลี่ยนหน้าต่าง Register Payment เป็น CV-specific wrapper ที่แก้ได้เฉพาะ Actual Payment Date และเรียก Payment Register มาตรฐานด้านหลัง เพื่อไม่แก้ view หรือแสดง fields ของ Payment flow อื่น
 - การตรวจครั้งนี้เป็นการทบทวนและแก้ไขเอกสารเท่านั้น ยังไม่มีการแก้โค้ด ติดตั้งโมดูล ทดสอบฐานข้อมูล Browser/PDF UAT หรือ Accounting UAT
 - สถานะ: หลังการแก้ไขนี้ข้อกำหนดพร้อมใช้เป็นฐานพัฒนา แต่การรับรองว่าไม่กระทบโมดูลอื่นต้องมีผล isolated co-install regression, Browser/PDF UAT และ Accounting UAT รองรับ

### 2026-09-02 — Implementation (Phase 1)

 - สร้าง `models/customer_refund_voucher.py` (`buz.customer.refund.voucher`) พร้อม state/workflow_state แยก, sequence `CV/YYYY/NNNN` แบบ date_range, snapshot, audit, validation, concurrency lock และห้ามลบ
 - ขยาย `models/account_move.py` เพิ่มปุ่ม Create Refund PV / smart button และ helper สำหรับ Credit Note `out_refund` Posted เท่านั้น
 - ขยาย `models/account_payment.py` เพิ่ม `buz_customer_refund_voucher_id` (`index=True`, `copy=False`, `ondelete='restrict'`)
 - ปรับ `models/account_payment_register.py` ให้ guard ด้วย `buz_customer_refund_voucher_id` เท่านั้น, บังคับ amount/journal/method/handling/writeoff จาก CV, ส่ง `skip_wht_deduct=True`, ล็อก Credit Note `SELECT FOR UPDATE` และคง `super()` chain
 - เพิ่ม `wizard/customer_refund_payment_wizard.py` wrapper ให้แก้ได้เฉพาะ Actual Payment Date และเรียก `account.payment.register` มาตรฐานภายใน transaction เดียว
 - เพิ่ม `data/sequence.xml` แบบ additive ด้วย annual date_range `buz.customer.refund.voucher`
 - เพิ่ม `security/customer_refund_voucher_security.xml` (record rule `company_id in company_ids`) ก่อน `security/ir.model.access.csv`
 - เพิ่ม `views/customer_refund_voucher_views.xml` (menu `Accounting > Customers > Customer Refund PV`, create=false), `views/customer_refund_payment_wizard_views.xml` และ `views/account_move_views.xml` แบบ additive (ตรวจ XPath ของ `account.view_move_form`)
 - เพิ่ม `reports/customer_refund_pv_report.py` adapter ตรวจ access/state (ให้ render เฉพาะ Confirmed/In Payment/Partially Refunded/Paid แม้เรียกผ่าน URL/RPC), `reports/customer_refund_pv_report.xml` (paperformat A4 ไม่ default), `reports/customer_refund_pv_template.xml` (แยกจาก Vendor PV, ใช้โลโก้/ฟอนต์ Sarabun จาก `buz_accounting_addon`)
 - อัปเดต `models/__init__.py`, `wizard/__init__.py`, `reports/__init__.py`, `__manifest__.py` เวอร์ชัน `17.0.3.0.0` และลำดับโหลด: sequence → security rules → access CSV → report action/paperformat → report template → Refund PV views → account.move view → CV wizard view
 - เพิ่ม `docker-compose.accounting-refund-pv.test.yml` แยก project/database/volume (ไม่แก้ `docker-compose.test.yml` กลาง) สำหรับ isolated test
 - เพิ่ม `tests/test_customer_refund_voucher.py` ครอบคลุม Full Refund, Keep Open, Write Off, sequence/name edit, active uniqueness, wrapper guard, unlink/print validation, multi-company, co-existence กับ Vendor PV
 - Static checks: Python AST ผ่าน 6 ไฟล์, XML syntax ผ่าน 5 ไฟล์, `git diff --check` ไม่พบ whitespace error, `docker compose config` ผ่าน
 - Isolated Odoo install/upgrade + test suite ยังไม่ได้รันบน DB จริง (รอการรัน `docker compose -f docker-compose.accounting-refund-pv.test.yml up --abort-on-container-exit` แยกจาก DEV/PROD)
 - Co-install regression, Browser UAT, PDF UAT, Accounting UAT ยังไม่ได้ทดสอบ — ต้องมีผลจริงก่อนสรุปว่าผ่าน
 - ไม่มีการ Deploy, SSH, Upgrade DEV/Production, Restart service/container หรือเข้าถึง `MOG_DEV`/`MOG_TEST` เดิม
 - ข้อจำกัด/งานค้าง: workflow `in_payment` ↔ bank reconciliation ยังใช้ heuristic (`is_matched`/`statement_line_ids`), `reversed`/`exception` จากการยกเลิก payment/bank statement ต้องทดสอบร่วมกับ bank statement จริง, การเลื่อน sequence แบบ date_range ต้องยืนยันกับ `ir.sequence.date_range` จริง, ต้องทดสอบ并发 two transactions แบบตั้งใจ, ต้องทดสอบสิทธิ์ Manager vs User แบบละเอียด

### 2026-09-02 — Odoo 17 Write-off Account Validation Fix

 - แก้ `models/customer_refund_voucher.py` ไม่ให้อ่าน `account.account.active` ซึ่งไม่มีใน Odoo 17 และใช้ `deprecated` ซึ่งเป็น field มาตรฐานสำหรับปิดการใช้งานบัญชีแทน
 - ยังคงบังคับว่าบัญชี Write-off ต้องอยู่บริษัทเดียวกันและเป็นประเภท Income ตามข้อกำหนดเดิม
 - เพิ่ม regression test ยืนยันว่าบัญชี Income ที่ใช้งานได้ไม่เกิด `AttributeError` ใน Write-off flow และบัญชีที่ `deprecated=True` ถูกปฏิเสธ
 - การตรวจ source ยืนยันว่า `odoo:17.0` มี field `account.account.deprecated` และไม่มี `account.account.active`
 - การรัน isolated test รอบแรกติดที่ test setup เดิมซึ่งพยายามเปลี่ยนสกุลเงินบริษัทหลังมี Journal Items แล้ว ทำให้ Customer Refund tests ทั้ง 12 รายการ error ก่อนเข้า test logic; แก้ setup ให้ใช้ company currency ที่ฐานข้อมูลสร้างไว้โดยไม่เปลี่ยนค่าบริษัท
 - isolated test รอบถัดมายืนยันว่า regression test ของบัญชี `deprecated=True` ผ่าน และ Write-off flow ผ่าน constraint ที่เคยเกิด `AttributeError`; full suite ยังเหลือปัญหาเดิมคนละจุด 1 failed/3 errors ได้แก่ field `memo` ของ `account.payment`, test แก้ Payment Method หลัง Confirm และ amount guard
 - regression tests แบบเจาะจงผ่าน 2/2 ด้วยผล `0 failed, 0 error(s)` ครอบคลุมบัญชี Income ที่ใช้งานได้และบัญชี `deprecated=True`
 - ตัด `currency_id` ซึ่งเป็น readonly related field ออกจาก `@api.constrains`; การเปลี่ยนบริษัทและสกุลเงินยังถูกตรวจผ่าน `company_id` ที่อยู่ใน constraint เดิม
 - ยังไม่ได้ Deploy หรือแก้ไขฐานข้อมูล DEV/Production; ปัญหา full suite ที่เหลือต้องแก้แยกก่อนรับรอง workflow ทั้งชุด

### 2026-09-02 — DEV Deployment: Write-off Validation Fix

 - อัปโหลดเฉพาะ `buz_accounting_addon` ไปยัง DEV ด้วย `scp`; ไม่ได้อัปโหลดโฟลเดอร์ `docs` และไม่ได้แตะ Production
 - ยืนยันไฟล์บน DEV มี validation `if acc.deprecated` ก่อน upgrade
 - upgrade เฉพาะโมดูล `buz_accounting_addon` บนฐาน `MOG_DEV` สำเร็จด้วย exit code `0`; registry โหลดสำเร็จ
 - restart Docker container `odoo` สำเร็จ และหลัง restart container อยู่สถานะ Up, HTTP `/web/login` ตอบ `303`
 - ตรวจฐานข้อมูลหลัง upgrade ได้ `buz_accounting_addon|installed|17.0.3.0.0`
 - ระหว่าง upgrade พบ warning/error เดิมจากโมดูลอื่น โดยเฉพาะ `office_supply_requisition` ไม่ installable แต่ไม่ทำให้การ upgrade `buz_accounting_addon` ล้มเหลว
 - ยังไม่ได้ทำ Browser/PDF/Accounting UAT บน DEV และ full isolated suite ยังมีปัญหาเดิม 1 failed/3 errors คนละส่วนกับบั๊กนี้

### 2026-09-02 — Register Payment Compatibility Fix

 - Fixed the Customer Refund Payment wrapper to provide `cheque_amount` when `account_payment_batch_process` adds this required field to Odoo 17 `account.payment.register`.
 - Removed unsupported `memo` from generated `account.payment` values and retained the standard `ref` reference.
 - Enforced the CV refund amount at register-wizard creation and payment creation to prevent client/RPC tampering.
 - Allowed a subsequent CV when the previous posted payment is already reconciled with the Credit Note but its workflow remains `In Payment` pending bank reconciliation. Draft, Confirmed, Exception, and unreconciled In Payment records remain blocking states.
 - Isolated Odoo 17 suite result: `0 failed, 0 error(s) of 19 tests`. The temporary test database and containers were removed afterward.
 - Browser/PDF/Bank Statement/Accounting UAT and any DEV or Production deployment remain separate acceptance gates.

## Assumptions

- การอนุมัติทำบนเอกสารที่พิมพ์ออกจากระบบ ไม่มีปุ่ม Manager Approve ใน Odoo
- ปุ่ม `Confirm` ยืนยันและล็อกข้อมูล ส่วนการพิมพ์ใช้ปุ่มแยก
- หากข้อมูลในเอกสารอนุมัติผิด ต้องยกเลิก Refund PV และสร้างใหม่
- ไฟล์เอกสารอนุมัติแนบได้แต่ไม่บังคับ
- บัญชี Write-off เลือกได้ในแต่ละ Refund PV แต่ต้องผ่าน domain/validation และนโยบายบริษัท
- ยอดจ่ายจริงเป็นศูนย์ไม่ได้
- Refund PV ใช้ annual date-range sequence แยก `CV/%(year)s/####` ต่อบริษัท เริ่มใหม่ทุกปี เลขที่แก้ได้เฉพาะ Accounting Manager ใน Draft และล็อกหลัง Confirm
- PDF แสดงข้อมูลล่าสุด จึงอาจแตกต่างระหว่างการพิมพ์ก่อนและหลัง Payment แต่ข้อมูลที่ Confirm แล้วเปลี่ยนไม่ได้
- การแก้ไขในอนาคตต้องรักษา uncommitted changes ที่มีอยู่ และจำกัดขอบเขตไว้ใน `buz_accounting_addon`
- งานตามแผนนี้ไม่รวมการ deploy, module upgrade, service restart หรือการเข้าถึงฐานข้อมูลที่มีอยู่
- ก่อนใช้งาน Production ต้องได้รับการยืนยันนโยบายบัญชีและภาษีสำหรับ Write-off จากผู้รับผิดชอบของบริษัท
- คำว่า Odoo 17 ในเอกสารหมายถึงรองรับ Odoo major version 17 โดยไม่ผูกกับ Docker image build หรือ patch release เฉพาะ
