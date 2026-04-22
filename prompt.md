```markdown
# Odoo 17 Stock Check Module — AI Code Generation Prompt

## Role
You are a Senior Odoo 17 Developer. Generate a complete, production-ready Odoo 17 module
based on the requirements below. Output all Python, XML, and manifest files with full code.
Do not skip any file. Do not use placeholder comments like `# TODO` or `# add logic here`.

---

## Module Identity
- **Technical Name:** `buz_stock_check_enhanced`
- **Display Name:** Stock Check Enhanced
- **Version:** 17.0.1.0.0
- **Dependencies:** `stock`, `sale_management`, `product`, `web`
- **License:** LGPL-3

---

## Core Features Required

### 1. Warehouse & Location Selection (Header Filter Bar)
- Dropdown to select **Warehouse** (res.model: `stock.warehouse`)
- Dropdown to select **Location** filtered by selected warehouse
  - Default to internal locations only (`usage = 'internal'`)
- Both dropdowns must be **dynamic** — changing warehouse reloads location list
- Persist last selection per user using `ir.config_parameter` or session

### 2. Product Stock Table (Main View)
Display a list/table of products with the following columns:

| Column | Description |
|---|---|
| Checkbox | Multi-select toggle per row |
| Product Name | `product.product` display name |
| Internal Reference | `product.default_code` |
| On Hand Qty | `qty_on_hand` at selected location |
| **Actual Available Qty** | `qty_on_hand` MINUS `qty_reserved` (outgoing reserved) — NOT Odoo's default `virtual_available` |
| Incoming Qty | Confirmed incoming moves (`state in ('assigned','confirmed','waiting')`) filtered by selected location as destination |
| UoM | Unit of measure |
| Reorder Point | From `stock.warehouse.orderpoint` if exists |
| Select Qty | Editable numeric field for quotation quantity |

> ⚠️ CRITICAL: "Actual Available Qty" must be calculated as:
> `qty_on_hand - qty_reserved`
> where `qty_reserved` = sum of `reserved_availability` from outgoing `stock.move.line`
> Do NOT use `product.with_context(location=...).virtual_available`

### 3. Multi-Select & Quotation Creation
- **Select All** checkbox in table header
- Each row has individual checkbox
- A **"Create …
[22/4/2026  09:35] IamManow001101_bot: # prompt.md สำหรับ `stock_enhanced_checker`

นี่คือไฟล์ `prompt.md` ที่ให้ AI ตัวอื่นไปสร้าง module ต่อได้เลยบอล 👇

---

```markdown
# Prompt: Generate Odoo 17 Module — `stock_enhanced_checker`

## Role
You are a Senior Odoo 17 Developer. Generate a fully working Odoo 17 module
based on the requirements below. Output all Python and XML files with correct
structure, no placeholders, no pseudo-code.

---

## Module Identity
- **Technical Name:** `stock_enhanced_checker`
- **Display Name:** Stock Enhanced Checker
- **Version:** 17.0.1.0.0
- **Dependencies:** `stock`, `sale_management`, `product`
- **License:** LGPL-3

---

## Core Features

### 1. Stock Check Dashboard (Main UI)
- A dedicated menu item under **Inventory** named **"Stock Checker"**
- Built as an OWL component (client action) for a clean, modern UI
- Page layout:
  - **Top bar:** Warehouse selector (dropdown) + Location selector
    (dropdown, filtered by selected warehouse) + Search bar (product name / ref)
  - **Product list table** (see Section 2)
  - **Bottom action bar:** "Create Quotation" button (active only when
    ≥1 product is ticked)

### 2. Product List Table Columns
| Column | Description |
|---|---|
| ☑ Checkbox | Multi-select per row |
| Product Name | Linked to product form |
| Internal Ref | `product.default_code` |
| On Hand | `qty_available` at selected location |
| Reserved | `outgoing_qty` (reserved for existing orders) |
| **Available (Actual)** | `qty_available - outgoing_qty` — NOT the Odoo default "virtual available" |
| **Incoming** | Sum of confirmed PO lines not yet received (`purchase.order.line` where `state='purchase'` and `qty_received < product_qty`) |
| Qty to Quote | Editable number input per row (auto-filled when ticked) |
| Unit Price | Editable, pulled from product sales price |

### 3. Warehouse & Location Selector Behavior
- Warehouse dropdown loads all active warehouses (`stock.warehouse`)
- Location dropdown shows only **internal locations** under the selected
  warehouse's `lot_stock_id` (recursive children)
- Default: user's default warehouse + main stock location
- Changing warehouse resets location to that warehouse's default stock location
- All stock quantities must recalculate immediately on location change (no
  page reload — use RPC call)

### 4. Available Quantity Calculation (Critical)
```
actual_available = qty_on_hand_at_location - qty_reserved_at_location
```
- Use `stock.quant` to get `qty_on_hand` filtered by `location_id`
- Use `stock.move.line` with `state in ('partially_available','assigned')`
  to get reserved qty at that location
- **Do NOT use** `product.product`'s `virtual_available` field
- Display negative available qty in **red**

### 5. Incoming Stock Calculation
```
incoming_qty = SUM of (product_qty - qty_received)
               FROM purchase.order.line
               WHERE order_id.state = 'purchase'
               AND product_id = current product
               AND (qty_received < product_qty)
