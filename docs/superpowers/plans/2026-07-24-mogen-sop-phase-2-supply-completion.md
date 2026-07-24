# S&OP Phase 2 Supply Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete auditable purchase and internal-transfer planning from approved S&OP recommendations, creating draft Odoo documents only.

**Architecture:** `mogen.sop.purchase.plan` materializes one approved purchase recommendation into one supplier-priced planning line, then groups ungenerated lines into draft purchase orders. `mogen.sop.transfer.plan` calculates transferable stock above source safety stock and creates draft internal pickings with linked moves. Persistent source/document links and SQL constraints make recalculation and generation idempotent.

**Tech Stack:** Odoo 17 ORM, `purchase`, `stock`, `product.supplierinfo`, multi-currency conversion, Odoo `TransactionCase`.

## Global Constraints

- Change only `mogen_sop_supply`.
- Use Odoo 17 APIs and `fields.Command` only.
- Enforce company compatibility with `check_company=True` and same-company warehouse searches.
- Never call `button_confirm`, `action_confirm`, or any picking validation method.
- Purchase-order grouping key is company, supplier, currency, destination warehouse, and receipt picking type.
- A recommendation may occur once per planning document; a generated line may create at most one source document.

---

### Task 1: Characterize and test supplier price selection

**Files:**
- Modify: `mogen_sop_supply/tests/test_supply_plan.py`
- Modify: `mogen_sop_supply/models/supply_plan.py`

**Interfaces:**
- Consumes: approved `mogen.sop.recommendation` records and `product.supplierinfo` price-break rows.
- Produces: `_supplierinfo_for(product, quantity, explicit_supplier=False)` returning the supplier row applicable to the planned quantity.

- [x] Add tests for explicit supplier selection, MOQ/multiple rounding, supplier lead time, applicable quantity price break, and conversion into the plan currency.
- [x] Run the focused tests against the existing test database; it was blocked by previously installed module errors, then use a fresh isolated database for the focused suite.
- [x] Update supplier selection to filter each vendor’s price rows to rows whose `min_qty` is no greater than the planned quantity; choose the highest applicable break deterministically and preserve the configured supplier strategy across vendors.
- [x] Run focused purchase tests and confirm the supplier data, order date, arrival date, and rounded quantity pass.

### Task 2: Test and harden draft PO creation

**Files:**
- Modify: `mogen_sop_supply/tests/test_supply_plan.py`
- Modify: `mogen_sop_supply/models/supply_plan.py`

**Interfaces:**
- Consumes: calculated `mogen.sop.purchase.line` records.
- Produces: draft `purchase.order` / `purchase.order.line` records linked by `sop_*` fields.

- [x] Add tests for compatible-line grouping, draft state, S&OP links, and repeated-action idempotency.
- [x] Verify the baseline grouping and linkage implementation through the focused isolated suite.
- [x] Retain direct creation from ungenerated rows grouped by the five-key tuple with stable plan-line links.
- [x] Run focused purchase tests and confirm draft state and idempotency.

### Task 3: Test and complete transfer calculation and draft pickings

**Files:**
- Modify: `mogen_sop_supply/tests/test_supply_plan.py`
- Modify: `mogen_sop_supply/models/supply_plan.py`

**Interfaces:**
- Consumes: approved transfer recommendations, source quants, and source warehouse orderpoints.
- Produces: same-company `mogen.sop.transfer.line` rows and linked draft `stock.picking` / `stock.move` records.

- [x] Add tests for source surplus, safety-stock protection across multiple recommendations, draft internal-picking/move links, and duplicate prevention on a second generation call.
- [x] Verify the transfer assertions with the focused isolated suite.
- [x] Aggregate source free quantity from quants, subtract orderpoint minimums, select only same-company surplus, and decrement the available source surplus after each proposal; draft documents remain unconfirmed.
- [x] Run focused transfer tests and confirm source/destination locations, safety protection, draft state, linkage fields, and idempotency.

### Task 4: Validate constraints and module integrity

**Files:**
- Modify: `mogen_sop_supply/models/supply_plan.py`
- Modify: `mogen_sop_supply/tests/test_supply_plan.py`

- [x] Retain the existing SQL duplicate-recommendation and distinct-warehouse constraints, with repeat-generation checks in the focused tests.
- [x] Run Python compilation and the module’s Odoo tests in a fresh isolated database.
