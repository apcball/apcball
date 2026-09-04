# Customer Refund PV — Workflow Plan (ถึงขั้น Register Refund Payment แยก)

## สรุป Flow ปัจจุบัน (อัปเดต 2026-09-04 — แก้เลข Payment ก่อน Post)
```
Posted Customer Credit Note (out_refund)
→ Create Refund PV (Draft)
→ กรอกเลข Refund PV (เช่น PV2600300) + Refund Amount (ยอดที่จะจ่ายจริง 4000/4990)
→ Confirm → Posted (ล็อกเอกสาร)
→ Print Refund PV (PDF แยกจาก Vendor PV)
→ Refund PV: Register Refund Payment (ปุ่มใหม่บน Refund PV, ใช้ refund_amount 4000)
→ Create Payment (Draft) → แก้เลข Payment/Journal (เช่น PBNK11/2026/00009, เลขเดียวกับ account.move.name) → Post Payment → Reconcile Payment ↔ Credit Note
→ [Phase ถัดไป] WHT / Bank Fee / ติดตามยอดจ่ายจริง
```
เลขแยกชัดเจน: `Refund PV (PV2600300)` ≠ `Payment/Journal (PBNK11/2026/00009)` ≠ `Credit Note (RINV/2026/00052)` — Payment สร้างเป็น Draft เพื่อให้แก้เลขได้ก่อน Post, Post แล้วล็อกเลขและ Reconcile

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
- **Register Refund Payment `action_register_refund_payment:219` (ปุ่มใหม่บน Refund PV)**
  - ตรวจ `state posted, credit_note_id มี, move_type out_refund, credit_note posted, refund_amount>0, not already registered (has_active_payment), refund_amount <= residual` กัน `Draft, ไม่มี CN, CN ไม่ใช่ out_refund, CN ไม่ posted, ยอด 0/ลบ, ยอดเกิน, Register ซ้ำ`
  - `ctx = {active_model account.move, active_ids [credit_note.id], buz_customer_refund_pv_id, force_amount=refund_amount, batch=False, default_journal/date/method}` — `batch=False` บังคับ standard flow ไม่ให้ `account_payment_batch_process` ตีความยอดเต็ม CN, เรียก `credit_note.with_context(ctx).action_register_payment()` เปิด `account.payment.register` ยอดเริ่มต้น `refund_amount` (เช่น 4000 ไม่ใช่ 4990)
  - **Context Merge `260`**: `action_register_payment()` สร้าง context ใหม่ทับ `buz_customer_refund_pv_id/force_amount` จึงต้อง `action_context.update(ctx)` ใส่กลับเข้า `action['context']` ก่อน return เพื่อไม่ให้ยอดหลุดเมื่อ Odoo สร้าง wizard
  - Reconcile กับ Credit Note ที่ผูกเท่านั้น ผ่านกลไกมาตรฐาน Odoo
- **Preview `get_preview_moves:193`**
  - ถ้ามี `refund_amount>0` ใช้เป็น `total_gross` (`total_net = gross - wht`) รองรับพิมพ์บางส่วน, `other_income =0.0` ไม่ใช้ Other Income คำนวณยอดคืน, `total_disbursement = net + bank_fee`

### 3. Account Move `buz_accounting_addon/models/account_move.py:29`
- `action_create_customer_refund_pv:29` ตรวจ `out_refund+posted` สร้าง PV `vals {partner_id, company_id, credit_note_id, date}` แล้ว `write line_ids Command.create({move_id, amount_to_pay_gross:residual, wht_base_amount:untaxed})` ใช้ field จริงเท่านั้น
- `customer_refund_pv_count:10` + smart button `Refund PVs`
- **ลบ `action_register_payment` ที่เคยดักบน Credit Note** — ปุ่ม `Register Payment` เดิมบน Credit Note กลับทำงานมาตรฐาน ใช้ยอดคงเหลือเต็มตาม Odoo ไม่ส่ง `force_amount`/`buz_customer_refund_pv_id` ไม่กระทบ Invoice/Vendor Bill

