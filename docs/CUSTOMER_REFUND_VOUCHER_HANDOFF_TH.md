# Customer Refund Voucher (CV) — บันทึกการหารือและข้อตกลง

> เอกสารส่งต่องานสำหรับ `buz_accounting_addon`  
> ปรับปรุงล่าสุด: 1 กันยายน 2026  
> สถานะ: ออกแบบและตกลงแนวทางแล้ว ยังไม่ได้เริ่มแก้โค้ดหรือสร้างข้อมูลทดสอบ

## 1. เป้าหมาย

สร้าง workflow สำหรับเลือก **Customer Credit Note** (`account.move` ชนิด `out_refund`) แล้วจ่ายเงินคืนลูกค้าจริง โดยมีเอกสาร **Customer Refund Voucher (CV)** สำหรับพิมพ์ขออนุมัติภายนอกก่อนสร้าง Payment ใน Odoo

หลักการสำคัญ:

- Customer และ Vendor ต้องแยก logic ออกจากกัน
- CV หนึ่งใบอ้างอิง Customer Credit Note หนึ่งใบ
- คืนเงินเต็มยอดคงเหลือของ Credit Note เท่านั้น ไม่รองรับ Partial Refund
- ใช้กลไก Standard Payment/Register/Reconciliation ของ Odoo ไม่สร้าง Journal Entry เอง
- รักษาประวัติเลขเอกสาร Revision และ Payment ที่ถูกยกเลิกครบถ้วน

## 2. สภาพระบบปัจจุบันที่ตรวจพบ

- `account.payment.voucher` ปัจจุบันเป็น AP/Vendor Payment Voucher รองรับ `in_invoice` และ `in_refund`
- Vendor PV มี WHT, Bank Fee, Other Income, หลาย Bill และ logic เฉพาะ Vendor จำนวนมาก
- `account.receipt.voucher` เป็น AR Receipt Voucher ไม่ใช่ workflow จ่ายเงินคืนลูกค้า
- ปัจจุบันยังไม่มี Customer Refund Voucher model/action/wizard ใน local repository
- Standard `account.payment.register` ของ Odoo 17 รองรับ Customer Outbound Payment และ Reconcile Customer Credit Note ได้
- โมดูลเดิมมี Automated Test เฉพาะบางส่วน เช่น Bank Transfer และ Approval Visibility ยังไม่มี test สำหรับ Customer Refund Voucher
- `docker-compose.test.yml` ปัจจุบันกำหนดไว้สำหรับ `agreement_rebate` จึงไม่ควรแก้ทับเพื่อใช้กับงานนี้

## 3. Workflow ที่ตกลง

```text
Customer Credit Note (Posted, Residual > 0)
    → Create Refund Voucher
    → CV Draft
    → กรอกข้อมูลและ Print Revision
    → ขออนุมัติบนกระดาษภายนอกระบบ
    → Confirm
    → Register Refund
    → Customer Outbound Payment (Posted)
    → Reconcile Credit Note
    → CV Registered
```

กติกา workflow:

- สร้าง CV ได้จากปุ่มบนฟอร์ม Customer Credit Note เท่านั้น
- เมนู CV ใช้ค้นหา/ติดตาม ไม่มีปุ่ม `New`
- External approval อยู่นอกระบบ ไม่บังคับแนบเอกสาร ไม่สร้าง Activity และไม่มี approver ในระบบ
- Accounting User คนเดิมสามารถสร้าง Print Confirm และ Register ได้
- Confirm และ Register เป็นสองขั้นตอนแยกกัน
- Confirm ล็อกข้อมูลที่ได้รับอนุมัติ
- Confirmed ที่ยังไม่มี Payment สามารถ Reset to Draft ได้โดย Accounting Manager
- หลังมี Payment แล้ว ห้าม Reset โดยตรง ต้องจัดการ Payment/Reconciliation ก่อน
- CV และ Payment ที่เกี่ยวข้องห้ามลบ ใช้ Cancel เพื่อรักษา audit trail

## 4. สถานะและสิทธิ์การทำงาน

