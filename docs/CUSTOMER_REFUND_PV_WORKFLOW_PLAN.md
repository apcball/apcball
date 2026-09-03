# Customer Refund PV — Workflow Plan (ถึงขั้น Register Payment)

## สรุป Flow ปัจจุบัน
```
Posted Customer Credit Note (out_refund)
→ Create Refund PV (Draft)
→ กรอกเลข Refund PV + Refund Amount (ยอดที่จะจ่ายจริง)
→ Confirm → Posted (ล็อกเอกสาร)
→ Print Refund PV (PDF แยกจาก Vendor PV)
→ Register Payment (ปุ่มเดิมบน Credit Note, ใช้ refund_amount)
→ Reconcile Payment ↔ Credit Note
→ [Phase ถัดไป] WHT / Bank Fee / ติดตามยอดจ่ายจริง
```

เอกสารเป็นโมเดลแยก `buz.customer.refund.pv` / `buz.customer.refund.pv.line` ใช้ layout เดียวกับ Vendor PV แต่ไม่กระทบ Vendor PV เดิม

## สิ่งที่แก้ไขจริง

### 1. Rename View (Phase 1)
- `buz_accounting_addon/views/buz_customer_refund_pv_views.xml` → `buz_accounting_addon/views/customer_refund_pv_views.xml`
- `buz_accounting_addon/__manifest__.py:66` อ้างอิงชื่อใหม่, ลบไฟล์เก่าบน DEV

### 2. โมเดลหลัก `buz_accounting_addon/models/customer_refund_pv.py`
- **Header `BuzCustomerRefundPv:6`**
  - `name:13` เปลี่ยน `readonly=True, default="/"` → `copy=False, index=True` รองรับกรอกเอง + auto `next_by_code("buz.customer.refund.pv")` เมื่อว่าง ใน `create:81` / `write:99` (Sequence สร้างเฉพาะ Header)
  - `refund_amount:63` เพิ่ม `fields.Monetary(string="Refund Amount")` สำหรับยอดจ่ายจริงที่บัญชีระบุ รองรับบางส่วนเช่น `4,990 → 3,000`
  - `line_ids:60` One2many `buz.customer.refund.pv.line`
  - `amount_total_gross/wht/net:66` คงสูตรเดิม `sum(line)` ไม่แก้
  - `payment_ids:72` `Many2many account.payment buz_customer_refund_pv_payment_rel` + `payment_count:73` `compute _compute_payment_count:184` + `action_view_payments:189`
- **Line `BuzCustomerRefundPvLine:351`**
  - ไม่มี field `name` / `date`
  - fields เดิม `pv_id:355, move_id:357 (domain out_refund,posted), amount_to_pay_gross:367, buz_wht_tax_id, wht_base_amount, wht_rate, wht_amount, amount_to_pay_net:376`
  - `onchange move_id:381` เติม Gross/WHT Base จาก `amount_residual_signed/amount_untaxed_signed`
  - `create:409` ลบโค้ดผิดที่ตั้ง `vals["name"]=next_by_code` บน Line (ต้นเหตุ `Invalid field 'name' on model 'buz.customer.refund.pv.line'`) เหลือแค่ตรวจ `if pv.state=="posted" raise` + `write:418/unlink:423` ล็อกหลัง Posted
- **Confirm `action_confirm:114`**
  - ตรวจ `state draft → name จำเป็น + ตรวจซ้ำ search name, partner, date, credit_note out_refund+posted, line_ids, refund_amount>0, gross/net>0, ทุกยอด <= residual (amount_residual_signed)` รวมถึง `refund_amount - residual >1e-6`
  - `write({"state":"posted"})` + `message_post` ไม่สร้าง `account.payment` ไม่ reconcile (Confirm ยังไม่สร้าง Payment)
  - `write:101` ล็อก `protected {name, partner_id, credit_note_id, date, payment_type, destination_journal_id, bank_free_dis, other_income_dis, line_ids, note, refund_amount}` หลัง Posted, `_check_name_unique:90` กันซ้ำ
