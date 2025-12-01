ช่วยเขียนโค้ด Odoo 17 โมดูล custom ชื่อ `stock_fifo_by_warehouse_recal` โดยมีคุณสมบัติและโครงสร้างดังนี้:

**ภาพรวมโมดูล**
- โมดูลนี้ทำงานร่วมกับ logic FIFO by warehouse ที่ผมมีอยู่แล้ว (ใช้ `warehouse_id` บน `stock.valuation.layer` และ override FIFO ให้ตัด per warehouse)
- สร้าง wizard สำหรับ "Recalculate FIFO by Warehouse" เพื่อใช้ในงานปิดงบ / แก้ layer พัง / ทำ clean up ข้อมูล
- wizard ต้องสามารถ:
  - เลือกช่วงวันที่ (date_from, date_to)
  - เลือก warehouse หลายตัวได้
  - เลือก products หรือ product categories ได้
  - ทำ preview ผลกระทบก่อน apply จริง
  - เวลา apply สามารถลบ layer เก่า แล้วสร้าง layer ใหม่ตาม logic FIFO by warehouse
  - lock layer ที่ถูก recal แล้ว เพื่อไม่ให้ recal ซ้ำอีก

---

### 1. โครงสร้างโมดูล

สร้างโฟลเดอร์และไฟล์ให้ครบ:

- `__init__.py`
- `__manifest__.py`
- โฟลเดอร์ `models/__init__.py`
- ไฟล์ `models/fifo_recalculation_wizard.py`
- โฟลเดอร์ `views/` พร้อมไฟล์ `views/fifo_recalculation_wizard_views.xml`
- ถ้าจำเป็นให้เพิ่ม security (record rule / access) ขั้นพื้นฐานสำหรับ stock manager

ใน `__manifest__.py`:
- name: "FIFO Recalculation by Warehouse"
- depends: `stock`, `stock_account` และ module custom FIFO ที่ผมมี (สมมติชื่อ `stock_fifo_by_warehouse`)
- data: โหลดไฟล์ view wizard + security ถ้ามี

---

### 2. Model: Stock Valuation Layer (เพิ่ม field lock)

ให้สืบทอด model `stock.valuation.layer` (แบบ `_inherit`) เพื่อเพิ่ม field:

- `locked = fields.Boolean(
    string='Locked',
    default=False,
    index=True,
    help='If checked, this layer will not be recalculated again by FIFO recalculation tools.'
  )`

ห้ามแก้ logic core อื่น ๆ ใน model นี้ นอกจากเพิ่ม field และใช้ใน domain ของ wizard เท่านั้น

---

### 3. Wizard หลัก: `fifo.recalculation.wizard`

สร้าง transient model:

- `_name = 'fifo.recalculation.wizard'`
- `_description = 'Recalculate FIFO by Warehouse'`

fields:

- `date_from = fields.Datetime(string='Start Date', required=True)`
- `date_to = fields.Datetime(string='End Date', required=True)`
- `warehouse_ids = fields.Many2many('stock.warehouse', string='Warehouses', help='Leave empty for all warehouses')`
- `product_ids = fields.Many2many('product.product', string='Products', help='Leave empty for all products')`
- `product_categ_ids = fields.Many2many('product.category', string='Product Categories', help='Filter products by categories')`
- `company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company, required=True)`
- `dry_run = fields.Boolean(string='Dry Run (No Commit)', default=True, help='If checked, system will simulate recalculation without modifying any valuation layer.')`
- `clear_old_layers = fields.Selection([
      ('none', 'Do not touch existing layers'),
      ('range', 'Delete & Rebuild in selected date range'),
      ('all_product', 'Delete all layers for selected products'),
  ], string='Existing Layers Handling', default='range')`
- `lock_after_recal = fields.Boolean(string='Lock new layers after recalculation', default=True)`
- `state = fields.Selection([
      ('draft', 'Draft'),
      ('preview', 'Preview'),
      ('done', 'Done'),
  ], default='draft')`