| สถานะ | การแก้ข้อมูล | การพิมพ์ | Action ที่อนุญาต |
|---|---|---|---|
| Draft | แก้ Approval Fields ได้ | ได้เมื่อข้อมูลครบ | Update Amount, Print, Confirm; Manager Cancel |
| Confirmed | อ่านอย่างเดียว | พิมพ์ Approved Revision เดิมได้ | Register Refund; Manager Reset/Cancel |
| Registered | อ่านอย่างเดียว | พิมพ์ Approved Revision เดิมได้ | เปิด Credit Note และ Payments |
| Payment Cancelled | อ่านอย่างเดียว | ห้ามพิมพ์ใหม่ | Manager Reset to Draft หรือ Cancel |
| Cancelled | อ่านอย่างเดียว | ห้ามพิมพ์ใหม่ | เปิดดูประวัติเท่านั้น |

Reset และ Cancel:

- Accounting Manager เท่านั้น
- บังคับกรอกเหตุผลผ่าน Popup
- เก็บเหตุผล ผู้ดำเนินการ และเวลาใน CV/Chatter
- Cancelled เป็นสถานะสิ้นสุด
- หาก Credit Note ยังมียอดคงเหลือ สามารถสร้าง CV ใหม่ด้วยเลขใหม่ได้

## 5. เลขเอกสาร

- ช่วงทดสอบใช้รูปแบบ `CV/2026/0001`
- `CV` หมายถึง Customer Voucher/Customer Refund Voucher ในช่วงทดสอบ
- ออกเลขตั้งแต่สร้าง Draft เพื่อใช้บนเอกสารขออนุมัติ
- เลข CV ต้อง Unique ภายใน Company
- Sequence ต้องรองรับ Company-specific sequence
- Prefix/Starting Number สำหรับใช้งานจริงให้ฝ่ายบัญชีกำหนดภายหลัง
- ไม่เปลี่ยนเลขเอกสารทดสอบหรือเอกสารเก่าย้อนหลัง
- การเปลี่ยน Prefix ภายหลังมีผลกับเลขใหม่เท่านั้น

## 6. โครงสร้าง Model ที่ตกลง

### 6.1 CV Model

Model ใหม่: `buz.customer.refund.voucher`

- แยกจาก `account.payment.voucher` โดยสมบูรณ์
- สืบทอด `mail.thread` และ `mail.activity.mixin`
- หนึ่ง CV อ้างอิง `account.move` ชนิด `out_refund` หนึ่งใบโดยตรง
- ไม่ต้องมี business line model เพราะไม่มีหลาย Credit Note
- หนึ่ง Credit Note มี Active CV ได้หนึ่งใบ
- CV สถานะ Cancelled ไม่นับเป็น Active และอนุญาตให้สร้าง CV ใหม่ได้

### 6.2 Revision Model

Model ใหม่: `buz.customer.refund.voucher.revision`

- เก็บ Snapshot ของทุก Revision ที่พิมพ์สำเร็จ
- Revision record แก้ไขและลบไม่ได้
- CV มี `approved_revision_id` ชี้ไป Revision ที่ Confirm
- Audit Tab แสดง Rev., Printed By/At และสถานะ Approved
- เปิดรายละเอียด Snapshot ได้แบบอ่านอย่างเดียว
- Revision เก่าหรือ Outdated เปิดดูข้อมูลได้ แต่ Accountant พิมพ์ไม่ได้

### 6.3 Payment Relation

- เพิ่ม nullable/indexed backlink บน `account.payment` ไป CV
- CV มี `payment_ids` เพื่อเก็บ Payment ทั้งหมด รวม Payment ที่ Cancelled
- หนึ่ง CV มี Active Payment ได้เพียงหนึ่งรายการ
- Payment เก่าห้ามแก้ Post ซ้ำ หรือลบ
- Payment Reference: `CV <CV Number> / CN <Credit Note Number>`

### 6.4 Credit Note Relation

- ขยาย `account.move` เฉพาะปุ่ม Create/Open CV และ Smart Button/Count
- Source Credit Note ใช้ `ondelete=restrict`
- ปุ่ม Create แสดงเฉพาะ Posted Customer Credit Note ที่มียอดคงเหลือ
- หากมี Active CV ให้เปิดเอกสารเดิมแทนการสร้างซ้ำ

## 7. กลุ่ม Field

### Source Fields — อ่านอย่างเดียว

- CV Number
- Customer
- Customer Code
- Credit Note Number
- Credit Note Date
- Credit Note Total
- Current Credit Note Residual
- Currency
- Company

### Approval Fields — แก้ได้เฉพาะ Draft

