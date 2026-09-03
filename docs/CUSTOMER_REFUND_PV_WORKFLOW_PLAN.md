# Customer Refund PV — Workflow Plan (ถึงขั้น Register Refund Payment แยก)

## สรุป Flow ปัจจุบัน
```
Posted Customer Credit Note (out_refund)
→ Create Refund PV (Draft)
→ กรอกเลข Refund PV + Refund Amount (ยอดที่จะจ่ายจริง)
→ Confirm → Posted (ล็อกเอกสาร)
→ Print Refund PV (PDF แยกจาก Vendor PV)
→ Refund PV: Register Refund Payment (ปุ่มใหม่บน Refund PV, ใช้ refund_amount 4000)
→ Create Payment → Reconcile Payment ↔ Credit Note
→ [Phase ถัดไป] WHT / Bank Fee / ติดตามยอดจ่ายจริง
```

เอกสารเป็นโมเดลแยก `buz.customer.refund.pv` / `buz.customer.refund.pv.line` ใช้ layout เดียวกับ Vendor PV แต่ไม่กระทบ Vendor PV เดิม ปุ่ม `Register Payment` เดิมบน Credit Note ยังใช้ยอดเต็มมาตรฐาน (4990) ไม่ส่ง `refund_amount`

## สิ่งที่แก้ไขจริง

### 1. Rename View (Phase 1)
- `buz_accounting_addon/views/buz_customer_refund_pv_views.xml` → `buz_accounting_addon/views/customer_refund_pv_views.xml`
- `buz_accounting_addon/__manifest__.py:66` อ้างอิงชื่อใหม่, ลบไฟล์เก่าบน DEV

### 2. โมเดลหลัก `buz_accounting_addon/models/customer_refund_pv.py`
- **Header `BuzCustomerRefundPv:6`**
  - `name:13` เปลี่ยน `readonly=True, default="/"` → `copy=False, index=True` รองรับกรอกเอง + auto `next_by_code("buz.customer.refund.pv")` เมื่อว่าง ใน `create:81` / `write:99` (Sequence สร้างเฉพาะ Header)
  - `refund_amount:63` เพิ่ม `fields.Monetary(string="Refund Amount")` สำหรับยอดจ่ายจริงที่บัญชีระบุ รองรับบางส่วนเช่น `4,990 → 3,000/4,000`
  - `line_ids:60` One2many `buz.customer.refund.pv.line`
  - `amount_total_gross/wht/net:66` คงสูตรเดิม `sum(line)` ไม่แก้
  - `payment_ids:72` `Many2many account.payment buz_customer_refund_pv_payment_rel` + `payment_count:73` `compute _compute_payment_count:185` (นับรวม cancel สำหรับประวัติ) + `has_active_payment:74` `compute _compute_has_active_payment:200` `any(p.state!='cancel')` สำหรับเปิดปุ่มใหม่ + `action_view_payments:189` + `action_register_refund_payment:204`
- **Line `BuzCustomerRefundPvLine:351`**
  - ไม่มี field `name` / `date`
  - fields เดิม `pv_id:355, move_id:357 (domain out_refund,posted), amount_to_pay_gross:367, buz_wht_tax_id, wht_base_amount, wht_rate, wht_amount, amount_to_pay_net:376`
  - `onchange move_id:381` เติม Gross/WHT Base จาก `amount_residual_signed/amount_untaxed_signed`
  - `create:409` ลบโค้ดผิดที่ตั้ง `vals["name"]=next_by_code` บน Line (ต้นเหตุ `Invalid field 'name' on model 'buz.customer.refund.pv.line'`) เหลือแค่ตรวจ `if pv.state=="posted" raise` + `write:418/unlink:423` ล็อกหลัง Posted
- **Confirm `action_confirm:114`**
  - ตรวจ `state draft → name จำเป็น + ตรวจซ้ำ search name, partner, date, credit_note out_refund+posted, line_ids, refund_amount>0, gross/net>0, ทุกยอด <= residual (amount_residual_signed)` รวมถึง `refund_amount - residual >1e-6`
  - ตรวจ Partial: `other_posted = search([credit_note_id, posted, id!=current]) total_other = sum(refund_amount)` `total_other + refund_amount <= cn_total(4990)` กันยอดรวมหลาย PV เกิน CN, `cancel` PV ไม่นับ (state!='posted')
  - `write({"state":"posted"})` + `message_post` ไม่สร้าง `account.payment` ไม่ reconcile (Confirm ยังไม่สร้าง Payment)
  - `write:101` ล็อก `protected {name, partner_id, credit_note_id, date, payment_type, destination_journal_id, bank_free_dis, other_income_dis, line_ids, note, refund_amount}` หลัง Posted, `_check_name_unique:90` กันซ้ำ
