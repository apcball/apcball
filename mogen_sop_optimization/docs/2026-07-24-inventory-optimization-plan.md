# Inventory Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Deliver deterministic, auditable inventory segmentation and policy recommendations without changing inventory policies automatically.

**Architecture:** Pure Python formula functions provide deterministic calculations and are covered by unit tests. Odoo models persist input assumptions, grouped demand metrics, proposed policies, and approval state. A run uses grouped ORM queries and bulk record creation; a cron invokes only explicitly queued runs.

**Tech Stack:** Odoo 17 ORM, PostgreSQL, Python 3.10+.

## Global Constraints

- Calculations are deterministic and retain their input parameters and algorithm version.
- Zero or missing economic inputs produce safe zero recommendations and an explanation.
- No run, cron, or approval action writes `stock.warehouse.orderpoint` records.
- All queries aggregate input data in batches.

## Formulae

- Fixed safety stock: `fixed_qty`.
- Days-of-demand safety stock: `average_daily_demand × coverage_days`.
- Statistical safety stock: `z × σ_demand × √lead_time_days`.
- With lead-time variation: `z × √(lead_time_days × σ_demand² + average_daily_demand² × σ_lead_time²)`.
- Reorder point: `average_daily_demand × lead_time_days + safety_stock`.
- EOQ: `√(2 × annual_demand × ordering_cost ÷ holding_cost_per_unit)`; it is zero when a required input is zero or negative.
- ABC: descending annual consumption value, with A through the A threshold, B through the B threshold, otherwise C.
- XYZ: coefficient of variation `σ / mean`: X at or below the X limit, Y at or below the Y limit, otherwise Z.

## Tasks

- [x] Add formula tests and verify they fail before the service exists.
- [x] Implement pure deterministic formula service.
- [x] Add run, constraint, result, and segment models with approval-gated proposals.
- [x] Add batch calculation and scheduled queued-run support.
- [x] Add security, views, demo configuration, and documentation.
- [ ] Run isolated Odoo installation and targeted tests.