### 4. Payment Link `buz_accounting_addon/models/account_payment.py:14` + `account_payment_register.py:13`
- `account.payment:14` เพิ่ม `buz_customer_refund_pv_id Many2one buz.customer.refund.pv`
- `account.payment.register:13`
  - `_compute_amount:14` ถ้ามี `buz_customer_refund_pv_id` ใน context จะ `browse` PV แล้วตั้ง `wizard.amount = refund_pv.refund_amount` โดยตรง (ไม่เชื่อ `force_amount` ที่ผู้ใช้อาจแก้) — กัน tamper, ถ้าไม่มี PV จึง fallback ใช้ `force_amount` เดิมของ Payment Voucher/WHT
  - `make_payments:26` ดักเฉพาะ Refund PV (`buz_customer_refund_pv_id` มี) → `invoice_payments = Command.clear()` กัน `account_payment_batch_process` สร้าง batch allocation ผิดยอด แล้ว `with_context(batch=False).action_create_payments()` ใช้ standard reconciliation; ถ้าไม่มี PV ให้ `super().make_payments()` มาตรฐาน ไม่กระทบ flow อื่น
  - `_create_payments:38` ก่อน `super` ตรวจเข้ม: `PV exists?`, `state posted?`, `has_active_payment?` (กัน Register ซ้ำ), `credit_note state posted & out_refund?`, `residual = abs(amount_residual)` (ใช้ `compare_amounts` ให้รองรับ currency precision), วน `wizard` ตรวจ `amount>0`, `amount == refund_amount` (must equal), `amount <= residual` กันยอดเกิน/tamper, หลัง `super` → `refund_pv.write payment_ids [(4)]` + `payments.write buz_customer_refund_pv_id` + `message_post` + log ไม่ใช้ WHT/Bank Fee ใน Phase นี้, Reconcile ใช้กลไกมาตรฐาน, `has_active_payment` ทำให้หลัง Payment `cancel` ปุ่ม Register กลับมาได้ Payment เดิมยังอยู่ในประวัติ `payment_count` รวม `cancel`

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
- `depends` เพิ่ม `account_payment_batch_process` เพื่อให้ `make_payments` ของ batch ถูก override ได้ และกัน batch สร้างยอดเต็ม CN ทับ `refund_amount`

### 8. Tests `buz_accounting_addon/tests/test_customer_refund_payment.py`
- `@tagged post_install -at_install` `AccountTestInvoicingCommon` สร้าง CN `out_refund 4990` + PV `posted refund_amount 4000`
- `test_refund_action_forces_approved_amount` ตรวจ `action context batch==False`, `buz_customer_refund_pv_id` ตรง, `wizard.amount==4000`
- `test_standard_credit_note_action_remains_unchanged` ตรวจปุ่มเดิมบน CN ไม่มี `buz_customer_refund_pv_id` และ `wizard.amount==4990` มาตรฐาน
- `test_refund_payment_is_partial_linked_and_reconciled` `wizard.make_payments()` → `payment_ids 1 record amount 4000 buz_customer_refund_pv_id ตรง` + `credit_note.amount_residual==990` (4990-4000) แสดง reconcile สำเร็จ
- `test_server_rejects_tampered_amount` แก้ `wizard.amount=4990` แล้ว `_create_payments` ต้อง `raise UserError` (must equal)

### 9. ตรวจสอบต้นทาง SO/Invoice ก่อน Confirm/Register (เพิ่ม 2026-09-04 — แผนตรวจสอบ SO และ Invoice ก่อน Customer Refund PV)
- **Spec:** `SO → Invoice Paid → Credit Note → Refund PV → Confirm → Print → Register Payment` ต้องตรวจว่า CN มี `invoice_line_ids.sale_line_ids` เชื่อม SO และ Invoice ต้นทาง `out_invoice` ทุกใบ `paid+residual 0` แล้วเท่านั้น ไม่ใช้ `invoice_origin` ข้อความ
- **โมเดล `buz_accounting_addon/models/customer_refund_pv.py:76`**
  - เพิ่ม fields read-only `source_sale_order_ids:Many2many sale.order compute`, `source_sale_order_count`, `source_invoice_ids:Many2many account.move compute`, `source_invoice_count`, `source_status:Char compute`, `source_status_is_paid:Boolean` — คำนวณจาก `CN.invoice_line_ids.sale_line_ids` (Odoo 17 `display_type='product'` ต้อง `mapped` ตรง ไม่ใช้ `not display_type`) แล้ว `search account.move.line sale_line_ids in (...) + move_type out_invoice` หา Invoice ต้นทางทุกใบ (handle หลาย Invoice)
  - `+float_is_zero:3` ใช้เทียบ `amount_residual` ด้วย `currency.rounding`
  - `_get_source_sale_lines:218` / `_get_source_invoices:234` / `_compute_source_documents:251` สร้างข้อมูลอ้างอิง read-only + สถานะ `Source Invoice Paid` / `Invoice ยังไม่ Paid: INV...` / `ไม่พบ SO ต้นทาง` / `ไม่พบ Invoice ต้นทาง` / `No Credit Note`
  - `_check_source_invoices_paid:310` เมธอดกลาง: ถ้าไม่มี CN/ไม่ใช่ out_refund/ไม่ posted → block, ไม่มี `sale_line_ids` → `ไม่พบ SO ต้นทาง`, ไม่มี Invoice ที่แชร์ sale_line → `ไม่พบ Invoice ต้นทาง`, มี Invoice แต่ไม่ครบเงื่อนไข `posted + out_invoice + payment_state=paid + residual 0` → `Invoice ยังไม่ Paid: INV... (state=..., payment_state=..., residual=...)` และหยุด
  - `action_confirm:128` และ `action_register_refund_payment:363` เรียก `_check_source_invoices_paid()` ก่อนดำเนินการต่อ (ตรวจซ้ำตอน Register เพื่อกัน state เปลี่ยนหลัง Confirm)
  - `action_view_source_invoices` / `action_view_source_sale_orders` เปิด smart button ไป Invoice/SO ต้นทาง (ไม่ให้ผู้ใช้เลือกเอกสารเอง)
