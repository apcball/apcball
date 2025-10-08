# 🎯 Objective

พัฒนาโมดูล Odoo 17 สำหรับ “เบิกของสิ้นเปลืองจากคลัง” (Internal Consumption Request) รองรับการอนุมัติหลายชั้น, ผูกคลัง/บัญชี, ตัดสต็อกจริง และบันทึกบัญชีอัตโนมัติ **Debit: ค่าใช้จ่ายสำนักงาน / Credit: สินค้าคงคลัง** พร้อมรายงานการใช้งานตามแผนก/โครงการ

---

## ✅ Scope & Deliverables

- โมเดล `ic.request` + `ic.request.line` จัดการคำขอเบิกของ
- เวิร์กโฟลว์: `draft → submitted → manager_approved → store_done → accounted → canceled`
- ปุ่มและ Wizard:
  - Submit for Approval, Approve, Reject, Done (Issue), Create Accounting Entry, Cancel
  - Optional: Multi-approve (ตามวงเงิน), Partial Issue (เบิกบางส่วน)
- สร้าง **Stock Move (Internal Transfer หรือ Scrap)** อัตโนมัติเมื่อ Done
- สร้าง **Account Move** อัตโนมัติเมื่อ Issue (หรือใช้ valuation อัตโนมัติหากเป็น Real-Time Valuation)
- ตั้งค่าบัญชี/คลังระดับ Category/Department/Line และรองรับ Analytic Account/Tags
- รายงานสรุปการใช้สิ้นเปลือง (by product, department, analytic, period)
- Security/Access, Menu/Action, Sequence, Demo Data, Tests

---

## 🔧 Dependencies & Tech

- Odoo 17 (Community)
- Addons: `stock`, `account`, `mail`, `approvals` (หรือใช้ approval logic เอง), `hr` (ถ้าจะผูกแผนก), `analytic`
- ชื่อโมดูล: `buz_internal_consumption`

---

## 🧱 Data Model

### `ic.request` (Header)

- `name` (Char, readonly): เลขที่เอกสาร `IC/%(year)s/%(seq)s`
- `date_request` (Date, required, default=Today)
- `requester_id` (Many2one res.users, required)
- `department_id` (Many2one hr.department, optional)
- `analytic_account_id` (Many2one account.analytic.account, optional)
- `analytic_tag_ids` (Many2many account.analytic.tag)
- `location_id` (Many2one stock.location, required): ต้นทาง (คลังจ่าย)
- `dest_location_id` (Many2one stock.location, default = Location ประเภท “Internal Use/Consumption”)
- `expense_policy` (Selection): `valuation_based` | `standard_cost` | `fifo_layer`
- `journal_id` (Many2one account.journal, domain type='general')
- `state` (Selection): `draft, submitted, manager_approved, store_done, accounted, canceled`
- `line_ids` (One2many ic.request.line)
- `amount_total_cost` (Monetary, compute): มูลค่าทั้งหมดจากต้นทุนสินค้าที่จะตัด
- `note` (Text)
- Chatter: `message_follower_ids`, `activity_ids`

### `ic.request.line`

- `request_id` (Many2one ic.request)
- `product_id` (Many2one product.product, required, domain: stockable products)
- `uom_id` (Many2one)
- `qty` (Float, required, >0)
- `available_qty` (Float, related/compute จาก location\_id)
- `expense_account_id` (Many2one account.account, optional)
- `analytic_account_id` (Many2one, optional)
- `analytic_tag_ids` (Many2many, optional)
- `unit_cost` (Monetary, compute ตาม policy)
- `subtotal_cost` (Monetary = qty \* unit\_cost)
- `move_id` (Many2one stock.move, readonly)
- `move_line_ids` (One2many stock.move.line, readonly)
- `valuation_layer_ids` (Many2many stock.valuation.layer, readonly)

---

## ⚙️ Configuration

