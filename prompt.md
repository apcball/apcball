คุณคือผู้ช่วยสร้างโค้ด Odoo 17 ที่ต้อง “เขียนโค้ดไฟล์ทั้งโมดูลให้รันได้จริง” (พร้อม ZIP) ตามสเปกด้านล่างนี้ โดยไม่พึ่งโมดูลจากภายนอก:

สรุปเป้าหมาย
	•	โมดูลเดียว ครอบคลุม:
ทะเบียนประกันสินค้า (Warranty Template/Contract) → การเคลม (Claim) → งานคลัง RMA/ซ่อม/เปลี่ยน → ออกบิลนอกประกัน → ปิดเคลม
	•	ทำงาน หลังบ้านเท่านั้น (ไม่ใช้ Web Portal)
	•	รองรับ Serial/Lot และ Multi-company

โครงโมดูล
	•	ชื่อ: buz_warranty_rma_management
	•	เวอร์ชัน: 17.0.1.0.0, ใบอนุญาต: LGPL-3
	•	Depends: stock, repair, sale_management, account, mail
	•	โฟลเดอร์/ไฟล์ที่ต้องมี:
    buz_warranty_rma_management/
├── __init__.py
├── __manifest__.py
├── README.md
├── SECURITY.md (อธิบายสิทธิ์)
├── data/
│   ├── sequence.xml
│   ├── mail_templates.xml
├── security/
│   ├── security.xml
│   └── ir.model.access.csv
├── models/
│   ├── warranty_template.py
│   ├── warranty_contract.py
│   ├── warranty_claim.py
│   ├── claim_cost_line.py
│   ├── res_config_settings.py
│   ├── stock_picking_inherit.py
│   └── repair_order_inherit.py
├── views/
│   ├── menuitems.xml
│   ├── warranty_template_views.xml
│   ├── warranty_contract_views.xml
│   ├── warranty_claim_views.xml
│   ├── claim_cost_line_views.xml
│   ├── repair_views_inherit.xml
│   ├── stock_picking_inherit.xml
│   └── res_config_settings_views.xml
├── report/ (ถ้ามี PDF)
├── tests/
│   └── test_warranty_rma_flow.py
└── i18n/th.po (เตรียม key หลัก)

แบบข้อมูล (Models)

1) buz.warranty.template
	•	ใช้เป็น แม่แบบประกัน สำหรับ Product (Free/Extended)
	•	Fields:
	•	name, code (unique), product_tmpl_id (m2o: product.template)
	•	coverage_type (selection: free, extended)
	•	duration_months (int), terms (text)
	•	sell_product_id (m2o: product.product, ใช้ออกบิล extended)
	•	company_id
	•	Constraint: duration_months > 0
	•	Smart button: จำนวนสัญญาที่สร้างจาก template นี้

2) buz.warranty.contract
	•	สัญญาประกัน ผูกกับลูกค้า + สินค้าจริง (Serial/Lot)
	•	Fields:
	•	name (sequence: WCT/%(year)s/%(seq)s)
	•	partner_id, product_id, lot_id (required), company_id
	•	template_id (m2o: buz.warranty.template)
	•	start_date, end_date (คำนวณจาก template.duration)
	•	state (active, expired, cancel)
	•	invoice_id (ถ้าเป็น extended ที่ต้องชำระ)
	•	note
	•	Compute/Onchange:
	•	กำหนด end_date อัตโนมัติจาก start_date + duration_months
	•	state เป็น expired เมื่อเกิน end_date
	•	Action:
	•	action_renew() สร้าง invoice จาก template.sell_product_id และขยายอายุเมื่อชำระ
	•	Constraint:
	•	ห้ามสร้างสัญญา ทับซ้อน (lot เดียว, ช่วงเวลาทับกับ active)
	•	lot ต้องเคยถูกส่งมอบ (ตรวจ stock move outgoing)

3) buz.warranty.claim
	•	คำร้องเคลม (หัวใจของ workflow)
	•	Fields:
	•	name (sequence: WCL/%(year)s/%(seq)s)
	•	contract_id (m2o: buz.warranty.contract) → auto-fill partner_id, product_id, lot_id
	•	partner_id, product_id, lot_id, company_id
	•	reason (selection: defect, repair, replacement, refund, others)
	•	description (text), manager_note (text)
	•	is_in_warranty (compute จาก contract.end_date >= today)
	•	RMA/Logistics refs:
	•	rma_in_picking_id (m2o: stock.picking)  – รับของกลับเข้าคลังซ่อม
	•	repair_id (m2o: repair.order)           – ใบซ่อม
	•	replacement_out_picking_id (m2o)          – ส่งของใหม่
	•	return_to_customer_picking_id (m2o)       – ส่งของกลับลูกค้า
	•	Billing:
	•	claim_cost_line_ids (o2m: buz.claim.cost.line)
	•	invoice_id (m2o: account.move)
	•	state (selection):