- **View `buz_accounting_addon/views/customer_refund_pv_views.xml:46`**
  - `button_box` เพิ่ม `action_view_source_sale_orders` (`source_sale_order_count`) `icon fa-shopping-cart` + `action_view_source_invoices` (`source_invoice_count`) `icon fa-file-text`
  - เพิ่ม group `Source Documents (Auto-detected, Readonly) invisible not credit_note_id` แสดง `source_sale_order_ids/source_invoice_ids` `many2many_tags readonly no_create` + `source_status` placeholder `Source Invoice Paid / Invoice ยังไม่ Paid / ไม่พบ Invoice ต้นทาง`
  - Tree เพิ่ม `source_status optional hide`
- **Payment Register `buz_accounting_addon/models/account_payment_register.py:63`**
  - หลังตรวจ `amount == refund_amount` และ `amount <= residual` เพิ่ม `refund_pv._check_source_invoices_paid()` ก่อน `super()._create_payments()` เพื่อบล็อกถ้า Invoice กลับเป็นไม่ paid หลัง Confirm (เช่น `In Payment`/`Outstanding Payments` → ยังไม่ถือว่า paid)
- **Manifest `buz_accounting_addon/__manifest__.py:49`**
  - เพิ่ม `sale` ใน `depends` เพื่อให้ `sale.order`/`sale.order.line.sale_line_ids` มีตัวตนบน DEV (Odoo 17 ต้องมี sale ติดตั้งก่อน load PV)
  - คง `account, mail, l10n_th_account_tax, account_payment_batch_process` เดิม
- **Tests `buz_accounting_addon/tests/test_customer_refund_payment.py:13`**
  - แก้ `setUpClass` สร้าง `sale.order (Command.create product_uom_qty 1 tax_id clear) → action_confirm → _create_invoices → action_post → pay via account.payment.register cheque_amount=residual → _create_payments → CN out_refund with sale_line_ids=[Command.set(order_line.ids)] → action_post` เพื่อให้ CN มี `sale_line_ids` ครบและ source invoice `paid`
  - คง 4 tests เดิม `test_refund_action_forces_approved_amount`/`test_standard_credit_note_action_remains_unchanged`/`test_refund_payment_is_partial_linked_and_reconciled`/`test_server_rejects_tampered_amount` — ผ่านหลัง fix `display_type='product'` (เดิม `not display_type` ทำให้ filtered ว่าง) และ `sale` depends
  - ทดสอบด้วย `docker-compose.test.yml` isolated (`-i buz_accounting_addon,sale --test-tags /buz_accounting_addon`) ผล `10 tests 0 failed 0 error`
- **ขอบเขตคงเดิม:** Refund PV แยกจาก Vendor PV, ปุ่ม Register แยกจาก Credit Note, Vendor PV ไม่เปลี่ยน, ไม่แก้ยอด SO/Invoice/CN, ไม่รองรับมัดจำ/ล่วงหน้า, ไม่เปลี่ยน Bank Reconciliation
- **ข้อควรระวัง:** `buz_accounting_addon/models/account_move.py:101` มี override `_compute_amount` ที่ทำให้ `in_payment + residual 0` กลายเป็น `paid` เมื่อ `ar_outstanding_as_paid=True` — spec ใหม่ถือว่า `Outstanding Payments` ยังไม่ paid ต้องปิด param นี้หรือปรับ logic ให้ strict `payment_state=paid` จริงถึงจะสอดคล้อง `Paid = Reconcile ธนาคารแล้ว`

### 10. แก้เลข Payment ก่อน Post (เพิ่ม 2026-09-04 — แผนปรับ Customer Refund PV ให้แก้เลข Payment ก่อน Post)
- **Spec:** `Refund PV → Register Refund Payment → Create Payment → แก้เลข Payment → Post Payment → Reconcile` — Payment/Journal สร้างเป็น Draft ก่อน ให้บัญชีแก้เลข `PBNK11/2026/00009` (เลขเดียวกับ `account.move.name` / Journal Entry) แล้วจึง Post, Post แล้วล็อกเลข ห้ามแก้ผ่าน Form/RPC/Import และตรวจเลขซ้ำใน Journal+Company เดียวกัน, คง `refund_amount` และลิ้ง `Refund PV → Payment → Credit Note`
- **Payment Register `buz_accounting_addon/models/account_payment_register.py:38`**
  - แยก Refund PV flow ออกจาก flow มาตรฐาน: ถ้า `buz_customer_refund_pv_id` ใน context ให้ทำ validation เดิม (`PV posted`, `has_active_payment`, `CN posted out_refund`, `amount==refund_amount`, `amount<=residual`, `_check_source_invoices_paid`) แล้วสร้าง Payment แบบ **Draft only** โดยเรียก `_get_batches` → `_create_payment_vals_from_wizard/_batch` → `_init_payments` อย่างเดียว **ไม่เรียก `_post_payments`/`_reconcile_payments`** — ทำให้ `payment.state=draft`, `move.state=draft`, `name='/'`, ยังไม่ Reconcile `Credit Note` (`amount_residual` ยัง 4990)
  - `refund_pv.write payment_ids [(4)]` + `payments.write buz_customer_refund_pv_id` + `message_post` Draft ทันที, return `payments` ให้ `action_create_payments` เปิดฟอร์ม Payment แบบ Draft เพื่อให้แก้เลขแล้ว Post
  - Flow มาตรฐาน (ไม่มี `buz_customer_refund_pv_id`) ยัง `super()._create_payments()` → `init+post+reconcile` เหมือนเดิม ไม่กระทบ `Credit Note` ปุ่มเดิม, `Vendor PV`, `Batch Payment`