- CV Date
- Refund Amount (เต็ม Current Residual และ User แก้ตัวเลขเองไม่ได้)
- Refund Reason — บังคับก่อน Print/Confirm
- Notes — Optional
- Refund Method: Cash / Transfer / Cheque
- Planned Payment Date
- Payment Journal
- Payment Method Line

### Transfer Fields

- Customer Bank Account จาก `res.partner.bank`
- เลือกได้เฉพาะ Commercial Customer เดียวกัน
- Account Holder, Bank และ Account Number
- ห้ามกรอกเลขบัญชีแบบ free text

### Cheque Fields

- Cheque Date
- Cheque Number
- Payee Name — default จาก Customer Name
- Cheque Date เป็นอนาคตได้
- Cheque Number ห้ามซ้ำใน Active CV ภายใต้ Company + Bank Journal เดียวกัน

### Payment/Audit Fields

- Actual Payment Date
- Payment Date Change Reason
- Created/Printed/Confirmed/Registered/Reset/Cancelled By และเวลา
- Reset/Cancel Reason
- Revision และ Approved Revision
- Payment History และ Active Payment

## 8. กติกาวันที่

- `Credit Note Date ≤ CV Date ≤ Planned Payment Date`
- Actual Payment Date ต้องอยู่ระหว่าง CV Date ถึงวันปัจจุบัน
- Actual Date จะก่อนหรือหลัง Planned Date ก็ได้
- หาก Actual Date ต่างจาก Planned Date ต้องระบุเหตุผล
- Cheque Date อนุญาตเป็นวันอนาคตและแยกจาก Actual Payment Date

## 9. Revision และ Approval Snapshot

- เอกสารใหม่ยังไม่มี Revision จนพิมพ์สำเร็จครั้งแรก
- Print ครั้งแรกเป็น Rev. 1
- การแก้ Approval Fields ทำให้ Printed Revision เป็น Outdated แต่ยังไม่เพิ่มเลขทันที
- Print ฉบับใหม่สำเร็จจึงเพิ่ม Revision
- Print ซ้ำโดยข้อมูลไม่เปลี่ยนใช้ Revision และไฟล์เดิม
- Reset to Draft ทำให้ Revision ที่อนุมัติเดิม Outdated; การ Print ครั้งถัดไปเพิ่ม Revision
- Confirm ได้เฉพาะ Revision ล่าสุดที่พิมพ์สำเร็จและข้อมูลยังตรงกัน
- ตอน Confirm แสดง Dialog ให้ User ยืนยันว่าเอกสารกระดาษ Revision นั้นได้รับอนุมัติภายนอกแล้ว

ข้อมูลสำคัญที่ Snapshot:

- Customer/Payee display data
- Bank/Account Holder/Account Number
- Refund Amount และ Currency
- Refund Method
- Journal และ Payment Method Line
- Planned Payment Date
- Cheque data
- Refund Reason และ Notes

## 10. Register Refund และ Accounting Data Flow

ใช้ Custom Register Wizard เป็น façade ครอบ Standard `account.payment.register`

Wizard แสดง:

- CV/Credit Note/Customer/Amount แบบอ่านอย่างเดียว
- Actual Payment Date — แก้ได้
- Payment Date Change Reason เมื่อ Actual ต่างจาก Planned
- สำหรับเงินต่างประเทศ แสดง Effective Rate, Rate Date, Company Currency Amount และประมาณการส่วนต่าง
- ไม่อนุญาตแก้ Journal, Method, Bank, Amount หรือ Exchange Rate

Transaction flow:

1. Lock CV และ Credit Note ป้องกัน Register พร้อมกัน
2. ตรวจ State, Revision, Credit Note, Residual, Company, Journal, Bank, Method, Date และ Currency Rate
3. สร้าง Standard Customer Outbound Payment
4. Post Payment และ Reconcile Credit Note ใน transaction เดียว
5. เชื่อม Payment กลับ CV
6. ตรวจ Payment Journal Entry ถูก Post และ Credit Note Residual เป็นศูนย์ตาม Currency Rounding
7. สำเร็จแล้วจึงเปลี่ยน CV เป็น Registered
8. หากขั้นตอนไหนผิดพลาด ให้ rollback ทั้งหมดและ CV คง Confirmed

หลักบัญชี:

