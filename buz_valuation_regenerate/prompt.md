บทบาท: คุณคือผู้เชี่ยวชาญ Odoo 17 (ทั้ง Inventory/Accounting) และนักพัฒนาโมดูลระดับ Production. จงสร้างโมดูล Odoo 17 ชื่อเชิงเทคนิค buz_valuation_regenerate ที่สามารถ “ลบและสร้างใหม่” Stock Valuation Layer (SVL) และ Journal Entries ที่เกี่ยวข้อง สำหรับสินค้า/ช่วงเวลา/บริษัทที่เลือก โดยมีโหมด Dry-run, สำรองข้อมูลย้อนกลับได้ และรองรับเคส Landed Costs.

1) ข้อมูลโมดูล

Name: Re-Generate Valuation & Entries

Technical name: buz_valuation_regenerate

Version: 17.0.1.0.0

License: LGPL-3

Depends: stock, account, stock_landed_costs

Installable: True, Application: False

Multi-company safe

2) Use cases หลัก

บน Product Form มี Action ปุ่ม “Re-Generate Valuation Layer” เพื่อ:

ลบ SVL เก่าของสินค้านั้นตามช่วงวันที่เลือก แล้ว คำนวณและสร้างใหม่

ลบ account.move (Journal Entry) ที่ผูกกับ SVL เก่า แล้ว สร้างใหม่ ให้ถูกต้อง

รองรับกรณีที่ SVL เดิมถูกสร้างจาก Landed Costs (ต้องคงความสัมพันธ์และผลกระทบของ LC)
(อ้างอิงฟีเจอร์หลักจากแอปต้นแบบที่ระบุว่าปุ่มนี้ “Delete old valuation layer and re-create it” และ “Delete old entry move and re-create it” รวมถึงพิจารณา Landed Costs), 
Odoo Apps Store

เมนู Inventory → Configuration → Valuation Tools → Valuation Regenerator สำหรับทำแบบ batch (หลายสินค้า/หลายหมวด/ทั้งบริษัท)

3) Wizard & UI/UX

สร้าง wizard ชื่อ valuation.regenerate.wizard เปิดได้จาก:

Product > Action “Re-Generate Valuation Layer”

เมนู Tools ด้านบน

ฟิลด์ใน Wizard

company_id (required, default current)

Target scope:

mode = product | category | domain

ถ้า product: product_ids (m2m)

ถ้า category: categ_ids (m2m)

ถ้า domain: domain_str (char, safe_eval)

วันที่: date_from, date_to (optional; ถ้าเว้นว่าง = ทั้งหมดของสินค้า)

ตัวเลือก:

rebuild_valuation_layers (bool, default True)

rebuild_account_moves (bool, default True)

include_landed_cost_layers (bool, default True)

recompute_cost_method (selection: auto | fifo | avco, default auto → อ่านจาก product.category)

dry_run (bool, default True) → คำนวณแผนที่ต้องลบ/สร้าง โดยไม่แตะข้อมูล

force_rebuild_even_if_locked (bool, default False) → ถ้า period/accounting lock ห้ามทำจริง ให้ raise แทน

post_new_moves (bool, default True) → โพสต์ JE ใหม่ทันที (ถ้า False ให้เป็น draft)

notes (text)

Readonly preview grids:

line_preview_ids: แสดง SVL/JE ที่จะถูกลบ+สร้างใหม่ พร้อม diff ก่อน-หลัง

ปุ่มใน Wizard

Compute Plan (Dry-run): คำนวณผลกระทบ, เติม preview ตาราง, ไม่เขียนฐานข้อมูล

Apply Regeneration: ทำจริงตามแผน (ต้องไม่มี lock และผ่าน validations)

4) หลักการคำนวณ/ความถูกต้อง

รองรับ Automatic inventory valuation ของ Odoo: เมื่อสร้าง SVL/เคลื่อนไหว ระบบจะสร้าง JE ให้สัมพันธ์กัน (ใช้บัญชีจาก Product Category) 
Odoo

รองรับ FIFO/AVCO:

FIFO: เดินตามลำดับ SVL รับเข้า → จับคู่เบิกออกใหม่ เพื่อให้ cost ถูกต้อง