- **Payment `buz_accounting_addon/models/account_payment.py:14` + `account_move.py:29`**
  - `account.payment:14` คง `buz_customer_refund_pv_id` + เพิ่ม `write:14` สำหรับ Refund PV: ถ้า `state != 'draft'` ห้ามแก้ `name`, ถ้า Draft ตรวจเลขซ้ำ `account.move search name+journal+company id!=move.id state!=cancel` และ `account.payment search` ซ้ำ → `UserError` (`Payment number already exists`), ใช้ `move_id` ตรวจ Journal/Company เดียวกัน
  - `account.move:29` เพิ่ม `write:29` กันแก้ `name` ของ Journal Entry ที่เป็น Payment ของ Refund PV หลัง Post และตรวจซ้ำ `journal+company`
  - `account.payment action_post:60` หลัง `super().action_post()` ถ้า `buz_customer_refund_pv_id` และ `state==posted` ให้หา `credit_note = pv.credit_note_id` แล้ว `reconcile` แบบ `payment_receivable_lines + credit_receivable_lines filtered account_type receivable/payable not reconciled → (p_lines + c_lines).reconcile()` ต่อ `account` — ทำให้ Draft ยัง `4990` หลัง Post จึง `990` และ `payment_state` Credit Note เปลี่ยน
- **Refund PV `buz_accounting_addon/models/customer_refund_pv.py:72`**
  - เพิ่ม `refund_payment_id:Many2one compute`, `refund_payment_name:Char compute`, `refund_payment_state:Selection related`, `refund_payment_move_name:Char compute` — `_compute_refund_payment:220` เลือก `payment_ids filtered state!=cancel [:1]` แสดงเลข `move_id.name` หรือ `payment.name` (ถ้า `'/'` ให้แสดง `Draft`) และ `move_name`
  - `payment_ids` ยัง `Many2many` เดิม, `payment_count/has_active_payment` คงเดิม (นับรวม cancel), `Register` ยัง `has_active_payment` ซ่อนปุ่มหลังสร้าง Draft
- **Views `buz_accounting_addon/views/customer_refund_pv_views.xml:93` / `account_payment_views.xml:4` / `account_move`**
  - `customer_refund_pv_views.xml:93` เพิ่ม `group Source Documents` ยังคง, เพิ่ม `group Refund Payment (Draft → Post) invisible payment_count==0` แสดง `refund_payment_name`, `refund_payment_state` badge, ปุ่ม `Open Payment`, hint `Draft: แก้เลข → Post` / `Posted: Reconcile แล้ว`, Tree เพิ่ม `refund_payment_name/state optional hide`
  - `account_payment_views.xml:4` เพิ่ม `view_account_payment_form_inherit_refund_pv_number` inherit `account.view_account_payment_form`: เพิ่ม `buz_customer_refund_pv_id invisible`, ซ่อน `h1 Draft` เดิมเมื่อเป็น Refund PV (`invisible state !='draft' or buz_customer_refund_pv_id`) แล้วเพิ่ม `h1` ใหม่ `invisible state !='draft' or not buz_customer_refund_pv_id` มี `field name placeholder PBNK11/2026/00009` แก้ได้เฉพาะ Draft, info alert `Draft แก้เลข → Post` / `Posted ล็อกแล้ว`, ใช้ `hasclass('oe_title')` แทน `@class` เพื่อเลี่ยง warning
  - `account_move` view เพิ่ม `payment_id invisible` และ `name readonly state !='draft'` (คงมาตรฐาน Odoo, ล็อกหลัง Post ผ่าน python write)
  - `account_payment_register_inherit_views.xml:4` ยัง `readonly context.get('buz_customer_refund_pv_id')` สำหรับ `amount` ใน wizard (คง)
  - Security: แก้เลข/ Post จำกัดด้วย `account.group_account_invoice` (ปุ่ม `Reset To Draft`/`Confirm` มี groups) + python `UserError` กัน RPC/Import หลัง Post