- `log_text = fields.Text(string='Log', readonly=True)`
- `line_ids = fields.One2many('fifo.recalculation.wizard.line', 'wizard_id', string='Preview Lines', readonly=True)`

methods สำคัญ:

1. `action_preview(self)`  
   - เคลียร์ preview เดิม
   - หา stock.move โดย domain:
     - state = done
     - company_id = wizard.company_id
     - date between date_from/date_to
     - filter product / category ถ้ามี
   - สำหรับทุก move คำนวณ warehouse ด้วย helper (`_get_move_warehouse()` ซึ่งเรียกใช้จาก module FIFO by warehouse ที่มีอยู่แล้ว)
   - group move ตามคู่ `(product_id, warehouse_id)`
   - เรียก helper `_simulate_fifo(groups)` เพื่อจำลองผล FIFO ใหม่ แล้วสร้าง preview lines

2. `_simulate_fifo(self, groups)`  
   - `groups` เป็น dict: key = (product_id, warehouse_id), value = list ของ moves sorted ตามวันที่
   - สำหรับแต่ละ group:
     - อ่าน `stock.valuation.layer` เดิม (เฉพาะที่ `locked = False`) ตาม product+warehouse+company และช่วงวันที่ที่กำหนด
     - คำนวณ `qty_before` และ `value_before`
     - เรียก `_rebuild_fifo_for_group(moves, product_id, warehouse_id)` เพื่อ simulate FIFO ใหม่ (ไม่เขียน DB)
     - ได้ `qty_after`, `value_after` แล้วสร้าง record `fifo.recalculation.wizard.line` เพื่อแสดง diff

3. `_rebuild_fifo_for_group(self, moves, product_id, warehouse_id)`  
   - ทำงานใน memory ไม่แตะ DB
   - ใช้ list ของ dict สำหรับถือ in-layers เช่น `{'qty': x, 'unit_cost': y}`
   - loop moves ตามลำดับ:
     - ใช้ helper `_classify_move_and_get_cost(move, warehouse_id)` เพื่อรู้ว่าการเคลื่อนไหวของ move นี้:
       - เป็น in หรือ out
       - quantity ที่ใช้
       - cost / value ที่ควรใช้ใน FIFO (reuse logic จาก module FIFO by warehouse เดิม)
     - ถ้า in → append layer
     - ถ้า out → consume layer ตาม FIFO (ลด qty layer, pop เมื่อหมด)
   - return `(total_qty, total_value)` จาก layers สุดท้าย

4. `action_apply(self)`  
   - ถ้า `dry_run` = True → raise UserError แจ้งให้ user ปิดก่อน
   - ใช้ข้อมูลจาก `line_ids` เพื่อรู้ว่ามี (product, warehouse) ไหนบ้างที่ต้องจัดการ
   - เตรียม domain `stock.valuation.layer` สำหรับลบ layer เดิม:
     - product_id ในชุดที่เกี่ยวข้อง
     - warehouse_id ในชุดที่เกี่ยวข้อง
     - company_id = wizard.company_id
     - `locked = False` (ห้ามลบ layer ที่ล็อกแล้ว)
     - ถ้า `clear_old_layers == 'range'` → filter ตาม create_date ช่วง date_from/date_to
     - ถ้า `clear_old_layers == 'all_product'` → ไม่กรอง create_date
   - ลบ `old_layers.unlink()` ตาม domain
   - เรียก `_recreate_layers_for_groups(groups)` เพื่อสร้าง `stock.valuation.layer` ใหม่ตาม moves ที่คำนวณไว้
   - ถ้า `lock_after_recal` = True → write `{'locked': True}` ให้กับ layer ใหม่ที่สร้างจากรอบนี้
   - เปลี่ยน state wizard เป็น `done` และ append log_text