- คืนเงินเต็ม Credit Note Residual
- ไม่หัก Bank Fee จากยอดลูกค้า
- Bank Fee บันทึกเป็นค่าใช้จ่ายแยกตอน Bank Reconciliation
- รองรับ Foreign Currency ตาม Odoo
- Actual Payment Date เป็นวันที่กำหนด Exchange Rate จริง
- หากไม่มี Currency Rate ที่ใช้ได้ ให้บล็อก Register
- ไม่สร้าง Journal Entry หรือ Reconciliation logic เอง

## 11. Payment Cancellation

- Accounting Manager เท่านั้นที่ Reset/Cancel Payment จาก CV
- ห้าม Direct Unreconcile ระหว่าง Payment กับ Credit Note
- ต้อง Cancel Payment ผ่าน workflow มาตรฐาน
- หาก Payment ถูก Bank Reconcile ให้บล็อก และให้ถอน Bank Reconciliation ตามมาตรฐานก่อน
- ไม่ถอน Bank Reconciliation อัตโนมัติจาก CV
- เมื่อ Cancel Payment สำเร็จ CV เปลี่ยนเป็น Payment Cancelled
- Payment เดิมคงอยู่ใน Smart Button และห้ามแก้/Post ซ้ำ/ลบ
- Manager เลือก Reset CV เพื่อสร้าง Payment ใหม่ หรือ Cancel CV

## 12. Security และ Record Rules

ผู้ใช้ CV:

- `account.group_account_user` — Accountant
- `account.group_account_manager` — Accounting Manager
- Billing User (`account.group_account_invoice`) ไม่มีสิทธิ์ CV

| สิทธิ์ | Accountant | Accounting Manager |
|---|---:|---:|
| Read/Create CV | ✓ | ✓ |
| Edit Draft | ✓ | ✓ |
| Print/Confirm/Register | ✓ | ✓ |
| Reset/Cancel CV | ✗ | ✓ |
| Reset/Cancel linked Payment | ✗ | ✓ |
| Delete CV/Payment | ✗ | ✗ |

กฎเพิ่มเติม:

- Accountant ใน Company เดียวกันแก้ Draft ที่ผู้อื่นสร้างได้
- Record Rule จำกัดตาม `company_ids`
- Credit Note, Journal, Bank และ Payment ต้องอยู่ Company เดียวกัน
- Protected Fields เขียนผ่าน Import/RPC โดยตรงไม่ได้
- ปิด New, Duplicate, Import และ Delete จาก UI
- ตรวจสิทธิ์ใน Python ทุก Action ไม่พึ่งการซ่อนปุ่ม
- ไม่ใช้ `sudo()` เพื่อข้ามสิทธิ์บัญชี งวดล็อก หรือ Company
- Chatter ไม่แสดงเลขบัญชีเต็มในข้อความ log

## 13. Form และ List UI

### Form

- Labels และปุ่มใช้ภาษาอังกฤษตาม Odoo เดิม
- หน้าเดียวสำหรับ Source/Refund/Payment และมี Audit Tab
- Header Status Bar: Draft → Confirmed → Registered → Payment Cancelled → Cancelled
- Draft ยังไม่ได้พิมพ์ล่าสุด: ปุ่ม Print เป็น Primary
- Draft พิมพ์ล่าสุดแล้ว: ปุ่ม Confirm เป็น Primary
- Confirmed: ปุ่ม Register Refund เป็น Primary
- Banner แจ้ง Source Invalid, Residual Mismatch, Payment Cancelled, Revision Outdated และ Overdue
- Banner มี Action ที่เกี่ยวข้อง เช่น Update Refund Amount/Open Credit Note
- เปลี่ยน Refund Method ให้ล้างข้อมูลของ Method เดิมและ invalidate Revision
- Payment Method Line เลือกอัตโนมัติเมื่อ Journal มี outbound method เดียว; แสดงช่องเมื่อมีหลายตัว
- Smart Buttons: Credit Note และ Payments

### List

- เมนู `Customer Refund Vouchers` อยู่ใต้ Receivables
- ไม่มีปุ่ม New
- แสดงทั้งหมดรวม Cancelled เรียงล่าสุดก่อน
- คอลัมน์หลัก: CV No., CV Date, Customer, Credit Note, Refund Amount, Refund Method, Planned Date, Actual Date, Status
- Created By และ Company เป็น Optional Columns
- ค้นหาจาก CV No., Customer, Customer Code และ Credit Note No.
- Filters: State, Method, My Vouchers, Planned Today, Overdue
- Group By: State, Customer, Method, Company, Planned Month
- Confirmed ที่เลย Planned Date แสดงแถวสีแดง
- Payment Cancelled แสดง Badge/แถวเตือนสีแดง
- ไม่มี Bulk Confirm/Register/Cancel
- รองรับ Batch Print เท่านั้น
- Batch Print มีใบใดไม่ผ่าน ให้ยกเลิกทั้งชุดและแจ้งปัญหาทุก CV