AVCO: คำนวณค่าเฉลี่ยถ่วงน้ำหนักใหม่จาก stock moves/valuation layers ในช่วงที่เลือก

Landed Costs:

ถ้า SVL เคยถูกปรับด้วย LC ให้คงผลกระจายต้นทุนเดิมหรือคำนวณกระจายใหม่ตามค่าคอนฟิกของ LC ที่ validate แล้ว (อย่าทำลายความสัมพันธ์ LC → SVL) — ฟีเจอร์แอปต้นแบบระบุให้ “consider layers created from landed cost”. 
Odoo Apps Store

ปลอดภัยกับ multi-company: filter ตาม company_id, currency conversion ตาม company currency

ตรวจ lock dates / tax lock / fiscal lock: ถ้าอยู่ในช่วง lock ให้บล็อก (raise UserError) เว้นแต่ติ๊ก override (แต่ยังต้องเคารพสิทธิ์ Access ระดับบัญชี)

เคารพ stock rules / ไม่แก้ stock.move state/history ที่ไม่เกี่ยว

ไม่แตะ entries ที่อยู่นอก scope (วันที่/สินค้า/บริษัท) เพื่อกัน side-effect

5) ขั้นตอนอัลกอริทึม (Apply Regeneration)

Validation: สิทธิ์ผู้ใช้ (Inventory/Accounting Manager), period lock, company

Build scope: ค้น product.product ตาม mode + วันที่ หา SVL/JE เป้าหมาย

Backup: บันทึก snapshot ของ SVL และ account.move ที่จะลบทิ้ง (ลง model log ของเราแบบ JSON blob)

Unlink accounting moves ที่เกี่ยว (ถ้า rebuild_account_moves) — เฉพาะที่ system สร้างจาก valuation เท่านั้น

Unlink SVL เดิม (ถ้า rebuild_valuation_layers)

Recompute:

อ่าน stock moves ที่ส่งผลต้นทุนในช่วงนั้น (incoming/internal/production/return ฯลฯ)

สร้าง SVL ใหม่ตามตรรกะ FIFO/AVCO + นำ LC allocation มาคิด

สำหรับแต่ละ SVL ใหม่ สร้าง account.move ใหม่ โดยดึงบัญชี valuation/price diff จาก Product Category/Company

Post JE ใหม่ (ตาม post_new_moves)

สร้าง diff report (ก่อน/หลัง): qty, unit_cost, value, move_ids ที่ได้รับผล, JE refs

Log & message_post ไปยัง product(s) ที่เกี่ยว, แนบ CSV รายงานผล

6) Model เสริมสำหรับ Audit/Undo

valuation.regenerate.log:

header: user, company, executed_at, scope (product/category/domain + dates), options (dry_run/post_new_moves/etc.)

lines (one2many): เก็บข้อมูลเดิม/ใหม่ของแต่ละ SVL/JE (JSON fields: old_payload, new_payload)

attachment: ไฟล์ CSV diff

ปุ่ม Export CSV, View Impacted Moves

(ถ้าทำได้) ปุ่ม Rollback: อ่าน snapshot แล้วพยายาม revert (optional; safe best-effort)

7) ความปลอดภัย/สิทธิ์

กลุ่ม: Inventory Manager, Accounting Manager เท่านั้นที่เห็นปุ่ม/เมนูนี้

record rules/ACL ครอบคลุม wizard + log

8) หน้าจอ/เมนู/ปุ่ม

Product form: smart action “Re-Generate Valuation Layer”

Menu: Inventory → Configuration → Valuation Tools → Valuation Regenerator

Wizard views (form+tree preview), Log views (tree/form), Search filters ตามวันที่/สินค้า/ผู้ใช้

9) โครงไฟล์ที่ต้องส่งมอบ
buz_valuation_regenerate/
├── __init__.py
├── __manifest__.py
├── README.md
├── SECURITY.md
├── security/
│   ├── ir.model.access.csv
│   └── security.xml
├── data/
│   ├── menu.xml
│   └── server_actions.xml   (หากมี)
├── views/
│   ├── product_views.xml    (เพิ่ม action/button)
│   ├── wizard_views.xml
│   ├── log_views.xml
│   └── menus.xml
├── models/
│   ├── valuation_regenerate_wizard.py
│   └── valuation_regenerate_log.py
├── report/
│   └── templates.xml        (ถ้าทำรายงาน QWeb/CSV export action)
├── i18n/
│   └── th.po
└── tests/
    ├── test_fifo.py
    ├── test_avco.py
    ├── test_landed_cost.py
    └── test_multicompany_lock.py