5. `_recreate_layers_for_groups(self, groups)`  
   - คล้าย `_simulate_fifo` แต่แทนที่จะใช้ list in memory ให้สร้าง `stock.valuation.layer` จริงใน DB
   - เวลาสร้าง layer ใหม่ ให้ใส่ field:
     - product_id
     - company_id
     - warehouse_id
     - quantity, value, unit_cost
     - remaining_qty (เท่ากับ quantity สำหรับ in-layer)
     - stock_move_id (ถ้า map ได้)
     - description (เช่นจาก picking/ move)
   - ไม่ต้องสร้าง account.move ใน scope แรก (แค่จัดการ SVL ก่อน) ให้โค้ดเขียนแบบที่สามารถต่อยอดสร้าง JE ได้ภายหลัง

ไม่ต้องเขียน logic ลึกมากใน `_classify_move_and_get_cost` ให้ทำ stub หรือคอมเมนต์ระบุว่า:
- ให้ reuse logic จาก module FIFO by warehouse ที่มีอยู่แล้ว

---

### 4. Preview Line Model

สร้าง transient model:

- `_name = 'fifo.recalculation.wizard.line'`
- `_description = 'Recalculated FIFO Preview Line'`

fields:

- `wizard_id = fields.Many2one('fifo.recalculation.wizard', required=True, ondelete='cascade')`
- `product_id = fields.Many2one('product.product', required=True)`
- `warehouse_id = fields.Many2one('stock.warehouse', required=True)`
- `qty_before = fields.Float(string='Qty Before')`
- `value_before = fields.Float(string='Value Before')`
- `qty_after = fields.Float(string='Qty After')`
- `value_after = fields.Float(string='Value After')`
- `diff_qty = fields.Float(string='Qty Diff')`
- `diff_value = fields.Float(string='Value Diff')`

---

### 5. View Wizard

สร้าง form view สำหรับ `fifo.recalculation.wizard`:

- ส่วน header/group:
  - company_id
  - date_from, date_to
  - warehouse_ids (many2many_tags)
  - product_ids (many2many_tags)
  - product_categ_ids (many2many_tags)
  - clear_old_layers
  - dry_run
  - lock_after_recal
- notebook 2 tab:
  - Tab "Preview":
    - tree view ของ line_ids แสดง:
      - product_id
      - warehouse_id
      - qty_before, value_before
      - qty_after, value_after
      - diff_qty, diff_value
  - Tab "Log":
    - field log_text (readonly, nolabel)
- footer ปุ่ม:
  - ปุ่ม `Preview` → `type="object" name="action_preview"` แสดงใน state draft/preview
  - ปุ่ม `Apply Recalculation` → `type="object" name="action_apply"` แสดงใน state preview เท่านั้น
  - ปุ่ม Close → `special="cancel"`

---

### 6. Action + Menu

สร้าง action window:

- `res_model = fifo.recalculation.wizard`
- `view_mode = form`
- `target = new`

สร้าง menu item ภายใต้เมนู Inventory (เช่นใน `stock.menu_stock_warehouse_mgmt`) ชื่อ "Recalculate FIFO"  
จำกัดสิทธิ์ให้ใช้ได้เฉพาะ group `stock.group_stock_manager` (หรือสร้าง group ใหม่เช่น `group_fifo_admin` ถ้าต้องการ)

---

### 7. คุณภาพโค้ด

- เขียนให้รองรับ multi-company ได้ (ใช้ company_id ตาม wizard)
- ใส่ docstring สั้น ๆ อธิบายแต่ละ method ว่าทำอะไร
- ใช้ ORM มาตรฐานของ Odoo ไม่เขียน raw SQL ยกเว้นจำเป็น
- ใส่ TODO comment ในจุดที่ผมต้องไปเติม logic เฉพาะ (เช่น `_classify_move_and_get_cost`)

ช่วยเขียนโค้ดให้ครบทุกไฟล์ตามรายละเอียดข้างต้น
พร้อมใช้งานใน Odoo 17 (Python 3, new API)
และจัด format ให้ตรงตามมาตรฐาน Odoo (4-space indentation, snake_case)