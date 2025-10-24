# Prompt Engineering: Odoo 17 Module - buz\_warranty\_management

## 🎯 Objective

Implement a complete **Warranty Management System** for Odoo 17 Community that integrates seamlessly with Sales, Stock, and Accounting. The goal is to allow configuration of warranty policies at the product level, automatic warranty creation on delivery, claim management (with both under and out-of-warranty handling), and the ability to generate warranty certificates.

---

## 🧩 Core Features

### 1. Warranty Setup (Product Level)

- Add a new tab `Warranty Information` to `product.template`.
- New fields:
  - `warranty_duration`: Integer (months)
  - `warranty_condition`: Text (terms & conditions)
  - `warranty_type`: Selection (Replacement / Repair / Refund)
  - `auto_warranty`: Boolean (auto-create warranty card on delivery)
  - `service_product_id`: Many2one to `product.product` (service used in repairs or out-of-warranty jobs)
  - `allow_out_of_warranty`: Boolean

---

### 2. Automatic Warranty Card Creation

- On `stock.picking` validation (state = done):
  - If any delivered product has `auto_warranty=True`, create `warranty.card` records.
  - Fields:
    - `name`: Sequence (WARR/YYYY/#####)
    - `partner_id`: Customer
    - `product_id`, `lot_id`, `sale_order_id`, `picking_id`
    - `start_date`: delivery date
    - `end_date`: start\_date + warranty\_duration
    - `state`: draft → active → expired
  - Generate a **Warranty Certificate PDF (QWeb)** automatically and attach to warranty record.

---

### 3. Warranty Claim Management

- Model: `warranty.claim`
- Workflow:

  1. Customer reports issue → create claim record.
  2. System checks if still under warranty (based on warranty card end date).
  3. If within warranty → repair/replace free.
  4. If expired → system offers wizard to create a **Quotation (SO)** with `service_product_id` and entered cost.
  5. Once repair is complete, update warranty history and mark claim as resolved.
- Fields:

  - `warranty_card_id`, `partner_id`, `product_id`, `lot_id`
  - `claim_date`, `claim_type` (Repair/Replace/Refund)
  - `is_under_warranty` (computed)
  - `status`: draft / under_review / approved / done / rejected
  - `cost_estimate`, `quotation_id`, `repair_id`

#### 3.1 RMA & Stock Operations (New)

Add full **RMA flow** with stock movements to support picking parts from warehouse for replacement/claim and billing when needed.

- **New Operation Types / Locations (configurable in Settings):**

  - `warranty_rma_in_picking_type_id` (Customer Return → Repair/Warranty Location)
  - `warranty_repair_location_id` (internal location for diagnosis/repair)
  - `warranty_replacement_out_picking_type_id` (Replacement Delivery → Customer)
  - `warranty_scrap_location_id` (for defective returns)
- **Claim Lines:** `warranty.claim.line`

  - Fields: `product_id`, `description`, `qty`, `uom_id`, `lot_id`, `need_replacement` (bool), `is_consumable` (bool), `unit_cost`, `unit_price`
  - Link to stock moves via `move_ids` (M2m) for traceability
- **Wizards:**

  - `warranty.claim.rma.receive.wizard`: create **RMA IN** picking (customer → repair location) with optional lot capture & return label.
  - `warranty.claim.replacement.issue.wizard`: create **Replacement OUT** picking (repair location → customer). Supports:
    - Under-warranty: zero-price delivery (no SO) or zero-price SO for portal tracking.
    - Out-of-warranty: generate SO lines from claim lines (parts + labor) → confirm → delivery.
  - `warranty.claim.invoice.wizard`: convert claim lines (parts/labor) to **Draft Invoice** directly (for quick-charge jobs) or attach to existing SO.
- **Accounting/Costing Rules:**

  - Under-warranty replacement: stock valuation hits **Warranty Expense** (configurable account) via category or account mapping (uses `stock_account`). Option to set `valuation_layer_analytic_tag_id` = "Warranty".
  - Out-of-warranty: normal SO/Invoice with prices from `unit_price`; cost flows FIFO as usual.
  - Consumables used during repair can be expensed directly using **stock rules to expense location** or via SO with zero price (if under warranty).
- **Serial/Lot Handling:**

  - Capture original lot on card and on RMA IN.
  - Replacement OUT may assign new lot; system writes lot link into claim and card history.
- **Statuses Extended:** `warranty.claim.status`

  - `draft` → `awaiting_return` → `received` → `diagnosing` → `awaiting_parts` → `ready_to_issue` → `done` / `rejected`.
- **Buttons / Smart Buttons:**

  - On Claim: `Create RMA IN`, `Issue Replacement`, `Create Invoice`, `Create SO` (if OOW).
  - On Warranty Card: `Claims`, `RMA Pickings`, `Invoices`.

---

### 4. Out-of-Warranty Flow

- If `is_under_warranty=False`:
  - A button **"Create Quotation"** triggers wizard `warranty.claim.out.wizard`.
  - Wizard asks for:
    - Service Product
    - Repair Cost
  - Creates a new Sale Order for customer → confirm → generate invoice.

---

### 5. Warranty Dashboard

- Dashboard menu for warranty team:
  - Filters for Active / Expired / Near-expiry (within 30 days)
  - Smart Buttons:
    - From Partner → Warranty Cards
    - From Product → Warranty Cards
  - KPIs: Total warranties, active %, claimed %, expired %

---

### 6. Reports

- **Warranty Certificate (QWeb)**: Printable warranty document.
- **Warranty Claim Form**: For repair documentation.
- **Warranty Summary Report**: By product, customer, or month.

---

## 🧠 Model Structure

### Model: `warranty.card`

| Field         | Type      | Description                 |
| ------------- | --------- | --------------------------- |
| name          | Char      | Warranty number             |
| partner_id    | Many2one  | Customer                    |
| product_id    | Many2one  | Product                     |
| lot_id        | Many2one  | Serial number               |
| start_date    | Date      | Warranty start date         |
| end_date      | Date      | Warranty end date           |
| sale_order_id | Many2one  | Sale order reference        |
| picking_id    | Many2one  | Delivery order reference    |
| state         | Selection | draft / active / expired    |
| condition     | Text      | Warranty conditions         |
| claim_count   | Integer   | Smart button link to claims |

### Model: `warranty.claim`

| Field             | Type      | Description                                       |
| ----------------- | --------- | ------------------------------------------------- |
| warranty_card_id  | Many2one  | Linked warranty card                              |
| partner_id        | Many2one  | Customer                                          |
| product_id        | Many2one  | Product                                           |
| claim_type        | Selection | Repair / Replace / Refund                         |
| is_under_warranty | Boolean   | Computed from card date                           |
| claim_date        | Date      | Date reported                                     |
| status            | Selection | draft / under_review / approved / done / rejected |
| description       | Text      | Problem details                                   |
| quotation_id      | Many2one  | Out-of-warranty sale order                        |
| repair_id         | Many2one  | Repair order reference                            |

### Model: `warranty.claim.line` (New)

| Field            | Type      | Description                |
| ---------------- | --------- | -------------------------- |
| claim_id         | Many2one  | Parent claim               |
| product_id       | Many2one  | Part/Item used             |
| description      | Char      | Notes                      |
| qty              | Float     | Quantity                   |
| uom_id           | Many2one  | UoM                        |
| lot_id           | Many2one  | Lot/Serial (optional)      |
| need_replacement | Boolean   | Mark as replacement item   |
| is_consumable    | Boolean   | If true, expense directly  |
| unit_cost        | Monetary  | For internal cost tracking |
| unit_price       | Monetary  | For customer billing       |
| move_ids         | Many2many | Related stock moves        |

### Settings/Config (New)

- `res.config.settings` fields:
  - `warranty_rma_in_picking_type_id`
  - `warranty_repair_location_id`
  - `warranty_replacement_out_picking_type_id`
  - `warranty_scrap_location_id`
  - `warranty_expense_account_id`
  - `warranty_default_service_product_id`

## ⚙️ Dependencies

- `sale`
- `stock`
- `stock_account`
- `account`
- `repair` (optional)
- `uom`
- `mail`

---

## 📁 Module Structure

```
buz_warranty_management/
├── __init__.py
├── __manifest__.py
├── models/
│   ├── __init__.py
│   ├── warranty_card.py
│   ├── warranty_claim.py
│   ├── warranty_claim_line.py
│   └── res_config_settings.py
├── wizard/
│   ├── __init__.py
│   ├── warranty_out_wizard.py                 # OOW quotation
│   ├── warranty_rma_receive_wizard.py         # Create RMA IN picking
│   ├── warranty_replacement_issue_wizard.py   # Create Replacement OUT picking / SO lines
│   └── warranty_invoice_wizard.py             # Quick invoice from claim lines
├── views/
│   ├── menu.xml
│   ├── warranty_card_views.xml
│   ├── warranty_claim_views.xml
│   ├── warranty_claim_line_views.xml
│   ├── product_template_views.xml
│   ├── res_config_settings_views.xml
│   ├── warranty_out_wizard_view.xml
│   ├── warranty_rma_receive_wizard_view.xml
│   └── warranty_replacement_issue_wizard_view.xml
├── report/
│   ├── report_warranty_certificate.xml
│   ├── report_warranty_claim_form.xml
│   └── report_warranty_rma_slip.xml
├── security/
│   ├── ir.model.access.csv
│   ├── security.xml
├── data/
│   ├── sequence.xml
│   ├── warranty_data.xml
│   ├── stock_picking_types.xml   # precreate operation types (optional)
│   └── mail_templates.xml
├── README.md
└── QWEN.md
```

buz_warranty_management/
├── __init__.py
├── __manifest__.py
├── models/
│   ├── __init__.py
│   ├── warranty_card.py
│   ├── warranty_claim.py
├── wizard/
│   ├── __init__.py
│   ├── warranty_out_wizard.py
├── views/
│   ├── menu.xml
│   ├── warranty_card_views.xml
│   ├── warranty_claim_views.xml
│   ├── product_template_views.xml
│   ├── warranty_out_wizard_view.xml
├── report/
│   ├── report_warranty_certificate.xml
│   ├── report_warranty_claim_form.xml
├── security/
│   ├── ir.model.access.csv
│   ├── security.xml
├── data/
│   ├── sequence.xml
│   ├── warranty_data.xml
├── README.md
└── QWEN.md

```

---

## 🚀 Implementation Steps

1. **Define Models:** `warranty.card`, `warranty.claim`, `warranty.claim.line` + settings.
2. **Extend Product Template:** Add warranty fields.
3. **Stock Picking Hooks:**
   - Auto-create warranty cards on Delivery Done.
   - RMA IN creation from claim; Replacement OUT from claim/wizard.
4. **Claim Workflow:** Add statuses + transitions; tie stock moves/repair.
5. **Wizards:** RMA Receive, Replacement Issue, Out-of-Warranty Quotation, Quick Invoice.
6. **Reports:** Warranty Certificate, Claim Form, **RMA Slip**.
7. **Menu & Security:** Define menus under `Warranty Management`.
8. **Accounting Rules:** Map under-warranty costs to expense; OOW via SO/Invoice.

---

## 🧰 Optional Enhancements

- Portal view for customers to check their warranties.
- Auto email when warranty is near expiration.
- Barcode scanning for quick warranty lookup.
- Integration with `buz_account_receipt` for billing out-of-warranty claims.

---

## 🧑‍💻 Prompt Template (to use with AI code generator)

**Prompt:**

> Generate a full Odoo 17 Community module named `buz_warranty_management` with the following specs:
> 
> ### Functional Scope
> - Product-level warranty configuration fields (duration, type, conditions, auto flag, default service product).
> - Auto-create `warranty.card` records when Delivery Orders are validated; start date = delivery done date; end date = start + months.
> - Warranty Claim management (`warranty.claim`) with statuses and portal chatter.
> - **RMA & Stock Flows:**
>   - RMA IN (customer → repair location) via wizard, capturing serial/lot.
>   - Replacement OUT (repair location → customer) via wizard; supports under-warranty (zero price) and out-of-warranty (SO/Invoice) flows.
>   - Claim lines with parts/consumables and linkage to stock moves.
> - **Billing:**
>   - Out-of-warranty quotation/invoice creation from claim lines (parts + labor).
>   - Quick Invoice wizard independent of SO (option).
> - **Accounting:** Under-warranty cost recognition to Warranty Expense (configurable), FIFO cost flow for OOW; optional analytic tag `Warranty` on SVLs.
> - **Reports:** Warranty Certificate, Claim Form, RMA Slip.
> - **Settings:** Operation types/locations/accounts defaults in `res.config.settings`.
> - **Security:** Groups for Warranty User/Manager; record rules for multi-company.
>
> ### Technical
> - Dependencies: `sale`, `stock`, `stock_account`, `account`, `repair` (optional), `uom`, `mail`.
> - Add models: `warranty.card`, `warranty.claim`, `warranty.claim.line`.
> - Add wizards: `warranty_out_wizard`, `warranty_rma_receive_wizard`, `warranty_replacement_issue_wizard`, `warranty_invoice_wizard`.
> - Views: product template tab; claim form/tree/kanban with smart buttons; RMA/Replacement wizards; settings view.
> - Hooks: extend `stock.picking` (create cards), methods to spawn pickings/SO/Invoice; computed fields & constraints.
> - Reports: QWeb templates (Thai/EN labels), attach PDF to card and claim.
> - Data: sequences, operation types (optional), mail templates.
> - Tests: basic flow tests (create card, claim, RMA, replacement, invoice).
> - OCA style & i18n (th, en_US).
>
> Deliver: full module tree with working code, manifests, and sample data ready to install.

```