- **Register Refund Payment `action_register_refund_payment:204` (ปุ่มใหม่บน Refund PV)**
  - ตรวจ `state posted, credit_note_id มี, move_type out_refund, credit_note posted, refund_amount>0, not already registered (has_active_payment), refund_amount <= residual` กัน `Draft, ไม่มี CN, CN ไม่ใช่ out_refund, CN ไม่ posted, ยอด 0/ลบ, ยอดเกิน, Register ซ้ำ`
  - `with_context(active_model account.move, active_ids [credit_note.id], buz_customer_refund_pv_id, force_amount=refund_amount, default_journal/date/method)` เรียก `credit_note.with_context(ctx).action_register_payment()` เปิด `account.payment.register` ยอดเริ่มต้น `refund_amount` (เช่น 4000 ไม่ใช่ 4990)
  - Reconcile กับ Credit Note ที่ผูกเท่านั้น ผ่านกลไกมาตรฐาน Odoo
- **Preview `get_preview_moves:193`**
  - ถ้ามี `refund_amount>0` ใช้เป็น `total_gross` (`total_net = gross - wht`) รองรับพิมพ์บางส่วน, `other_income =0.0` ไม่ใช้ Other Income คำนวณยอดคืน, `total_disbursement = net + bank_fee`

### 3. Account Move `buz_accounting_addon/models/account_move.py:29`
- `action_create_customer_refund_pv:29` ตรวจ `out_refund+posted` สร้าง PV `vals {partner_id, company_id, credit_note_id, date}` แล้ว `write line_ids Command.create({move_id, amount_to_pay_gross:residual, wht_base_amount:untaxed})` ใช้ field จริงเท่านั้น
- `customer_refund_pv_count:10` + smart button `Refund PVs`
- **ลบ `action_register_payment` ที่เคยดักบน Credit Note** — ปุ่ม `Register Payment` เดิมบน Credit Note กลับทำงานมาตรฐาน ใช้ยอดคงเหลือเต็มตาม Odoo ไม่ส่ง `force_amount`/`buz_customer_refund_pv_id` ไม่กระทบ Invoice/Vendor Bill

### 4. Payment Link `buz_accounting_addon/models/account_payment.py:14` + `account_payment_register.py:13`
- `account.payment:14` เพิ่ม `buz_customer_refund_pv_id Many2one buz.customer.refund.pv`
- `account.payment.register:13` `_compute_amount` รองรับ `force_amount` (ตั้งเฉพาะจากปุ่มใหม่บน Refund PV จึงใช้ `4000` ไม่ใช่ `4990` เต็ม CN) → `_create_payments:22` ก่อน `super` ตรวจ `buz_customer_refund_pv_id` แล้ว `if abs(wizard.amount - refund_amount)>1e-6 raise must equal` และ `wizard.amount - residual >1e-6` กันยอดเกิน และกันแก้ Wizard ต่างจาก Refund Amount, หลัง `super` ตรวจ `buz_customer_refund_pv_id` → `refund_pv.write payment_ids [(4)]` + `payments.write buz_customer_refund_pv_id` + `message_post` + log ไม่ใช้ WHT/Bank Fee ใน Phase นี้, Reconcile ใช้กลไกมาตรฐาน, `has_active_payment` ทำให้หลัง Payment `cancel` ปุ่ม Register กลับมาได้ Payment เดิมยังอยู่ในประวัติ `payment_count` รวม `cancel`

### 5. View `buz_accounting_addon/views/customer_refund_pv_views.xml`
- Header `38` ปุ่ม `Confirm invisible draft` + `Print Payment Voucher %(action_report_customer_refund_pv)d invisible posted` + **`Register Refund Payment action_register_refund_payment invisible state!='posted' or not credit_note_id or not refund_amount or has_active_payment`** (ใช้ `has_active_payment` แทน `payment_count` เพื่อให้หลัง Cancel กลับมากดใหม่ได้) + `has_active_payment invisible 1` หลัง header เพื่อให้ modifier ใช้ได้
- Title `54` `name` `placeholder="Enter Refund PV Number" readonly draft required=1`
- Header_right `66` เพิ่ม `refund_amount widget monetary readonly draft required=1`
- `oe_button_box:44` คง `Credit Note` + `Net Amount` เพิ่ม `action_view_payments:46` `icon fa-credit-card invisible payment_count==0` `payment_count` นับรวม `cancel` สำหรับประวัติ
- `line_ids:81` `readonly draft` tree แสดง `move_id(domain out_refund), amount_to_pay_gross, wht_base_amount, buz_wht_tax_id, wht_amount, amount_to_pay_net`
- **Wizard View** `views/account_payment_register_inherit_views.xml:4` `inherit_id account.view_account_payment_register_form` `xpath //field[@name='amount'] readonly context.get('buz_customer_refund_pv_id')` ทำให้ยอดใน Wizard แก้ไม่ได้เฉพาะเมื่อเรียกจากปุ่มใหม่

### 6. Report แยกจาก Vendor PV
- `buz_accounting_addon/reports/customer_refund_pv_report.xml:4` `paperformat_customer_refund_pv` A4 `19` `action_report_customer_refund_pv` `model buz.customer.refund.pv` `report_name buz_accounting_addon.report_customer_refund_pv` `binding_model_id model_buz_customer_refund_pv`
- `buz_accounting_addon/reports/customer_refund_pv_template.xml:4` `id report_customer_refund_pv` โคลน `payment_voucher_template.xml` เปลี่ยน `VOUCHER NO. = o.name:66`, `เลขที่เอกสาร = line.move_id.name:105`, `จำนวนเงิน = o.refund_amount:112,121`, `payment_main_amount:128` `(o.refund_amount or gross) - wht - bank_fee` ตัด `other_income`
- Vendor `payment_voucher_report/template` ไม่แก้