- **Product Category**: กำหนด `Expense Account` (เช่น 521101 Office Supplies), `Stock Valuation` settings (real-time vs periodic), `Stock Input/Output`
- **Company Settings (โมดูลนี้)**:
  - Default Expense Account (fallback)
  - Default Consumption Location (เช่น `WH/Consumption`)
  - Default Journal for Manual JE (เช่น Miscellaneous)
  - Costing Policy default: `valuation_based`
- **Department Mapping (optional)**: ผูก department → analytic account/analytic tags
- **Approval Rules**: กำหนดวงเงิน/ระดับอนุมัติ (manager, finance) และเงื่อนไขพิเศษ (เช่น qty เกิน threshold)

---

## 🛠️ Business Logic

### การคำนวณต้นทุน (เลือกหนึ่งหรือรองรับทั้งหมดผ่าน policy)

1. **valuation\_based**: ใช้กลไก Odoo เอง หาก Category ตั้งเป็น Real-Time Valuation (FIFO/AVCO) → เมื่อ Scrap/Issue จะเกิด valuation entry อัตโนมัติ
2. **standard\_cost**: ใช้ standard\_price ของ product (เหมาะกับ periodic valuation)
3. **fifo\_layer**: ดึงต้นทุนจาก `stock.valuation.layer` ตาม FIFO แบบ custom (กรณีต้องตัดตาม lot/batch/วันที่รับเข้า)

### บัญชี (ตัวอย่างไทย)

- **Debit**: 521101 Office Supplies Expense (หรือดึงจาก line/department/category)
- **Credit**: 141101 Inventory (หรือ Stock Valuation Account ของ Category)
- รองรับ Analytic Account/Tags จาก header/line

### เวิร์กโฟลว์หลัก

- **Submit**: ตรวจความถูกต้อง → สร้างกิจกรรมอนุมัติให้ Manager
- **Approve**: ล็อกแก้ไข, อนุญาตคลังออกของ
- **Issue (Store Done)**:
  - สร้าง `stock.move` ประเภท Internal Transfer จาก `location_id` → `dest_location_id` (หรือสร้าง `stock.scrap` per line)
  - Validate move → บันทึก qty จริง (รองรับ partial)
- **Accounting**:
  - หาก Category เป็น Real-Time → ระบบสร้าง valuation entry อัตโนมัติอยู่แล้ว (สามารถ map analytic)
  - หาก **ไม่** Real-Time → โมดูลนี้สร้าง `account.move` เอง:
    - Lines ต่อรายการ/สรุปตาม expense account
    - Debit: Expense (analytic) / Credit: Inventory
    - วันที่เอกสาร = `date_request` หรือ `date_done`
- **Cancel**: ย้อนสถานะ, Unlink stock moves หากยังไม่ done, ยกเลิก JE หากยังไม่ posted

### Partial Issue & Backorder

- อนุญาตจ่ายบางส่วน → ปรับ `qty_done` ใน move line → บันทึกต้นทุนเฉพาะส่วนที่จ่าย

### กติกา & Validation

- qty ≤ available\_qty ที่ `location_id`
- ต้องเลือกอย่างน้อย 1 line
- หากใช้ manual JE: ห้ามโพสต์บัญชีซ้ำ, ตรวจ policy ต้นทุนถูกกำหนด
- ป้องกันแก้ไขหลัง approve/done (except ผู้มีสิทธิ์)

---

## 🔐 Security & Access

- กลุ่มสิทธิ์:
  - `IC User`: สร้าง/แก้ไขของตัวเอง, submit
  - `IC Manager`: อนุมัติ/ปฏิเสธ, ปรับแก้บางฟิลด์, ชุดอนุมัติ
  - `IC Store`: ทำ Issue/Validate Stock Move
  - `IC Accountant`: Create/Validate Account Move
- record rules แยกตาม requester/department หากต้องการ

---

## 🧭 Menus & Actions

- **Inventory → Internal Consumption**
  - Requests (Tree/Form/Kanban)
  - Reports
  - Configuration (Settings, Approval Rules)

