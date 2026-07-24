# S&OP Supply Purchase and Transfer Planning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert approved S&OP purchase and transfer recommendations into auditable purchase/transfer plans and draft Odoo documents.

**Architecture:** Purchase plans materialize approved purchase recommendations into supplier-selected, UoM-rounded lines and group compatible lines into draft POs. Transfer plans materialize approved transfer recommendations into warehouse-surplus proposals and group them into draft internal pickings. Both retain stable source links and reject duplicate document generation.

**Tech Stack:** Odoo 17 ORM, purchase, stock, product supplierinfo, currencies, TransactionCase.

## Global Constraints

- Target Odoo 17 and Python 3.10+.
- Modify only `mogen_sop_supply`; do not modify Odoo core.
- Support multiple companies and warehouses using company record rules.
- Create only draft POs and draft internal pickings; never confirm them.
- Use batch aggregation and stored planning rows.
- Use Odoo 17 `fields.Command` relation values.

---

### Task 1: Purchase Planning Tests and Models

**Files:**
- Create: `mogen_sop_supply/models/supply_plan.py`
- Create: `mogen_sop_supply/tests/test_supply_plan.py`
- Modify: `mogen_sop_supply/models/__init__.py`

- [ ] **Step 1: Write failing purchase tests**

```python
plan.action_calculate_purchase()
line = plan.line_ids
self.assertEqual(line.proposed_qty, 12.0)
self.assertEqual(line.expected_arrival_date, required_date)
```

Cover explicit supplier selection, MOQ/multiple rounding, supplier lead time, price break, currency conversion, PO grouping, and duplicate PO prevention.

- [ ] **Step 2: Implement stored purchase plans**

Use approved core purchase recommendations. Select valid supplierinfo deterministically by explicit supplier, sequence, then configured strategy; convert supplier UoM to product UoM and supplier currency into plan currency. Keep one line per recommendation and one stable generated PO link.

### Task 2: Draft Purchase Orders and S&OP Links

**Files:**
- Modify: `mogen_sop_supply/models/supply_plan.py`

- [ ] **Step 1: Add linkage fields**

```python
class PurchaseOrder(models.Model):
    _inherit = "purchase.order"
    sop_plan_id = fields.Many2one("mogen.sop.plan", copy=False, index=True)
```

Add plan/version/purchase-plan/purchase-line fields to purchase orders and lines.

- [ ] **Step 2: Group and create draft POs**

Group by company, supplier, currency, destination warehouse, and receipt picking type. Create `purchase.order` and `purchase.order.line` directly in draft, link source plan lines, and reject a second creation for an already-linked line.

### Task 3: Transfer Planning, Draft Pickings, and Stock Links

**Files:**
- Modify: `mogen_sop_supply/models/supply_plan.py`
- Modify: `mogen_sop_supply/tests/test_supply_plan.py`

- [ ] **Step 1: Write failing transfer tests**

```python
transfer_plan.action_calculate_transfers()
self.assertEqual(line.proposed_qty, 5.0)
transfer_plan.action_create_draft_pickings()
self.assertEqual(line.generated_picking_id.state, "draft")
```

Cover source selection, safety protection, transfer amount, same-company isolation, draft picking creation, and duplicate prevention.

- [ ] **Step 2: Implement transfer calculation and documents**

Aggregate stock quants and orderpoint safety by warehouse/product. Choose a same-company internal-transfer warehouse with surplus, then create draft internal pickings and moves using the internal picking type and warehouse stock locations.

- [ ] **Step 3: Add stock linkage fields**

Add plan/version/transfer-plan/transfer-line fields to stock pickings and moves.

### Task 4: Security, Views, and Verification

**Files:**
- Create: `mogen_sop_supply/security/supply_security.xml`
- Create: `mogen_sop_supply/security/ir.model.access.csv`
- Create: `mogen_sop_supply/views/supply_plan_views.xml`
- Create: `mogen_sop_supply/views/supply_menu.xml`
- Modify: `mogen_sop_supply/__manifest__.py`

- [ ] **Step 1: Add planner ACLs and company rules**

- [ ] **Step 2: Add list/form/search views and menus**

- [ ] **Step 3: Compile, XML-validate, update module, run focused tests, and request review**