- **Tests `buz_accounting_addon/tests/test_customer_refund_payment.py:95`**
  - อัปเดต `test_refund_payment_is_partial_linked_and_reconciled` ให้ตรวจ `payment.state draft` หลัง `make_payments` (`amount_residual 4990` ยังไม่ reconcile) → `payment.name = PBNK11/2026/00009` ตรวจ `move_id.name` ตรงกัน → `action_post` → `posted` → `amount_residual 990`
  - เพิ่ม `test_refund_payment_draft_editable_and_post_locks` ตรวจ Draft แก้ได้, Posted ล็อก `UserError`
  - เพิ่ม `test_refund_payment_duplicate_number_blocked` สร้าง PV2 `990` แล้วตั้งเลขซ้ำ `PBNK11/2026/00012` ใน Journal เดียวกัน → `UserError`
  - เพิ่ม `test_refund_payment_draft_not_reconciled` ตรวจ Draft ยัง `4990`
  - รวม `13 tests 0 failed 0 error` บน `docker-compose.test.yml` isolated (`-i buz_accounting_addon,sale`)
- **ขอบเขตคงเดิม:** Refund PV แยกจาก Vendor PV, ปุ่ม Register แยกจาก Credit Note, Vendor PV ไม่เปลี่ยน, ไม่แก้ยอด SO/Invoice/CN, ไม่รองรับมัดจำ/ล่วงหน้า, ไม่เปลี่ยน Bank Reconciliation ก่อน Post
- **ทดสอบ:** `docker-compose.test.yml` isolated บนเครื่องนี้ (`docker compose -f docker-compose.test.yml up --abort-on-container-exit` แบบ `-i buz_accounting_addon,sale --test-tags /buz_accounting_addon`) ผล `13 tests 0 failed` — ทดสอบผ่านแล้ว deploy ณ 04:45 ตามคำขอใหม่

### 11. แก้ RPC_ERROR จาก `_compute_source_documents` (เพิ่ม 2026-09-04 — แผนแก้ RPC_ERROR)
- **Bug:** `not_paid` เป็น Python `list` (`append(inv)`) แต่เรียก `.mapped("name")` ทำให้เปิด Refund PV หรือ Confirm/Register เมื่อ Invoice ยังไม่ Paid แล้วเกิด `RPC_ERROR: 'list' object has no attribute 'mapped'` — เปิดหน้าไม่ได้, Confirm/Register ไม่ได้ข้อความที่อ่านเข้าใจ
- **Fix:** `buz_accounting_addon/models/customer_refund_pv.py:326` ใน `_compute_source_documents` และ `:384` ใน `_check_source_invoices_paid` เปลี่ยนจาก `not_paid.mapped("name")` เป็น `", ".join(inv.name or str(inv.id) for inv in not_paid)` คงเงื่อนไข `posted`/`out_invoice`/`payment_state=paid`/`amount_residual=0` และ `UserError` เดิม ไม่แก้ Payment/CN/Vendor PV/Batch ไม่ปรับสูตรยอดเงิน
- **ทดสอบ:** เปิด PV มี Source Invoice Paid ได้, เปิด PV ไม่มี Source Invoice ได้และแสดง `ไม่พบ SO/Invoice` โดยไม่เกิด RPC_ERROR, เปิด PV ยังไม่ Paid ได้, Confirm ยังไม่ Paid ถูกบล็อก `UserError`, Register เมื่อเปลี่ยนเป็นยังไม่ Paid ถูกบล็อก, Paid ครบ Confirm/Register ได้, `python -m py_compile 0`, `git diff --check` ผ่าน, `docker-compose.test.yml` isolated `13 tests 0 failed 0 error`