### 7. Manifest `buz_accounting_addon/__manifest__.py:61`
- เพิ่ม `reports/customer_refund_pv_report.xml`, `reports/customer_refund_pv_template.xml` ต่อหลัง `payment_voucher` ก่อน `payment_transfer`, เพิ่ม `views/account_payment_register_inherit_views.xml`

## ผลการ Upgrade และ Restart DEV (ล่าสุด)
- **Upload ล่าสุด 2026-09-03 09:19:** `scp -r -i dev_server_ed25519` `SCP_EXIT 0`, ตรวจ `models/customer_refund_pv.py` 24114→24700 bytes (เพิ่ม `has_active_payment`), `views/customer_refund_pv_views.xml` 7350 bytes (เพิ่ม `has_active_payment` invisible), `views/account_payment_register_inherit_views.xml` 710 bytes, `grep next_by_code` พบ 2 จุดใน PV เท่านั้น Line ไม่มี, `grep action_register_refund_payment` พบใน PV `204`, `grep Payment amount must equal` พบใน `account_payment_register.py`
- **Upgrade 2026-09-03 09:19:** `docker exec odoo odoo -d MOG_DEV -u buz_accounting_addon --stop-after-init --no-http` สำเร็จ `Modules loaded.` `Registry loaded in 31.221s` `Stopping gracefully` (ก่อนหน้าเคย `ParseError has_active_payment must be present` แก้ด้วยเพิ่ม `field invisible 1`)
- **Upgrade ก่อนหน้า 2026-09-03 08:45/08:34/08:15/07:52:** `36.925s` / `40.623s` / `34.553s` / `30.789s` (เคย `SerializationFailure` ต้อง retry)
- **Restart:** `docker restart odoo` → `odoo Up 14s` (ล่าสุด 09:19), `odoo_dev Up 31h`, `postgres Up 3 days (healthy)`
- **Verify DB:** `psql MOG_DEV: select name, state from ir_module_module where name='buz_accounting_addon'` → `installed`, `select name from ir_act_report_xml where report_name like '%customer_refund%'` → `Customer Refund Payment Voucher`, `grep has_active_payment` บน DEV พบ

## Error / ข้อจำกัดที่ยังเหลือ
- **Upgrade concurrent** ยังมีโอกาส `SerializationFailure` เมื่อมี request พร้อมกัน — แก้ด้วย retry
- **Warning คงเหลือ** `office_supply_requisition: not installable, skipped`, `fields.states is no longer supported`, `Two fields ... have same label` — ไม่กระทบ Refund PV
- **เลขซ้ำ** ใช้ `@api.constrains` + ตรวจใน `action_confirm` ไม่ใช้ `_sql_constraints unique(name)` เพื่อให้หลาย Draft ว่าง `name=False` ได้
- **Other Income** ยังมี field `other_income_dis` ในโมเดล/ฟอร์มแต่ไม่ใช้คำนวณยอดคืน (report `payment_main_amount` และ `get_preview_moves` ตั้ง `other_income=0.0`)
- **Register แยก** ปุ่มใหม่ `Register Refund Payment` บน Refund PV ใช้ `refund_amount` (เช่น 4000) ส่วนปุ่มเดิมบน Credit Note ใช้ยอดเต็ม CN (4990) ยังแยกกันชัดเจน ไม่กระทบ Invoice/Vendor Bill, ทดสอบ `Draft, ยอดเกิน, ไม่มี CN, Register ซ้ำ` block ครบ, Wizard `amount` ล็อก `readonly` เมื่อมาจาก PV, หลัง `Cancel` Payment กลับมา Register ใหม่ได้

## ขอบเขต Phase นี้ vs ถัดไป
- **Phase นี้ทำแล้ว:** `Create → Confirm → Print → Register Refund Payment (ปุ่มใหม่บน Refund PV ใช้ refund_amount) → Create Payment → Reconcile` เก็บ `payment_ids/payment_count (รวม cancel) + has_active_payment` บน Refund PV, Smart Button `Payment` บน Refund PV, `Credit Note ↔ Refund PVs ↔ Payment` ครบ, ปุ่มเดิมบน Credit Note ยังมาตรฐาน, รองรับหลาย PV ต่อ CN ตรวจยอดรวมไม่เกิน CN
- **ยังอยู่นอก Phase นี้:** ไม่ใช้ `WHT` / `Bank Fee` คำนวณยอดคืน (แม้มี field ยังไม่ผูก), ไม่สร้าง `account.payment` อัตโนมัติตอน Confirm, ไม่แก้ Vendor PV, ไม่รวม `WHT Certificate`, `Bank Transfer`

Flow หลัง Fix ใช้งานได้ครบ `Credit Note → Create → Confirm → Print → Register Refund Payment (4000)` → Payment → Reconcile พร้อมขออนุมัติแล้ว