- **Preview `get_preview_moves:193`**
  - ถ้ามี `refund_amount>0` ใช้เป็น `total_gross` (`total_net = gross - wht`) รองรับพิมพ์บางส่วน, `other_income =0.0` ไม่ใช้ Other Income คำนวณยอดคืน, `total_disbursement = net + bank_fee`

### 3. Account Move `buz_accounting_addon/models/account_move.py:29`
- `action_create_customer_refund_pv:29` ตรวจ `out_refund+posted` สร้าง PV `vals {partner_id, company_id, credit_note_id, date}` แล้ว `write line_ids Command.create({move_id, amount_to_pay_gross:residual, wht_base_amount:untaxed})` ใช้ field จริงเท่านั้น
- `customer_refund_pv_count:10` + smart button `Refund PVs`
- `action_register_payment:87` **Phase Register Payment** — ไม่สร้างปุ่มใหม่ ใช้ปุ่มเดิมบน Credit Note: ถ้า `move_type out_refund` และมี `customer_refund_pv_ids` ให้หา `refund_pv` ล่าสุด `posted + refund_amount>0` ตรวจ `ไม่เคย Register (payment_ids non-cancel)`, `refund_amount <= residual`, กัน Register ก่อน Confirm (`draft` → raise), แล้ว `with_context(buz_customer_refund_pv_id, force_amount=refund_amount, default_journal_id, default_payment_date)` เรียก `super().action_register_payment()` ใช้ `refund_amount` แทนยอดเต็ม Credit Note

### 4. Payment Link `buz_accounting_addon/models/account_payment.py:14` + `account_payment_register.py:13`
- `account.payment:14` เพิ่ม `buz_customer_refund_pv_id Many2one buz.customer.refund.pv`
- `account.payment.register:13` `_compute_amount` รองรับ `force_amount` อยู่แล้ว, `_create_payments:44` หลัง `super` ตรวจ `buz_customer_refund_pv_id` ใน context → `refund_pv.write payment_ids [(4)]` + `payments.write buz_customer_refund_pv_id` + `message_post` + log ไม่ใช้ WHT/Bank Fee ใน Phase นี้, Reconcile ใช้กลไกมาตรฐาน Odoo

### 5. View `buz_accounting_addon/views/customer_refund_pv_views.xml`
- Header `38` ปุ่ม `Confirm invisible draft` + `Print Payment Voucher %(action_report_customer_refund_pv)d invisible posted`
- Title `54` `name` `placeholder="Enter Refund PV Number" readonly draft required=1`
- Header_right `66` เพิ่ม `refund_amount widget monetary readonly draft required=1`
- `oe_button_box:44` คง `Credit Note` + `Net Amount` เพิ่ม `action_view_payments:46` `icon fa-credit-card invisible payment_count==0` `payment_count statinfo`
- `line_ids:81` `readonly draft` tree แสดง `move_id(domain out_refund), amount_to_pay_gross, wht_base_amount, buz_wht_tax_id, wht_amount, amount_to_pay_net`

### 6. Report แยกจาก Vendor PV
- `buz_accounting_addon/reports/customer_refund_pv_report.xml:4` `paperformat_customer_refund_pv` A4 `19` `action_report_customer_refund_pv` `model buz.customer.refund.pv` `report_name buz_accounting_addon.report_customer_refund_pv` `binding_model_id model_buz_customer_refund_pv`
- `buz_accounting_addon/reports/customer_refund_pv_template.xml:4` `id report_customer_refund_pv` โคลน `payment_voucher_template.xml` เปลี่ยน `VOUCHER NO. = o.name:66`, `เลขที่เอกสาร = line.move_id.name:105`, `จำนวนเงิน = o.refund_amount:112,121`, `payment_main_amount:128` `(o.refund_amount or gross) - wht - bank_fee` ตัด `other_income`
- Vendor `payment_voucher_report/template` ไม่แก้

### 7. Manifest `buz_accounting_addon/__manifest__.py:61`
- เพิ่ม `reports/customer_refund_pv_report.xml`, `reports/customer_refund_pv_template.xml` ต่อหลัง `payment_voucher` ก่อน `payment_transfer`

