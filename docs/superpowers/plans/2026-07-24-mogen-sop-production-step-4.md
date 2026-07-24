# S&OP Production Material Planning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic, warehouse-specific, multi-level material requirements to Phase 2 production plans without creating operational documents.

**Architecture:** `mogen.sop.production.plan` owns stored aggregate requirement rows. The calculation starts from stored production lines, uses Odoo's `mrp.bom.explode()` for each BoM's phantom/variant/UoM semantics, then walks normal child BoMs with an ancestry set to prevent cycles. It aggregates leaf component demand by plan company, warehouse, component and period, then calculates warehouse stock and incoming purchase/MO quantities in grouped queries.

**Tech Stack:** Odoo 17 ORM, MRP BoM API, stock/purchase/mrp aggregates, Odoo TransactionCase tests.

## Global Constraints

- Target Odoo 17 and Python 3.10+.
- Modify only `mogen_sop_production`; do not modify Odoo core.
- Use stored planning rows, batch queries and standard ORM access control.
- Do not create or confirm purchase orders, manufacturing orders or transfers.
- Preserve multi-company and multi-warehouse isolation.
- Use `fields.Command` for Odoo 17 relation values.

---

### Task 1: Define Material-Requirement Tests

**Files:**
- Modify: `mogen_sop_production/tests/test_production_plan.py`
- Test: `mogen_sop_production/tests/test_production_plan.py`

**Interfaces:**
- Consumes: `mogen.sop.production.plan.action_calculate_production()`.
- Produces: expected contract for `action_calculate_material_requirements()` and stored `material_line_ids`.

- [ ] **Step 1: Write the failing tests**

```python
production_plan.action_calculate_production()
production_plan.action_calculate_material_requirements()
requirement = production_plan.material_line_ids
self.assertEqual(requirement.required_qty, 6.0)
self.assertEqual(requirement.shortage_qty, 4.0)
```

Cover one normal BoM, nested normal BoMs, shared leaves, a component UoM conversion, a phantom child BoM, no selected BoM, a cyclic normal BoM graph and free/incoming component availability.

- [ ] **Step 2: Run tests to verify they fail**

Run: `odoo ... -u mogen_sop_production --test-enable --test-tags /mogen_sop_production --stop-after-init --no-http`

Expected: failures because `action_calculate_material_requirements` and `material_line_ids` do not exist.

### Task 2: Implement Stored Material Requirements

**Files:**
- Modify: `mogen_sop_production/models/production_plan.py`
- Modify: `mogen_sop_production/security/ir.model.access.csv`
- Modify: `mogen_sop_production/security/production_security.xml`
- Modify: `mogen_sop_production/views/production_plan_views.xml`

**Interfaces:**
- Consumes: generated `mogen.sop.production.line` records and Odoo `mrp.bom.explode(product, quantity)`.
- Produces: `mogen.sop.material.requirement`, `action_calculate_material_requirements()` and `action_generate_material_recommendations()`.

- [ ] **Step 1: Add the failing-model API contract**

```python
material_line_ids = fields.One2many(
    "mogen.sop.material.requirement", "production_plan_id", readonly=True
)

def action_calculate_material_requirements(self):
    """Replace stored requirements from current planned production quantities."""
```

- [ ] **Step 2: Implement explosion and aggregation**

```python
boms, leaves = bom.explode(product, quantity)
for bom_line, values in leaves:
    demand[component_id] += bom_line.product_uom_id._compute_quantity(
        values["qty"], component.uom_id, round=False
    )
```

Recursively run this only for a selected normal BoM of a leaf product. Pass an immutable ancestry of BoM ids; raise `ValidationError` when a BoM repeats in one ancestry. Group the resulting leaves by `(component_id, period_date)`, retain parent production-line ids, and make one stored requirement per group.

- [ ] **Step 3: Implement availability and statuses**

```python
shortage = max(0.0, required - free_qty - incoming_qty)
status = "available" if shortage == 0 else (
    "partial" if free_qty + incoming_qty else "shortage"
)
```

Use `read_group` over `stock.quant`, open incoming `purchase.order.line`, and open component `mrp.production`, scoped to the plan company and warehouse stock location. Use `procurement_route` only as an auditable classification, never to create a stock document.

- [ ] **Step 4: Implement draft recommendation generation**

```python
existing = Recommendation.search([
    ("source_model", "=", "mogen.sop.material.requirement"),
    ("source_res_id", "=", requirement.id),
])
if not existing:
    Recommendation.create({"recommendation_type": route, "quantity": requirement.shortage_qty})
```

Create one draft core recommendation for each shortage requirement, link it, and keep later executions idempotent. Never create PO, MO, transfer or picking records.

### Task 3: Add Security and Views

**Files:**
- Modify: `mogen_sop_production/security/ir.model.access.csv`
- Modify: `mogen_sop_production/security/production_security.xml`
- Modify: `mogen_sop_production/views/production_plan_views.xml`

**Interfaces:**
- Consumes: stored requirement model from Task 2.
- Produces: company record rule and read-only material page/actions for planners.

- [ ] **Step 1: Add access and company rule**

```xml
<record id="rule_sop_material_requirement_company" model="ir.rule">
    <field name="model_id" ref="model_mogen_sop_material_requirement"/>
    <field name="domain_force">[('company_id', 'in', company_ids)]</field>
    <field name="global" eval="True"/>
</record>
```

- [ ] **Step 2: Add the form notebook page and calculation actions**

```xml
<button name="action_calculate_material_requirements" type="object" string="Calculate Materials"/>
<page string="Materials"><field name="material_line_ids" readonly="1"/></page>
```

### Task 4: Verify the Module

**Files:**
- Verify: `mogen_sop_production/`

- [ ] **Step 1: Compile and validate XML**

Run: `python3 -m compileall -q mogen_sop_production` and parse module XML.

- [ ] **Step 2: Install/update and run focused Odoo tests**

Run: isolated Docker Odoo update with `--test-tags /mogen_sop_production`.

Expected: module installs and all existing plus Step 4 tests pass.

- [ ] **Step 3: Request code review**

Review the final diff against the Step 4 requirements; correct all material findings before handoff.