---

## 🖼️ UI/Views (สรุป)

- Form `ic.request`:
  - Header: requester, date, department, analytic, locations, policy, journal
  - Lines (tree editable): product, qty, uom, available, expense\_account, analytic, unit\_cost, subtotal
  - Chatter + Smart Buttons: Stock Moves, Journal Entries, Valuation Layers
  - Buttons: Submit, Approve, Reject, Issue, Create JE, Cancel
- Filter/Group by: state, department, analytic, requester, product

---

## 🧮 Accounting Details

- Mapping ลำดับชั้น (priority): line.expense\_account\_id → department mapping → category expense account → company default
- JE line-level analytic: ดึงจาก line หากมี, ไม่งั้นจาก header
- กรณี Real-Time Valuation: เพิ่ม hook map analytic ไปยัง valuation move lines (สืบทอด stock.move.\_account\_entry\_move)

---

## 🧰 Python Methods (หลัก ๆ)

- `action_submit()` → set state, activity
- `action_approve()` → validations, set state
- `action_issue()` → สร้าง/validate stock.move ต่อ line (หรือ scrap) + เข้าสู่ `store_done`
- `action_create_account_move()` → หากต้องทำ JE manual → สร้าง `account.move` จากยอดต้นทุนจริง + analytic
- `action_cancel()` → ย้อนสถานะ, ยกเลิกเอกสารที่เกี่ยวข้องตามสิทธิ์
- `_compute_unit_cost()` / `_get_fifo_cost()` / `_get_standard_cost()`
- `_prepare_move_vals(line)` / `_prepare_account_move_vals(grouped)`

---

## 🧪 Tests (สำคัญ)

- สร้าง request + lines ครบเงื่อนไข, approve, issue, create JE → ยอดบัญชีถูกต้อง
- Real-Time vs Periodic valuation (เปิด/ปิด) ให้ผ่านทั้งสองโหมด
- Partial issue และ backorder ยังถูกต้อง
- Analytic mapping ถูกต้องเมื่อกำหนดที่ header/line
- Permission: user ทำไม่ได้, manager ทำได้, accountant โพสต์ JE ได้

---

## 🧾 QWeb Reports

- IC Request Form (PDF): รายละเอียดสินค้า/ต้นทุน/อนุมัติ
- Consumption Summary (XLSX): period, department, analytic, product

---

## 📦 Data & Files

- `data/sequence.xml` → `IC/%(year)s/%(seq)s`
- `security/ir.model.access.csv` for groups
- `views/ic_request_views.xml`, `views/menu.xml`, `views/settings.xml`
- `report/ic_request_report.xml`, `report/ic_summary_xlsx.py`

---

## 🗂️ Directory Template

```
buz_internal_consumption/
├─ __init__.py
├─ __manifest__.py
├─ security/
│  ├─ ir.model.access.csv
│  └─ security.xml
├─ data/
│  ├─ sequence.xml
│  └─ ic_settings_data.xml
├─ models/
│  ├─ __init__.py
│  ├─ ic_request.py
│  └─ res_company.py
├─ views/
│  ├─ ic_request_views.xml
│  ├─ ic_settings_views.xml
│  └─ menu.xml
├─ report/
│  ├─ ic_request_report.xml
│  └─ ic_summary_xlsx.py
└─ README.md
```

---

## 📝 `__manifest__.py` (ตัวอย่าง)

```python
{
    "name": "Internal Consumption Request",
    "version": "17.0.1.0.0",
    "summary": "Internal consumption with approval, stock moves, and accounting",
    "author": "Ball/MOGEN + Buz",
    "depends": ["stock", "account", "mail", "approvals", "analytic", "hr"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/sequence.xml",
        "views/ic_settings_views.xml",
        "views/ic_request_views.xml",
        "views/menu.xml",
        "report/ic_request_report.xml",
    ],
    "application": True,
}
```

---