```
- Group by product, show total pending incoming quantity
- Tooltip on hover shows PO references (e.g., "PO/2024/0042, PO/2024/0055")

### 6. Multi-Select & Quotation Creation
- Checkbox on each row; "Select All" checkbox in header
- Ticking a row auto-populates `qty_to_quote` with `actual_available`
  (user can override)
- **"Create Quotation" button** behavior:
  1. Collect all ticked rows with `qty_to_quote > 0`
  2. Create a `sale.order` in **draft** state
  3. Add one `sale.order.line` per selected product with the entered qty
     and unit price
  4. Open the created quotation form in a new breadcrumb (do not navigate away)
  5. Show a success toast notification

### 7. Search & Filter
- Real-time search by product name or internal reference (debounce 300ms)
- Filter buttons: **All | In Stock | Out of Stock | Low Stock**
  (Low Stock = available < 5, configurable via Settings)
- "Low Stock Threshold" setting in **Inventory > Configuration > Settings**
  (integer field, default = 5)

### 8. Per[22/4/2026  09:14] Apichart Pangsalung: ช่วยออกแบบ module odoo17 สำหรับ เช็ค stock บน odoo มี config สามารถเลือก warehouse และ location ที่จะแสดงได้ มี UI ที่สวยงามน่าใช้ สามารถติ๊กเลือกได้หลายรายการและ กด create quotation ได้จากหน้า check stock ได้เลย หน้า สินค้าจะแสดงจำนวนที่ขายได้จริงไม่ติด จอง และ แสดงจำนวนที่จะเข้ามาเร็วๆนี้  เขียนเป็น prompt.md เพิ่อให้ ai generate module
[22/4/2026  09:18] IamManow001101_bot: # prompt.md สำหรับ AI ตัวอื่น

นี่คือไฟล์ `prompt.md` ที่เขียนเป็นภาษาอังกฤษทั้งหมดตามที่ขอ 👇

---

```markdown
# Odoo 17 Stock Check Module — AI Code Generation Prompt

## Role
You are a Senior Odoo 17 Developer. Generate a complete, production-ready Odoo 17 module
based on the requirements below. Output all Python, XML, and manifest files with full code.
Do not skip any file. Do not use placeholder comments like `# TODO` or `# add logic here`.

---

## Module Identity
- **Technical Name:** `stock_check_enhanced`
- **Display Name:** Stock Check Enhanced
- **Version:** 17.0.1.0.0
- **Dependencies:** `stock`, `sale_management`, `product`, `web`
- **License:** LGPL-3

---

## Core Features Required

### 1. Warehouse & Location Selection (Header Filter Bar)
- Dropdown to select **Warehouse** (res.model: `stock.warehouse`)
- Dropdown to select **Location** filtered by selected warehouse
  - Default to internal locations only (`usage = 'internal'`)
