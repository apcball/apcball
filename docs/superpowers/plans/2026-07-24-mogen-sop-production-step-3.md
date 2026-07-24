# Mogen S&OP Production Planning — Phase 2 Step 3

> **For implementation:** execute this plan in order. It deliberately excludes BOM explosion, material requirements, capacity planning, and manufacturing-order generation.

## Scope and source contract

Phase 1 currently exposes no demand or inventory-policy models. The production addon will therefore read only approved `mogen.sop.recommendation` records (`recommendation_type = 'manufacture'`) as its approved production-demand source. Warehouse reordering rules provide per-warehouse safety stock (`product_min_qty`) and manufacturing batch multiple (`qty_multiple`). The selected BOM's `product_qty` is the second rounding fallback, then the product UoM rounding.

## Task 1 — Establish the module and red tests

**Files:**
- Create `mogen_sop_production/__init__.py`
- Create `mogen_sop_production/__manifest__.py`
- Create `mogen_sop_production/models/__init__.py`
- Create `mogen_sop_production/tests/__init__.py`
- Create `mogen_sop_production/tests/test_production_plan.py`

1. Add a minimal installable Odoo 17 module depending on core, demand, supply, inventory, MRP, stock, maintenance, and mail.
2. Write `TransactionCase` tests for the required-quantity formula, three-priority rounding, company isolation, and warehouse-specific stock.  The initial test run must fail because production models do not exist.

## Task 2 — Implement stored plan and line calculation

**Files:**
- Create `mogen_sop_production/models/production_plan.py`

1. Add chatter-enabled `mogen.sop.production.plan` and `mogen.sop.production.line` with the Step 3 field subset.
2. Implement workflow states and `action_calculate_production`.
3. Batch-read approved manufacture recommendations, warehouse stock quants, reordering rules, and BOMs. Store generated calculation lines; do not call stock availability product-by-product.
4. Apply the required-quantity formula and rounding priority. Allow only draft/calculated workflow transitions in this step; leave approval/execution and downstream generation outside scope.

## Task 3 — Security and planning views

**Files:**
- Create `mogen_sop_production/security/production_security.xml`
- Create `mogen_sop_production/security/ir.model.access.csv`
- Create `mogen_sop_production/views/production_plan_views.xml`
- Create `mogen_sop_production/views/production_menu.xml`
- Update `mogen_sop_production/__manifest__.py`

1. Define the production-planner group implied by the core viewer group.
2. Add company-scoped rules and ACLs for planners, core managers, and administrators.
3. Add tree, form, search, pivot, and graph views plus a planning menu/action.

## Task 4 — Verify

1. Run the new production test class through Odoo's isolated test environment.
2. Run syntax/XML validation and module installation if the local image/database harness supports it.
3. Report any existing test-harness defect distinctly from module failures.

## Acceptance checklist

- [ ] Uses only approved manufacture recommendations as demand source.
- [ ] Required quantity is `max(0, demand + safety - free - incoming)`.
- [ ] Rounding prioritizes reordering-rule multiple, BOM quantity, then UoM rounding.
- [ ] Stock aggregation remains warehouse-specific and batched.
- [ ] Lines are stored; excluded Step 4/5 and MO-generation features are absent.
- [ ] Security, views, and formula/multi-company/warehouse tests are present.