## 14. PDF/QWeb

- Report title: `ใบสำคัญจ่ายคืนลูกค้า / Customer Refund Voucher`
- Standalone QWeb Template ไม่ inherit หรือแก้ Vendor PV Template
- ใช้ `web.external_layout` และ A4 Paper Format เดียวกับ PV
- หนึ่งหน้า A4 ไม่ย่อ Font อัตโนมัติ
- Labels/หัวตารางเป็นอังกฤษ ยกเว้นหัวเอกสารสองภาษา
- Customer แสดง Code และ Name เท่านั้น
- Refund Reason สูงสุด 300 ตัวอักษร
- Notes สูงสุด 500 ตัวอักษร
- แสดง CV No., Revision, CV Date, Credit Note, Refund Amount, Currency, Amount in Thai Words, Payment Details, Accounting Preview, Notes และลายเซ็น
- ช่องลายเซ็นเหมือน PV เดิม 5 ช่อง: Prepare By, Checked (1), Checked (2), Approved (1), Approved (2)
- ไม่มี WHT, Bank Fee หรือรายการหักแบบ Vendor
- PDF ไม่แสดง Status และไม่มี Watermark
- Payment Cancelled/Cancelled ห้ามพิมพ์ใหม่
- Accounting Preview ใช้ Planned Payment Date และคงเหมือน Revision ที่อนุมัติแม้หลัง Register
- รายการจริงดูจาก Payment/Journal Entry
- ชื่อไฟล์: `Customer Refund Voucher - <CV Number> - Rev <n>.pdf`

### การเก็บ PDF

- เก็บไฟล์ PDF จริงของทุก Revision แบบ immutable
- Reprint ใช้ไฟล์เดิม ไม่ render ใหม่ตาม Template เวอร์ชันใหม่
- Accountant ดาวน์โหลดได้เฉพาะ Revision ปัจจุบันที่สถานะอนุญาต
- Revision เก่า/Outdated/Cancelled ดาวน์โหลดได้เฉพาะ Accounting Manager
- Accountant ยังดู Snapshot และ Audit metadata ของ Revision เก่าได้
- Batch Print สร้าง/ใช้ PDF ราย Revision แล้วรวมด้วย `odoo.tools.pdf.merge_pdf()`

## 15. Validation และข้อความ Error

- ข้อความเป็นภาษาไทยและคงชื่อ Field/Status ภาษาอังกฤษ
- Draft Save ข้อมูลไม่ครบได้
- Print/Confirm รวมทุกปัญหาในข้อความเดียว
- ข้อความระบุ CV/Credit Note สาเหตุ และวิธีแก้
- ไม่แสดง traceback แก่ User

ตรวจซ้ำในแต่ละจุด:

- Create: Posted `out_refund`, Residual > 0, Company, Active CV
- Print: Reason, Amount, Method, Date, Journal, Payment Method Line และ Method-specific fields
- Confirm: Printed Revision ล่าสุด, Source/Residual/Master Data ยังตรง
- Register: ตรวจทุกอย่างซ้ำ รวม Actual Date, Rate, Active Payment และ Locked Period
- Reset/Cancel: Manager และ Reason

กรณีพิเศษ:

- Residual เปลี่ยนใน Draft: แสดงยอดเดิม/ปัจจุบัน บล็อก Print/Confirm และให้กด Update Refund Amount
- Residual เปลี่ยนหลัง Confirm: บล็อก Register และต้อง Manager Reset/Reprint
- Credit Note ถูก Reset/Cancel: บล็อก Print/Confirm/Register
- Bank Account หรือข้อมูลปลายทางเปลี่ยนหลัง Confirm: บล็อก Register และต้อง Reset/Reprint
- Register ล้มเหลว: rollback และคง Confirmed

## 16. Backward Compatibility และผลกระทบฐานข้อมูล