## ผลการ Upgrade และ Restart DEV (ล่าสุด)
- **Upload 2026-09-03 15:13:** `scp -r -i dev_server_ed25519` `SCP_EXIT 0`, ตรวจ `models/customer_refund_pv.py` 24114 bytes, `reports/customer_refund_pv_report.xml` 1534 bytes, `customer_refund_pv_template.xml` 23090 bytes, `views/customer_refund_pv_views.xml` 7297 bytes, `grep next_by_code` พบ 2 จุดใน PV เท่านั้น Line ไม่มี
- **Upgrade 2026-09-03 08:15:** `docker exec odoo odoo -d MOG_DEV -u buz_accounting_addon --stop-after-init --no-http` สำเร็จ `Modules loaded.` `Registry loaded in 34.553s` `Stopping gracefully` (ไม่พบ SerializationFailure รอบนี้)
- **Upgrade ก่อนหน้า 2026-09-03 07:52:** เคย `SerializationFailure could not serialize access due to concurrent update` ต้อง retry 5s แล้วสำเร็จ `Registry loaded in 30.789s`
- **Restart:** `docker restart odoo` → `odoo Up 13s` (ล่าสุด) / `odoo Up 23s` (รอบก่อน), `odoo_dev Up 29h`, `postgres Up 3 days (healthy)`
- **Verify DB:** `psql MOG_DEV: select name, state from ir_module_module where name='buz_accounting_addon'` → `installed`, `select name from ir_act_report_xml where report_name like '%customer_refund%'` → `Customer Refund Payment Voucher`

## Error / ข้อจำกัดที่ยังเหลือ
- **Upgrade concurrent** ยังมีโอกาส `SerializationFailure` เมื่อมี request พร้อมกัน — แก้ด้วย retry
- **Warning คงเหลือ** `office_supply_requisition: not installable, skipped`, `fields.states is no longer supported`, `Two fields ... have same label` — ไม่กระทบ Refund PV
- **เลขซ้ำ** ใช้ `@api.constrains` + ตรวจใน `action_confirm` ไม่ใช้ `_sql_constraints unique(name)` เพื่อให้หลาย Draft ว่าง `name=False` ได้
- **Other Income** ยังมี field `other_income_dis` ในโมเดล/ฟอร์มแต่ไม่ใช้คำนวณยอดคืน (report `payment_main_amount` และ `get_preview_moves` ตั้ง `other_income=0.0`)
- **Register Payment จำกัด** กรณี Credit Note มีหลาย Refund PV จะใช้ใบล่าสุดที่ `posted` เท่านั้น, กรณีจ่ายบางส่วน `residual` เหลือตามจริงถูกต้อง แต่ยังไม่มีการตรวจสอบแบบกลุ่มหลาย Credit Note

## ขอบเขต Phase นี้ vs ถัดไป
- **Phase นี้ทำแล้ว:** `Create → Confirm → Print → Register Payment (ใช้ refund_amount) → Reconcile` ผ่านปุ่ม `Register Payment` เดิมบน Credit Note, เก็บ `payment_ids/payment_count` บน Refund PV, Smart Button `Payment` บน Refund PV, `Credit Note ↔ Refund PVs ↔ Payment` ครบ
- **ยังอยู่นอก Phase นี้:** ไม่ใช้ `WHT` / `Bank Fee` คำนวณยอดคืน (แม้มี field ยังไม่ผูก), ไม่สร้าง `account.payment` อัตโนมัติตอน Confirm, ไม่แก้ Vendor PV / Invoice / เอกสารประเภทอื่น, ไม่รวม `WHT Certificate`, `Bank Transfer`, การอัปเดต `CUSTOMER_REFUND_PV_WORKFLOW_PLAN.md` จะทำนอก Phase นี้ตามสเปค

Flow หลัง Fix ใช้งานได้ครบ `Credit Note → Create → Confirm → Print → Register Payment → Reconcile` พร้อมขออนุมัติและตัดยอดแล้ว