10) โค้ดสำคัญ (แนวทางภายในไฟล์)

ใน valuation_regenerate_wizard.py:

method action_compute_plan() → สร้าง preview (dry-run)

method action_apply() → ทำจริง: validate → backup → unlink JEs/SVLs → recompute → create JEs → post → log

helper สำหรับ:

คัด SVL ตาม product/company/date

อ่าน config บัญชีจาก Product Category

เดินคิว FIFO ใหม่ และสูตร AVCO

รวม/กระจาย Landed Costs ที่เกี่ยว

currency rounding ตาม company.currency_id

ใน valuation_regenerate_log.py:

เก็บ snapshot JSON, สร้าง attachment CSV (ใช้ base64, io.StringIO)

11) ข้อควรระวัง & Guardrails

อย่าลบ JE ที่ผู้ใช้ทำเอง; ลบเฉพาะ JE ที่ผูกกับ SVL/stock valuation เท่านั้น

เคารพ account.fiscal.year และ lock dates; ถ้าตรง lock ให้ raise ชัดเจน

ปริมาณข้อมูลเยอะ: ใช้ batch และ SQL optimize จุดที่เหมาะสม

ใส่ warnings กรณี on-hand เป็นศูนย์ในบางช่วง (revalue ย้อนหลังอาจไม่สมเหตุผล)

เพิ่มระบบ message_post แจ้งใน chatter ของ Product และแนบสรุปผล

12) เอกสาร/README

อธิบายความสามารถ เทียบกับแนวคิดจากแอปบน Apps (ปุ่ม Action “Re-Generate Valuation Layer” จะลบ-สร้าง SVL/JE ใหม่ และคำนึง Landed Costs) พร้อมคำเตือนให้ทดสอบบน staging ก่อนใช้งานจริง. 
Odoo Apps Store

ลิงก์อ้างอิงแนวคิด valuation อัตโนมัติของ Odoo 17 (official docs) เพื่อความเข้าใจผู้ใช้ปลายทาง. 
Odoo

แนะนำติดตั้งร่วมกับเครื่องมือวิเคราะห์อย่าง Stock Valuation Layer Usage (OCA) เพื่อ trace ที่มา/ที่ไปของชั้นต้นทุน. 
Odoo Community Association (OCA)

13) ทดสอบอัตโนมัติ (pytest)

FIFO case: รับเข้า 2 batch ราคาต่าง, เบิกออก, regenerate ย้อนช่วงกลาง → ตรวจ unit_cost/remaining qty/JE เท่าที่ควร

AVCO case: หลาย receipt & internal moves, regenerate → ค่าเฉลี่ยถูกต้อง

Landed Cost: มี LC 1 ใบ กระจาย 3 สินค้า → regenerate แล้วยังคง weight/amount allocation ถูก

Multi-company & currency

Locked period → ต้อง raise

Dry-run ไม่แตะฐานข้อมูล

ส่งมอบทั้งหมดเป็นโค้ด Production-ready + README + tests + i18n (th.po).

ทำไมสเปคนี้ครอบคลุมของต้นแบบ

ระบุชัดว่า ปุ่มบน Product Action = Re-Generate Valuation Layer ที่ “ลบ-สร้างใหม่” ทั้ง SVL และ Journal Entry และ “พิจารณา Landed Costs” ตรงกับคำอธิบายบนหน้าแอปต้นฉบับ, 
Odoo Apps Store

ผนวกแนวปฏิบัติจาก Automatic inventory valuation ของ Odoo 17 เพื่อให้การสร้าง JE ใหม่สอดคล้องเอกสารทางการ, 
Odoo

แนะนำใช้ OCA stock_valuation_layer_usage เพื่อช่วย trace และดีบักต้นทุนก่อน/หลัง regenerate.