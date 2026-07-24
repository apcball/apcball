# Mogen Smart S&OP Planning Workspace Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a modular, auditable Odoo 17 Smart S&OP workspace without changing Odoo core.

**Architecture:** Five addons separate workflow/security, demand, supply, inventory, and a thin OWL dashboard. Heavy calculations write immutable plan/version snapshots and stored planning lines; the dashboard reads only secured aggregates.

**Tech Stack:** Odoo 17 ORM, Python 3.10+, PostgreSQL, OWL, standard Odoo views/security/tests.

## Global Constraints

- Odoo 17 Community/Enterprise; no Odoo core changes.
- Every business record is multi-company; warehouse calculations use warehouse locations.
- Use ORM/read_group and batched processing; no N+1 source reads.
- Documents created from recommendations remain draft until a user confirms them.
- Use `fields.Command`, chatter/activities for approvals, stable XML IDs, and Odoo TransactionCase/SavepointCase tests.
- Live DEV tests affect the database; prefer `docker-compose.test.yml` once updated for the target module.

---

### Task 1: Addon skeleton and shared S&OP navigation

**Files:**
- Create: `mogen_sop_core/__manifest__.py`, `mogen_sop_core/security/sop_security.xml`, `mogen_sop_core/views/sop_menu.xml`
- Create: package files, manifests, README files for the other four addons
- Create: `docs/mogen_sop_phase_1_architecture.md`

**Produces:** installable dependency graph, five role groups, top-level Smart S&OP navigation.

- [ ] Create the skeletons and manifests with only dependencies that exist in Phase 1.
- [ ] Load the security groups before menus, using stable module-prefixed XML IDs.
- [ ] Test installation of each addon against an isolated Odoo database.
- [ ] Review the file list and obtain approval before Task 2.

### Task 2: Core planning workflow and access control

**Files:** `mogen_sop_core/models/sop_plan.py`, `sop_version.py`, `sop_scenario.py`, `sop_recommendation.py`, `sop_alert.py`, security/views/tests.

**Produces:** plan/version/scenario/recommendation/alert models, enforced transitions, plan locking, access rows and company record rules.

- [ ] Add failing TransactionCase tests for transitions, lock protection, current-version uniqueness, and company visibility.
- [ ] Implement models and workflow until tests pass.
- [ ] Install/update core and run its test suite.

### Task 3: Demand planning

**Files:** `mogen_sop_demand/models/`, `wizard/`, `views/`, `security/`, `tests/`.

**Produces:** stored demand records, deterministic sales extraction, moving-average baseline and forecast precedence.

- [ ] Add failing tests for sales filtering/UOM/returns, precedence, accuracy and zero-safe bias.
- [ ] Implement batched aggregation and forecast actions, then views and wizard.
- [ ] Run isolated demand-module tests.

### Task 4: Inventory policy and snapshots

**Files:** `mogen_sop_inventory/models/`, settings/views/security/tests.

**Produces:** policy resolution precedence, company thresholds, batched warehouse snapshots.

- [ ] Add failing tests for policy precedence and warehouse-only stock.
- [ ] Implement policy lookup and chunked quant/move snapshot creation.
- [ ] Run isolated inventory-module tests.

### Task 5: Supply and recommendations

**Files:** `mogen_sop_supply/models/`, security/views/tests.

**Produces:** supply lines, incoming supply aggregation, projection/shortage/coverage, deduplicated recommendations.

- [ ] Add failing tests for incoming PO/MO, formulas, route selection and duplicate prevention.
- [ ] Implement batch calculations and recommendation generation.
- [ ] Run isolated supply-module tests.

### Task 6: Recommendation execution

**Files:** core recommendation action implementation and tests.

**Produces:** manager-authorized draft PO and draft MO actions with linkage and validation.

- [ ] Add failing tests for vendor selection/draft PO and BOM validation/draft MO.
- [ ] Implement actions without confirmation side effects.
- [ ] Run core/supply test suites.

### Task 7: Inventory health

**Files:** `mogen_sop_inventory/models/sop_inventory_health.py`, views/tests.

**Produces:** stored, threshold-driven health classifications.

- [ ] Add failing tests for understock, overstock, slow/non-moving and no-demand.
- [ ] Implement batch classification and drill-down views.
- [ ] Run inventory tests.

### Task 8: Dashboard

**Files:** dashboard model/service, controller if required, OWL JS/XML/SCSS, assets, tests.

**Produces:** responsive secured client action with persisted filters and aggregate endpoints.

- [ ] Add failing tests for access validation and each aggregate service contract.
- [ ] Implement services first, then OWL loading/empty/error states and drill-downs.
- [ ] Run dashboard tests and asset/module installation.

### Task 9: Release assets and verification

**Files:** demo XML, each README, installation/configuration/workflow/model/formula documents, all missing tests.

**Produces:** demo-ready, documented suite with full required test coverage.

- [ ] Add deterministic demo data using existing products only through stable references.
- [ ] Complete all end-user and technical documentation.
- [ ] Run isolated module installation/tests, lint, and a requirement-by-requirement audit.