### 12. แก้ต้นเหตุ Refund PV ตรวจไม่พบ Invoice เนื่องจาก CN ไม่มี `sale_line_ids` (เพิ่ม 2026-09-04 — แผนแก้ Refund PV ตรวจไม่พบ Invoice ต้นทาง)
- **สาเหตุ:** CN มี SO และ Invoice จริง แต่รายการใน CN ไม่ได้เชื่อมด้วย `sale_line_ids` ทำให้ Refund PV ค้นหา Invoice ไม่พบ — เจ้าของ CN คือ `sale_order_line_credit_note` และ `po_so_credit_note` (SO wizard) นอก `buz_accounting_addon` แต่ต้องแก้เพื่อคง flow `SO → Invoice Paid → CN → Refund PV → Confirm/Register`
- **ความสัมพันธ์ที่ต้องได้:** `CN Invoice Line → sale_line_ids → SO Line ← sale_line_ids ← Invoice Line` — ไม่ใช้ `invoice_origin` เป็น fallback อัตโนมัติ ป้องกันจับ Invoice ผิดเมื่อมีหลายเอกสาร
- **`po_so_credit_note/wizards/so_credit_note_wizard.py:108`:** เดิม `sale_line_id: so_line.id` (field ไม่มีใน `account.move.line`, Odoo 17 ใช้ `sale_line_ids` M2M) → แก้เป็น `sale_line_ids: [fields.Command.link(so_line.id)]` + `tax_ids: [fields.Command.set(so_line.tax_id.ids)]` พร้อม comment `preserve sale_line_ids for Refund PV source tracking / do NOT guess via invoice_origin`
- **`sale_order_line_credit_note/wizard/sale_order_credit_note_wizard.py:198`:** เดิม `sale_line_ids: [(6,0, ids)]` / `tax_ids: [(6,0, ids)]` → แก้เป็น `sale_line_ids: [fields.Command.link(line.sale_line_id.id)] if line.sale_line_id else []` + `tax_ids: [fields.Command.set(line.tax_ids.ids)]` + comment `CN line.sale_line_ids -> SO line <- Invoice line.sale_line_ids` — รักษา link เดิมทันทีที่สร้าง CN ห้ามเดาจากชื่อ/ยอด/ข้อความ `invoice_origin`
- **`buz_accounting_addon/models/customer_refund_pv.py` (คงเดิมไม่แก้ยอด):** คงการค้นหาหลัก `CN line.sale_line_ids → Invoice line.sale_line_ids → Invoice` (`_get_source_sale_lines:243`, `_get_source_invoices:258`, `_compute_source_documents:275`, `_check_source_invoices_paid:333`) ตรวจ `out_invoice` + `posted` + `payment_state=paid` + `amount_residual=0` (`float_is_zero` + rounding) ทุกใบ, ข้อความแยก `ไม่พบ SO ต้นทาง` vs `ไม่พบ Invoice ต้นทาง` vs `Invoice ยังไม่ Paid: INV... (state=..., payment_state=..., residual=...)` — ไม่สร้างลิงก์โดยเดา, ไม่ mass update CN เดิม ต้อง repair รายใบระบุ CN/Invoice ชัดเจน
- **RPC ที่เกี่ยวข้อง:** คง fix `not_paid: list` + `", ".join(...)` ใน `_compute_source_documents:325` และ `_check_source_invoices_paid:379` เพื่อให้เปิด/Confirm/Register ได้โดยไม่เกิด `RPC_ERROR: 'list' object has no attribute 'mapped'` ทั้งกรณี Paid/ยังไม่ Paid
- **ทดสอบ:** `SO 3 รายการ → CN เฉพาะรายการที่ต้องการ → sale_line_ids ตรง SO line เดิม → Invoice Paid residual 0 → Create Refund PV พบ Invoice ได้`, `CN ไม่มี sale_line_ids → แจ้ง ไม่พบ SO ต้นทาง`, `Invoice ยังไม่ Paid → Confirm/Register block UserError`, `Invoice หลายใบ → ตรวจทุกใบ`, `CN เชื่อมผิด SO line → ไม่จับ Invoice ผิด`, `เปิด Refund PV ไม่เกิด RPC_ERROR`, `ยอด CN/Refund PV ไม่เปลี่ยน`, `Register Payment / Vendor PV / Batch ยังเหมือนเดิม`, `python -m py_compile 0`, `git diff --check 0` ผ่าน
- **ขอบเขต:** ใช้ `sale_line_ids` จริงเป็นหลัก ไม่จับคู่ด้วยชื่อเอกสาร/จำนวนเงิน, ไม่แก้ยอดบัญชี, ไม่เปลี่ยน Logic Payment/Reconcile, ตรวจเจ้าของ CN แล้ว (2 wizards ข้างต้น) จึงแก้ได้ทันที