draft → under_review → rma_in → repairing → replacing → ready_to_return → done → cancel
	•	Constraints:
	•	ป้องกันเปิดเคลมซ้อนสำหรับ contract/lot เดิม ที่ยังไม่ done/cancel
	•	Actions (server actions):
	•	action_submit() → under_review
	•	action_receive_rma() → สร้าง Incoming Picking (ดูค่าจาก Settings) ใส่ move 1 ชิ้น ระบุ lot, จาก location ลูกค้า → location ซ่อม
	•	action_create_repair() → สร้าง repair.order (ผูก lot) → repairing
	•	action_create_replacement() → สร้าง Outgoing Picking ส่งของใหม่ (เลือก replacement_product_id/lot ตอน validate) → replacing
	•	action_return_to_customer() → สร้าง Outgoing Picking ส่งของ (หลังซ่อม/เดิม) → ready_to_return
	•	action_create_invoice() → สร้าง SO/Invoice จาก claim_cost_line_ids (ใช้ VAT จาก product)
	•	action_mark_done() → ปิดเคลม (ต้องไม่มีเอกสารคลังค้าง และถ้าเป็น out-of-warranty มี invoice แล้ว)
	•	อัปเดตสถานะอัตโนมัติ:
	•	เมื่อ rma_in_picking_id.state = done → state = rma_in
	•	เมื่อ repair_id.state = done → state = ready_to_return (ถ้าไม่ต้องเปลี่ยน)
	•	เมื่อ replacement_out_picking_id หรือ return_to_customer_picking_id = done → state = done

4) buz.claim.cost.line
	•	รายการค่าใช้จ่าย/อะไหล่สำหรับวางบิล (นอกประกัน/บางส่วน)
	•	Fields: claim_id, product_id, name, quantity, price_unit, tax_ids, subtotal (compute), currency_id

5) Settings: res.config.settings
	•	คีย์เก็บค่าใน ir.config_parameter:
	•	buz.default_rma_in_type_id           (m2o: stock.picking.type – Inbound)
	•	buz.default_rma_return_type_id       (m2o: stock.picking.type – Outbound to customer)
	•	buz.default_replacement_type_id      (m2o: stock.picking.type – Outbound replacement)
	•	buz.default_repair_location_id       (m2o: stock.location – โซนซ่อม)
	•	(optional) buz.reminder_days_before_expiry สำหรับแจ้งเตือนสัญญา
	•	สร้าง เมล์เทมเพลต แจ้งเตือนหมดอายุสัญญา และ cron รายวัน

6) Inherit
	•	stock.picking: เพิ่มฟิลด์ buz_claim_id (m2o: buz.warranty.claim) + smart button ย้อนกลับจาก Claim
	•	repair.order: เพิ่ม buz_claim_id + domain lot/product ให้ตรงกับ claim

Views/UI
	•	เมนูหลัก Warranty
	•	Configuration: Warranty Templates, Settings
	•	Operations: Contracts, Claims
	•	Reporting: Claims Analysis (Pivot/Graph) – by product, lot, reason, TAT
	•	ฟอร์ม Template/Contract: กระชับ ใช้งานง่าย, Smart buttons
	•	ฟอร์ม Claim:
	•	แท็บ “Warranty & Serial”: product, lot, สัญญา, วันที่คุ้มครอง, is_in_warranty
	•	แท็บ “RMA & Logistics”: ปุ่ม/ลิงก์ pickings/repair, เหตุผล/บันทึก
	•	แท็บ “Costs & Invoice”: tree claim_cost_line_ids + Smart button เปิด invoice
	•	Header buttons: Submit, Receive RMA, Create Repair, Create Replacement, Return to Customer, Create Invoice, Mark Done
	•	เงื่อนไขแสดงปุ่มตาม state

Sequences
	•	WCT/ สำหรับ Contract, WCL/ สำหรับ Claim

Mail/Cron
	•	Template แจ้งเตือนก่อนหมดอายุ X วัน (อ่านจาก settings) ส่งให้ partner + ผู้ดูแล
	•	Cron รายวัน loop contracts active ที่จะหมดอายุภายใน X วัน

Security
	•	กลุ่ม:
	•	group_buz_warranty_user (อ่าน/สร้าง/เขียนบางส่วน)
	•	group_buz_warranty_manager (จัดการทั้งหมด + settings)
	•	ir.model.access.csv ครอบคลุมทุกโมเดลใหม่ + inherit ที่จำเป็น
	•	Record rules เคารพ company_id

Tests (จำเป็น)

tests/test_warranty_rma_flow.py ครอบคลุม:
	1.	Create warranty contract (in-warranty) → create claim → action_receive_rma() → validate inbound → state=rma_in
	2.	action_create_repair() → set repair done → action_return_to_customer() → validate outbound → state=done
	3.	Out-of-warranty: ใส่ claim_cost_line_ids → action_create_invoice() → invoice posted → action_mark_done()
	4.	Replacement flow: action_create_replacement() → validate outbound (เลือก lot ใหม่) → done
	5.	Constraints: ห้ามเปิดเคลมซ้อนสำหรับสัญญา/lot เดิมที่ยังเปิดอยู่, ห้ามสร้าง contract ซ้อนช่วงเวลา

README.md (ให้สร้างให้ครบ)
	•	ภาพรวม, Dependencies, ขั้นตอนติดตั้ง
	•	วิธีตั้งค่า Settings
	•	ตัวอย่าง 3 flow: Repair / Replacement / Out-of-warranty billing
	•	Tips: Multi-company, Serial domain, การกำหนด taxes, Pricelist (ถ้าใช้)

คุณภาพโค้ดที่ต้องการ
	•	โค้ด รันได้จริง บน Odoo 17: ไม่มี missing ref, ไม่มี view xpath พัง
	•	ใช้ API Odoo มาตรฐาน: create/write/onchange/compute/constraints
	•	ตรวจ error cases ด้วย UserError ที่อ่านง่าย
	•	เคารพ security (groups, access, rules)
	•	จัดระเบียบไฟล์และคอมเมนต์สั้น ๆ ชัดเจน