- เพิ่ม feature ใน `buz_accounting_addon` เดิม
- ห้ามเปลี่ยน behavior ของ Vendor PV/Receipt Voucher
- เพิ่มไฟล์ใหม่เป็นหลัก และขยาย Model มาตรฐานแบบ conditional
- Global hook ต้องเรียก `super()` ทันทีเมื่อ record ไม่มี CV backlink
- ไม่ refactor shared helper/report ของ Voucher เดิมในงานนี้
- ไม่มี migration/backfill/recompute business records เดิม
- ไม่เพิ่ม Python dependency ใหม่
- ใช้ PDF merge helper ที่มากับ Odoo 17

โครงสร้างฐานข้อมูลที่คาดว่าจะเพิ่ม:

- CV table
- Revision table
- Transient Wizard tables
- Nullable/indexed CV backlink บน `account.payment`
- Sequence, Actions, Views, ACL และ Record Rules ใหม่
- Partial Unique Index สำหรับ Active CV ต่อ Credit Note
- Unique constraints สำหรับ Company + CV Number, Voucher + Revision และ Active Cheque Number

## 17. ขอบเขตการทำงานที่พักไว้ก่อน

เมื่อเริ่มลงมือจริง ขอบเขตรอบแรกที่ตกลงไว้คือ:

- แก้เฉพาะ local repository
- ทดสอบด้วย Docker Desktop ก่อน
- ยังไม่ Deploy/Upgrade/Restart MOG_DEV หรือ Production
- ใช้ Docker Compose และฐานข้อมูลแยกสำหรับ `buz_accounting_addon`
- ทดสอบ Automated Test และ Browser/PDF local
- ใช้ Seed Script เฉพาะ Docker ไม่โหลดผ่าน manifest ไป DEV/Production
- Regression ทั้ง Automated และ Browser smoke สำหรับ Vendor PV/Receipt Voucher

หมายเหตุ: ให้กลับมาทบทวนขอบเขตนี้อีกครั้งก่อนเริ่มแก้โค้ดจริง

## 18. แนวทาง UAT ที่ตกลงไว้สำหรับภายหลัง

- ใช้ Credit Note ทดสอบโดยเฉพาะ ไม่ใช้เอกสารใช้งานจริง
- ทดสอบ Cash, Transfer และ Cheque อย่างละกรณี
- เพิ่ม Foreign Currency Transfer โดย Planned Date ต่างจาก Actual Date
- ทดสอบ Payment Cancelled → Reset → Register ใหม่ครบวงจร
- ใช้ทั้ง Accounting User และ Accounting Manager
- Manual UAT เฉพาะจุดเสี่ยง + Automated Test ครบ
- เก็บ Checklist พร้อมเลข Credit Note, CV, Payment, Journal Entry และ PDF

คาดว่าใช้ Credit Note ทดสอบอย่างน้อย 5 ใบ:

1. Cash — THB
2. Transfer — THB
3. Cheque — THB
4. Transfer — Foreign Currency
5. Residual เปลี่ยนหลัง Confirm

## 19. หัวข้อที่ยังไม่ได้คุยจบ/ควรคุยต่อ

1. Automated Test Architecture และ Test Matrix ระดับ Model/Transaction
2. รายการไฟล์และลำดับ implementation ที่แน่นอน
3. วิธีจำลอง upgrade path จาก `17.0.2.1.0` พร้อมข้อมูล Vendor PV/RV เดิม
4. การตั้งค่า Prefix/Starting Number จริงของแต่ละ Company ก่อน Production
5. เกณฑ์ผ่าน local Docker รอบสุดท้ายก่อนขออนุญาตขึ้น MOG_DEV
6. การตรวจ visual PDF ที่ข้อมูลยาวสุดและทุก Payment Method

## 20. ข้อห้ามสำหรับผู้รับช่วงงาน

- อย่านำ Customer Refund ไปเพิ่มเงื่อนไขใน Vendor PV model เดิม
- อย่าสร้าง Journal Entry/Reconciliation เองแทน Standard Odoo Register Payment
- อย่าปรับ Template Vendor PV เพื่อทำ CV
- อย่าเปลี่ยนหรือลบเลข CV/Revision/Payment เก่าย้อนหลัง
- อย่าข้าม Company, ACL, Locked Period หรือ Currency Rate ด้วย `sudo()`
- อย่าทดสอบบน MOG_DEV/Production หรือสร้าง business data โดยไม่ได้ยืนยันขอบเขตอีกครั้ง
- อย่าถือว่า Automated Test ผ่านแล้วเท่ากับ Browser/PDF/Accounting UAT ผ่าน