- Both dropdowns must be **dynamic** — changing warehouse reloads location list
- Persist last selection per user using `ir.config_parameter` or session

### 2. Product Stock Table (Main View)
Display a list/table of products with the following columns:

| Column | Description |
|---|---|
| Checkbox | Multi-select toggle per row |
| Product Name | `product.product` display name |
| Internal Reference | `product.default_code` |
| On Hand Qty | `qty_on_hand` at selected location |
| **Actual Available Qty** | `qty_on_hand` MINUS `qty_reserved` (outgoing reserved) — NOT Odoo's default `virtual_available` |
| Incoming Qty | Confirmed incoming moves (`state in ('assigned','confirmed','waiting')`) filtered by selected location as destination |
| UoM | Unit of measure |
| Reorder Point | From `stock.warehouse.orderpoint` if exists |
| Select Qty | Editable numeric field for quotation quantity |

> ⚠️ CRITICAL: "Actual Available Qty" must be calculated as:
> `qty_on_hand - qty_reserved`
> where `qty_reserved` = sum of `reserved_availability` from outgoing `stock.move.line`
> Do NOT use `product.with_context(location=...).virtual_available`

### 3. Multi-Select & Quotation Creation
- **Select All** checkbox in table header
- Each row has individual checkbox
- A **"Create …
[22/4/2026  09:35] IamManow001101_bot: formance Requirements
- Load products lazily — default show 50 rows, "Load More" button at bottom
- Use a single RPC call (`/web/dataset/call_kw`) to fetch all required data
  in one batch per location change
- Cache warehouse/location tree on first load

---

## File Structure Required
```
stock_enhanced_checker/
├── __init__.py
├── __manifest__.py
├── models/
│   ├── __init__.py
│   ├── stock_checker.py          # Transient or helper model with compute methods
│   └── res_config_settings.py    # Low stock threshold setting
├── controllers/
│   ├── __init__.py
│   └── stock_checker_controller.py  # JSON RPC endpoints
├── static/
│   └── src/
│       ├── js/
│       │   ├── stock_checker_action.js   # OWL Component (main)
│       │   ├── stock_checker_table.js    # OWL Sub-component: table
│       │   └── stock_checker_filters.js  # OWL Sub-component: filters/search
│       ├── xml/
│       │   ├── stock_checker_action.xml  # OWL templates
│       │   └── stock_checker_table.xml
│       └── css/
│           └── stock_checker.css
├── views/
│   ├── stock_checker_menu.xml    # Menu + Client Action registration
│   └── res_config_settings_view.xml
└── security/
    └── ir.model.access.csv
```

---

## UI/UX Design Guidelines
- Use **Bootstrap 5** classes (already available in Odoo 17)
- Table header: sticky on scroll
- Selected rows: highlight with light blue background (`#e8f4fd`)
- Available qty column: green if > 0, red if ≤ 0, orange if ≤ low_stock_threshold
- Incoming qty: show with a small arrow-up icon (✅ Odoo icon `fa-arrow-up`)
- "Create Quotation" button: `btn-primary`, disabled state when nothing selected
- Responsive: hide "Internal Ref" column on small screens

---

## Security
- Access: Users with `stock.group_stock_user` can view
- Only users with `sales_team.group_sale_salesman` can create quotations
- No new security groups needed — reuse existing Odoo groups

---

## Coding Standards
- Follow Odoo 17 OWL 2.0 component patterns (use `useState`, `useService`,
  `onWillStart`, `onWillUpdateProps`)
- Use `this.orm.call()` for RPC — do NOT use deprecated `this._rpc()`
- All Python methods must have docstrings
- No hardcoded strings in JS — use `_t()` for translations
- Python: follow PEP8, max line length 120
- XML: all views must have `id` and proper `string` attributes

---

## Output Instructions
1. Generate **every file** listed in the file structure — no skipping
2. Each file must be **complete and functional** — no `# TODO` or `...`
3. Start each file with a comment block: filename + purpose
4. After all files, provide a **Setup Instructions** section explaining:
   - How to install the module
   - Any required Odoo configuration
   - How to test each feature
```
