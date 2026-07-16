# POS Lite Location Products Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Allow each POS Lite configuration to select an internal stock location used to load terminal products and quantities.

**Architecture:** Add an optional `location_id` to `pos.lite.config`; the product API resolves it from the active session/config and falls back to the warehouse’s lot-stock location for existing configurations. Keep the existing warehouse selector and order flow compatible.

**Tech Stack:** Odoo 17 Python ORM, XML views, Odoo TransactionCase.

## Global Constraints

- Preserve existing configurations by making the new location optional.
- Only internal locations in the selected company may be configured.
- Service products remain visible regardless of stock quantities.

### Task 1: Add configuration location and API resolution

**Files:**
- Modify: `pos_lite/models/pos_config.py`
- Modify: `pos_lite/views/pos_config_view.xml`
- Modify: `pos_lite/controllers/main.py`
- Test: `pos_lite/tests/test_terminal_products.py`

- [ ] Add a failing test that creates a config with an internal sublocation and verifies the terminal location resolver returns it, while a config without one returns the warehouse lot-stock location.
- [ ] Run the focused Odoo test and confirm it fails because the field/helper is missing.
- [ ] Add `location_id = fields.Many2one('stock.location', ...)` with a company/internal-location domain and a controller helper that prefers config location and falls back to warehouse lot stock.
- [ ] Add the field to the config tree/form views.
- [ ] Update `/pos_lite/api/products` to read quants and stockable product inclusion from the resolved location.
- [ ] Run Python syntax and `git diff --check`, then run the focused Odoo test in DEV/isolation.
