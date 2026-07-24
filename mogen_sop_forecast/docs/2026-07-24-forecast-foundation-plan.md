# Forecast Foundation Implementation Plan

**Goal:** Add auditable, deterministic forecast runs and stored results to `mogen_sop_forecast`.

**Architecture:** Forecast formulas are pure Python services. The run model obtains history in batched `sale.order.line.read_group` queries, normalizes quantities to the product UoM, and stores every generated result with source metadata.

**Constraints:** Odoo 17; multi-company and warehouse safe; no per-product sale-line queries; no model selection or demand-plan publication.

- [ ] Add test coverage for deterministic algorithms and insufficient history.
- [ ] Add forecast models, batched history adapter, lifecycle, and durable results.
- [ ] Add ACLs, company rules, views, seed models, and documentation.
- [ ] Validate with Odoo installation and module tests.
