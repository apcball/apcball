สร้างโมดูล Odoo 17 ชื่อ stock_fifo_by_location โดยทำตามข้อกำหนดต่อไปนี้อย่างเข้มงวด — ให้ผลลัพธ์เป็นโค้ดพร้อมติดตั้ง (module folder พร้อมไฟล์ทั้งหมด) และรวม unit tests, migration script, README, และตัวอย่างการทดสอบ manual ด้วย

สรุปฟังก์ชันหลัก (goal)

เพิ่มการจัดการ FIFO แบบแยก queue ต่อ location: แต่ละ stock.valuation.layer ต้องมี location_id เพื่อให้เราสามารถคำนวณ COGS ตาม FIFO เฉพาะโลเคชันที่สินค้านั้นอยู่ได้

ต้องทำงานร่วมกับ Odoo 17 stock + stock_account (หรือโมดูลบัญชีที่เกี่ยวข้อง) และยังคงรักษาความถูกต้องของ journal entries

ข้อกำหนดเชิงเทคนิค (must-have)

Manifest

name: Stock FIFO by Location

depends: ['stock', 'stock_account']

compatible กับ Odoo 17

Add field

เพิ่ม location_id = fields.Many2one('stock.location') ใน model stock.valuation.layer (_inherit = 'stock.valuation.layer')

Field ต้องมี index และ help text

การสร้าง SVL (valuation layers)

หาจุดที่ Odoo 17 สร้าง stock.valuation.layer (ใช้ method/flow ที่แท้จริงของ Odoo 17) แล้วแก้ไข/override ให้เมื่อตอนรับเข้า/สร้าง layer ระบบใส่ค่า location_id ที่ถูกต้องโดยอิงจาก stock.move หรือ stock.move.line (สำหรับ incoming → ใช้ destination location, สำหรับ outgoing → ใช้ source location, สำหรับ internal transfer → ขึ้นกับนโยบาย แต่ต้องกำหนดชัดเจน)

หากมีจุดที่สร้าง SVL หลายจุด ให้แก้ทุกจุดให้ consistent

FIFO per-location logic

เขียน service/helper ที่ดึง FIFO queue เฉพาะ location_id (เรียงตาม create_date / oldest first) และคำนวนการใช้ชั้น (layer) สำหรับการลดสต็อกเมื่อออกขายหรือ validate picking

เมื่อใช้ layer ใด ต้อง update/สร้าง accounting entries ให้ถูกต้อง (ใช้ existing mechanisms ของ stock_account ถ้าเป็นไปได้ แต่ปรับให้ใช้ location_id ในการเลือก layer)

Behavior policy on shortage

กำหนดพฤติกรรมเมื่อสต็อกไม่พอในโลเคชันที่ระบุ (choose one and implement):

A) Raise an error and block validation (default safety), และ provide config option to allow fallback to other locations

B) (optional) If fallback allowed, pull from other locations following company policy (documented)

Implement this as a setting in module settings (ir.config_parameter or menu setting)

Migration script

สร้าง script (server action / script runnable from Odoo shell) เพื่อ populate location_id สำหรับ existing stock.valuation.layer:

Preferentially derive from linked stock.move or stock.move.line (incoming -> location_dest_id, outgoing -> location_id)

Log or list items that cannot be resolved for manual review

Unit & Integration Tests

สร้าง tests (pytest / Odoo test framework) ครอบคลุม:

Incoming receipt → SVL created with correct location_id

Internal transfer → expected SVL behavior (depending on chosen policy)

Outgoing sale from specific location → COGS drawn from FIFO queue of that location

Shortage in location → raising error (and if fallback configured — pulling from fallback)

Returns, scrap, inventory adjustments → correct SVL and accounting results

Tests must assert journal entries (COGS) correctness and that cost calculations match expected FIFO results

Edge cases

Negative quantity layers, partial consumption across multiple layers, rounding issues, multicompany boundary conditions

Document how module behaves with multi-company and multi-warehouse; if unsupported, mention explicitly

Code quality

Pythonic, PEP8-compliant, use Odoo ORM idioms (no raw SQL unless necessary and justified)

Add docstrings/comments for complex logic

Use contexts correctly where needed (e.g., passing location via context when creating SVL)

Do not break existing Odoo APIs — prefer inheritance/extension

Security

Add ir.model.access.csv entries for new model fields if needed

Ensure no unauthorized access to sensitive accounting operations

README

How it works, install instructions, config options, migration steps, testing steps, known limitations, and example flows (incoming → internal → outgoing)

Deliverables

Module folder stock_fifo_by_location/ with all files

__manifest__.py

models/ with stock_valuation_layer.py, stock_move.py (or files with actual method overrides used)

security/ir.model.access.csv

tests/ with pytest tests

migrations/ or script for populating location_id

README.md

Optional: example Odoo server action / CLI command to run migration

Acceptance criteria (what I will check)

 Module installs cleanly on Odoo 17 with stock and stock_account installed

 After receiving incoming goods to Location A, stock.valuation.layer records have location_id = Location A

 When validating a delivery (sale) coming from Location A, consumed layers are taken from FIFO queue of Location A only

 If Location A lacks enough qty, module blocks or follows configured fallback (matching chosen policy)

 Accounting entries (COGS, inventory valuation) reflect amounts based on the used FIFO layers

 Tests pass (pytest / Odoo test runner) and demonstrate the scenarios above

 Migration script populates legacy SVL location_id correctly for typical moves

Extra: Example unit test scenario (include as test)

Setup product P, two incoming receipts:

Receipt 1 (2025-01-01) to Location A: qty 10, unit cost 100 → SVL1 (loc A)

Receipt 2 (2025-01-10) to Location A: qty 5, unit cost 120 → SVL2 (loc A)

Validate sale from Location A for qty 12:

Expect: consume 10 from SVL1 and 2 from SVL2

COGS should = 10100 + 2120 = 1000 + 240 = 1240

Journal entries must match above amounts

Test asserts consumed SVL remaining quantities and posted journal lines

Tone for code generator

Produce runnable, production-considerate code (not pseudo-code). If some Odoo internal method names differ, adapt to Odoo 17 conventions but ensure correctness. If a single-file change is insufficient, modify all necessary call sites where stock.valuation.layer is created.