## ผลการ Upgrade และ Restart DEV (ล่าสุด)
- **Upload ล่าสุด 2026-09-04 06:08 (รอบนี้ — แก้ต้นเหตุ sale_line_ids):** `scp -r -i dev_server_ed25519` `buz_accounting_addon, po_so_credit_note, sale_order_line_credit_note` → `/srv/docker/odoo/custom-addons/` `SCP_EXIT True` ทั้ง 3 โมดูล, `cp -r` ไป `/srv/docker/odoo_dev/custom-addons/` `COPIED` ทั้ง 3, ตรวจ `models/customer_refund_pv.py 40932` bytes (เดิม), `po_so_credit_note/wizards/so_credit_note_wizard.py` มี `sale_line_ids: [fields.Command.link...]` (แก้ `sale_line_id` → `sale_line_ids`), `sale_order_line_credit_note/wizard/sale_order_credit_note_wizard.py` มี `Command.link/set` (แก้ `(6,0)` → `Command`), `Module buz_accounting_addon loaded in 6.73s` `Registry loaded in 37.261s`
- **Upgrade 2026-09-04 06:08 (รอบนี้):** `docker exec odoo odoo -d MOG_DEV -u buz_accounting_addon,po_so_credit_note,sale_order_line_credit_note --stop-after-init --no-http` สำเร็จ `320 modules loaded in 19.79s, 1090 queries` `Module buz_accounting_addon loaded in 6.73s` `Registry loaded in 37.261s` `Modules loaded. Stopping gracefully` (warning `office_supply_requisition not installable` + `fields.states` เดิม — ไม่กระทบ Refund PV) `commit 51461ad4 fix: preserve sale_line_ids on CN creation`
- **Upload ก่อนหน้า 2026-09-04 05:09 (แก้ RPC_ERROR _compute_source_documents):** `scp -r -i dev_server_ed25519` `buz_accounting_addon` → `/srv/docker/odoo/custom-addons/` `SCP_EXIT 0`, `cp -r` ไป `/srv/docker/odoo_dev/custom-addons/` `COPIED`, ตรวจ `models/customer_refund_pv.py` 40932 bytes (แก้ `not_paid.mapped` → `join` 2 จุด `:326` `:384`), `Module buz_accounting_addon loaded in 5.70s` `Registry loaded in 25.937s`
- **Upgrade 2026-09-04 05:09 (ก่อนหน้า):** `docker exec odoo odoo -d MOG_DEV -u buz_accounting_addon --stop-after-init --no-http` สำเร็จ `Module buz_accounting_addon loaded in 5.70s` `Registry loaded in 25.937s` `Modules loaded. Stopping gracefully` (warning `office_supply_requisition not installable` เดิม — ไม่กระทบ Refund PV)
- **Upload ก่อนหน้า 2026-09-04 04:45 (แก้เลข Payment ก่อน Post):** `scp -r -i dev_server_ed25519` `buz_accounting_addon` → `/srv/docker/odoo/custom-addons/` `SCP_EXIT 0`, `cp -r` ไป `/srv/docker/odoo_dev/custom-addons/` `COPIED`, ตรวจ `models/customer_refund_pv.py` 40925 bytes (เพิ่ม `refund_payment_*` 4 fields, `_compute_refund_payment`), `models/account_payment.py` 4979 bytes (`write` ล็อกเลข + `action_post` reconcile), `views/account_payment_views.xml` 3828 bytes (`hasclass` + แก้เลข Draft), `models/account_payment_register.py` 6 `buz_customer_refund_pv_id` (Draft flow), `models/account_move.py` `write` ล็อก Journal Entry, `views/customer_refund_pv_views.xml` + `Refund Payment (Draft→Post)` group, `tests` 13 tests
- **Upgrade 2026-09-04 04:45 (ก่อนหน้า):** `docker exec odoo odoo -d MOG_DEV -u buz_accounting_addon --stop-after-init --no-http` สำเร็จ `Module buz_accounting_addon loaded in 6.95s` `Registry loaded in 43.749s` `Modules loaded. Stopping gracefully` (warning `office_supply_requisition not installable` เดิม — ไม่กระทบ Refund PV)
- **Upload ก่อนหน้า 2026-09-04 03:53 (Source Validation):** `scp -r -i dev_server_ed25519` `buz_accounting_addon` → `/srv/docker/odoo/custom-addons/` `SCP_EXIT 0`, `cp -r` ไป `/srv/docker/odoo_dev/custom-addons/` `COPIED`, ตรวจ `models/customer_refund_pv.py` 38950 bytes (เพิ่ม `_check_source_invoices_paid`, `source_*` 6 fields, `float_is_zero`), `views/customer_refund_pv_views.xml` 9574 bytes (เพิ่ม button_box + source group), `models/account_payment_register.py` 8894→~9000 bytes (`+_check_source...`), `__manifest__.py` `+sale`, `tests/test_customer_refund_payment.py` สร้าง SO/Invoice paid ก่อน CN
- **Upgrade ก่อนหน้า 2026-09-04 03:53:** `docker exec odoo odoo -d MOG_DEV -u buz_accounting_addon --stop-after-init --no-http` สำเร็จ `Module buz_accounting_addon loaded in 5.69s` `Registry loaded in 27.767s` `Modules loaded. Stopping gracefully` (warning `office_supply_requisition not installable`, `fields.states no longer supported` เดิม — ไม่กระทบ Refund PV)
- **Upload ก่อนหน้า 2026-09-03 16:50:** `scp -r -i dev_server_ed25519` `SCP_EXIT 0`, ตรวจ `models/customer_refund_pv.py` 28359 bytes (เพิ่ม `batch=False` + merge `action_context`), `models/account_payment_register.py` 8894 bytes (`compare_amounts` 3 จุด, `make_payments` override), `tests/test_customer_refund_payment.py` 3.3K (4 tests), `__manifest__` depends `+account_payment_batch_process`
- **Upgrade ก่อนหน้า 2026-09-03 16:50:** `docker exec odoo odoo -d MOG_DEV -u buz_accounting_addon --stop-after-init --no-http` สำเร็จ `Module buz_accounting_addon loaded in 10.17s` `Registry loaded in 45.589s` `Modules loaded. Stopping gracefully` `UPGRADE_EXIT 0` (warning `office_supply_requisition not installable`, `fields.states no longer supported` เหมือนเดิม — ไม่กระทบ Refund PV)
- **Upload ก่อนหน้า 2026-09-03 09:19:** `scp -r` `SCP_EXIT 0`, `models/customer_refund_pv.py` 24114→24700 bytes (เพิ่ม `has_active_payment`), `views/customer_refund_pv_views.xml` 7350 bytes, `views/account_payment_register_inherit_views.xml` 710 bytes
- **Upgrade ก่อนหน้า 2026-09-03 09:19:** `Registry loaded in 31.221s` `Stopping gracefully` (เคย `ParseError has_active_payment` แก้แล้ว), ก่อนหน้า `08:45/08:34/08:15/07:52` `36.925s/40.623s/34.553s/30.789s`
- **Restart (รอบนี้ 06:08):** `docker restart odoo odoo_dev` → `odoo Up 6 seconds` + `odoo_dev Up 3 seconds` (ณ 06:08) `postgres Up 4 days (healthy)` `Odoo version 17.0-20260119 HTTP service running on 0.0.0.0:8069 Workers alive` `Evented Service (longpolling) running on 0.0.0.0:8072` — หลัง upgrade ทั้ง 3 โมดูล
- **Verify (รอบนี้):** `wc -c customer_refund_pv.py 40932` `grep sale_line_ids 3 sale_line_ids: [fields.Command.link...` `grep not_paid.mapped 0` `python -m py_compile 0 (ทั้ง 3 โมดูล)` `git diff --check 0` — ยืนยันโค้ดใหม่บน DEV แล้ว; `docker-compose.test.yml` isolated คง `13 tests 0 failed 0 error` (ไม่แก้ยอด ไม่กระทบ Payment/Batch)

