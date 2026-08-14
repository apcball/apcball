# WIP Manufacturing Report

Read-only Odoo 17 report of raw-material consumption by Manufacturing Order (MO). Strictly read-only: it never creates, writes, or deletes `stock.move`, `stock.valuation.layer`, `account.move`, or `mrp.production` records.

## Installation

Standard addon install/upgrade:

```bash
odoo -d <db> -u buz_wip_manufacturing_report --stop-after-init
```

Depends on: `mrp`, `stock`, `product`, `web`.

## Menu

**Manufacturing → Reporting → WIP Manufacturing Report**

Access: `mrp.group_mrp_user` (read-only).

## Report usage

- Set Date From / Date To (default: first day of current month → today). This filters by the raw-material `stock.move.date` — the date the material was actually consumed, not the MO's creation date. This means backdated MOs are reported in the period they were actually consumed, not the period they were entered.
- Filter by MO, finished Product, Component, or Store/Location.
- Status checkboxes default to **In Progress + Done**. "In Progress" covers both the `progress` and `to_close` Odoo states.
- **Group by MO** is the only hierarchy level — there is no separate "Job" grouping in this codebase (verified: no unified Job model/fields exist anywhere in this repo), so the Manufacturing Order itself is the top-level grouping.
- Expand All / Collapse All and search are entirely client-side — no reload.
- Export Excel produces the exact same dataset as the on-screen report (both read from `buz.wip.manufacturing.report.get_wip_data()`), so totals always match between HTML and Excel.

## Cost calculation logic

Three selectable Cost Source modes:

| Mode | Behavior |
|---|---|
| **Stock Valuation** (default) | Sums `stock.valuation.layer.value` / `.quantity` for all SVLs tied to the raw-material `stock.move`. Weighted unit cost = `abs(sum(value)) / abs(sum(quantity))`. Falls back to `move.price_unit` when no SVL exists yet (e.g. in-progress MOs whose materials haven't been valued). |
| **Move Unit Cost** | Always uses `stock.move.price_unit`, ignoring SVLs. |
| **Standard Cost** | Always uses `product.standard_price`. |

### SVL sign convention

Raw-material consumption creates **negative** SVL quantity and value (material leaving stock). The report always takes `abs()` of both before dividing, so unit costs and the WIP Value summary/total are always non-negative. This is intentional — do not remove the `abs()` calls when modifying the cost logic, or totals can go negative.

### Actual vs. BOM quantity

The report uses `stock.move.quantity` (the Odoo 17 field for actual/processed quantity), never the BOM's theoretical demand quantity. Partial consumption (move quantity less than BOM demand) is reported as consumed, not as demand.

### Scrap / cancelled / in-progress moves

- Cancelled moves (`state = 'cancel'`) are always excluded.
- Moves in `assigned` / `partially_available` state (in-progress MOs, materials reserved/picked but not yet marked `done`) are included as WIP consumption, using the fallback cost source since no SVL exists yet for undone moves.
- Scrap and unbuild moves are not part of `mrp.production.move_raw_ids` and are out of scope for this report.

## Data sources

- `mrp.production` — MO header (no Job layer; MO is the top grouping level)
- `stock.move` (filtered via `raw_material_production_id`) — raw material consumption lines
- `stock.valuation.layer` (via `stock_move_id`) — cost source
- `product.product`, `stock.location`, `uom.uom` — display/drill-down

## Security

- All access is read-only (`perm_read=1`, all other perms `0`), gated to `mrp.group_mrp_user`.
- Multi-company: every query is scoped by `company_id in company_ids`, defaulting to `self.env.companies.ids` (the current user's allowed companies). No raw SQL bypasses this filter.
- Drill-down links open standard Odoo `ir.actions.act_window` — Odoo's normal access control applies; a user without permission to a linked model sees Odoo's standard access-denied behavior.

## Excel export

`.xlsx` via `xlsxwriter` (matches the pattern used by `buz_new_stock_card`), triggered from the "Export Excel" wizard or the toolbar button. Includes: bold headers, `#,##0.00` number formatting, landscape orientation, repeated header row on each printed page, print area, autofilter, frozen panes, per-MO subtotal rows, and a Grand Total row.

## Known limitations

- "Job" is not a modeled concept anywhere in this codebase; this report groups by Manufacturing Order only.
- Multiple SVLs per move (FIFO/AVCO layers) are summed and weight-averaged; the report does not show per-layer breakdown in the main table (enable "Show Valuation Detail" for aggregate SVL count/value/qty per line).
- In-progress MOs without SVLs use a fallback cost (`move.price_unit`) that may differ from the eventual FIFO/AVCO-settled cost once the move is marked `done`.

## Tests

`tests/test_wip_manufacturing_report.py` — 9 `TransactionCase` tests covering: multi-component aggregation, multi-MO grand totals, in-progress fallback cost, FIFO multi-SVL weighted cost, partial consumption, cancelled-move exclusion, multi-company isolation, SVL sign handling, and summary-vs-pagination consistency.

Run against the isolated test DB (`docker-compose.test.yml`), **not** MOG_DEV/MOG_LIVE — edit that file's `command:` to target `-u buz_wip_manufacturing_report` before running, per repo convention.