## Error / ข้อจำกัดที่ยังเหลือ
- **Upgrade concurrent** ยังมีโอกาส `SerializationFailure` เมื่อมี request พร้อมกัน — แก้ด้วย retry
- **Warning คงเหลือ** `office_supply_requisition: not installable, skipped`, `fields.states is no longer supported`, `Two fields ... have same label` — ไม่กระทบ Refund PV
- **เลขซ้ำ** ใช้ `@api.constrains` + ตรวจใน `action_confirm` ไม่ใช้ `_sql_constraints unique(name)` เพื่อให้หลาย Draft ว่าง `name=False` ได้
- **Other Income** ยังมี field `other_income_dis` ในโมเดล/ฟอร์มแต่ไม่ใช้คำนวณยอดคืน (report `payment_main_amount` และ `get_preview_moves` ตั้ง `other_income=0.0`)
- **Register แยก** ปุ่มใหม่ `Register Refund Payment` บน Refund PV ใช้ `refund_amount` (เช่น 4000) ส่วนปุ่มเดิมบน Credit Note ใช้ยอดเต็ม CN (4990) ยังแยกกันชัดเจน ไม่กระทบ Invoice/Vendor Bill, ทดสอบ `Draft, ยอดเกิน, ไม่มี CN, Register ซ้ำ` block ครบ, Wizard `amount` ล็อก `readonly` เมื่อมาจาก PV, หลัง `Cancel` Payment กลับมา Register ใหม่ได้

## ขอบเขต Phase นี้ vs ถัดไป
- **Phase นี้ทำแล้ว (รวม 2026-09-04 แก้ต้นเหตุ sale_line_ids + แก้เลขก่อน Post):** `SO → Invoice Paid → CN (sale_line_ids ครบ) → Create Refund PV → Confirm (ตรวจ SO/Invoice Paid) → Print → Register Refund Payment (ปุ่มใหม่บน Refund PV ใช้ refund_amount) → Create Payment (Draft) → แก้เลข Payment/Journal (PBNK11/2026/00009, เลขเดียวกับ move.name, ตรวจซ้ำ Journal+Company) → Post Payment (ล็อกเลข) → Reconcile` เก็บ `payment_ids/payment_count (รวม cancel) + has_active_payment + refund_payment_name/state` บน Refund PV, Smart Button `Payment` + `Open Payment` + `Source SOs/Invoices`, `Credit Note ↔ Refund PVs ↔ Payment (Draft→Posted)` ครบ, เลข PV ≠ เลข Payment/Journal ≠ เลข CN, ปุ่มเดิมบน Credit Note ยัง `Posted` ทันทีมาตรฐาน, รองรับหลาย PV ต่อ CN ตรวจยอดรวมไม่เกิน CN + ตรวจ SO/Invoice Paid ก่อน Confirm/Register + สร้าง CN ต้องมี `sale_line_ids` ทุกบรรทัด (2 wizards แก้แล้ว)
- **ยังอยู่นอก Phase นี้:** ไม่ใช้ `WHT` / `Bank Fee` คำนวณยอดคืน (แม้มี field ยังไม่ผูก), ไม่สร้าง `account.payment` อัตโนมัติตอน Confirm, ไม่แก้ Vendor PV/Batch Payment, ไม่รวม `WHT Certificate`, `Bank Transfer`, ไม่ mass update CN เก่าที่ไม่มี sale_line_ids (ต้อง repair รายใบ)

Flow หลัง Fix ใช้งานได้ครบ `SO → Invoice Paid → CN (sale_line_ids) → Refund PV → Confirm → Print → Register Refund Payment (4000) → Payment Draft (แก้เลข PBNK11...) → Post → Reconcile` พร้อมขออนุมัติแล้ว — ทดสอบ `13 tests` ผ่านบนเครื่องนี้, deploy แล้ว ณ 06:08 บน DEV (`MOG_DEV`) รวมแก้ต้นเหตุ `sale_line_ids` (commit 51461ad4) + แก้ RPC_ERROR `not_paid.mapped`
