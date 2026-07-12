# SPE × pos_lite integration + dashboard polish — Design

Date: 2026-07-12
Module: `buz_sales_performance_engine` (direct dependency on `pos_lite`)
Version bump: 17.0.1.0.0 → 17.0.2.0.0

## Goal

Recognize POS Lite sales in the Sales Performance Engine using the same strict
rule as SO-based sales (delivered AND invoiced), and modernize the OWL
dashboard styling.

## 1. Data model — `buz.sales.performance.result`

- `source` — Selection `[('sale', 'Sales Order'), ('pos', 'POS Lite')]`,
  default `sale`, required, indexed.
- `pos_order_id` — Many2one `pos.lite.order`, ondelete cascade, indexed.
- `pos_order_line_id` — Many2one `pos.lite.order.line`, ondelete cascade, indexed.
- `sale_order_line_id` stays; each row has exactly one of
  `sale_order_line_id` / `pos_order_line_id`.
- SQL constraints: keep `uniq_sol_company`; add `uniq_pos_line_company`
  UNIQUE(pos_order_line_id, company_id). Postgres UNIQUE ignores NULLs, so the
  two constraints coexist.

## 2. Recognition rule for POS

A result row exists for a `pos.lite.order.line` **only** when its order state
is `done` (pos_lite sets `done` when invoice is posted AND picking is done, or
no shippable products).

- Normal order (`is_return = False`): `invoice_amount = price_subtotal`,
  `refund_amount = 0`.
- Return order (`is_return = True`): `invoice_amount = 0`,
  `refund_amount = price_subtotal`. Returns are separate orders, so net sales
  aggregate correctly across original + return rows.
- Cancelled orders: rows deleted.

Dimension mapping:

| Result field | POS source |
|---|---|
| salesperson_id | `order.employee_id.user_id` (may be empty) |
| team_id | `salesperson.sale_team_id` (empty if no user) |
| partner_id | `order.partner_id` |
| product_id / categ_id | line product / product category |
| company_id | `order.company_id` |
| date_order | `order.date_order` |
| date_invoiced | `order.invoice_id.invoice_date` |
| date_delivered | `order.picking_id.date_done` |
| ordered_qty / delivered_qty / invoiced_qty | `line.qty` (all equal — POS is all-or-nothing) |
| period/year/month/quarter | bucketed from date_invoiced (monthly, same as SO path) |

## 3. Recompute plumbing

- `_recompute_for_pos_lines(pos_line_ids)` on the result model: one SQL
  aggregation + upsert, mirrors `_recompute_for_sol`. Deletes rows whose line
  no longer qualifies (order not `done`).
- `_recompute_for_pos_orders(order_ids)` convenience wrapper.
- New `models/pos_lite_order.py`: `write()` hook — when `state` changes,
  trigger recompute for the order's lines (post-commit safe, same pattern as
  existing sale/stock/account hooks).
- `_cron_rebuild_all`: after SOL batches, batch over all `pos.lite.order.line`
  of done/cancelled orders and recompute.
- Recompute wizard: extended to also rebuild POS rows.

## 4. Dashboard backend (`spe_dashboard_controller.py`)

- New filter param `source` ∈ {`all`, `sale`, `pos`}; injected into every
  domain (KPI, charts, leaderboards, drill-downs). Default `all`.
- Drill-downs: rows with `source = pos` open `pos.lite.order` records; the
  invoice/credit-note/delivery drills include POS-linked documents via the
  result rows' pos_order_id.

## 5. Dashboard UI polish (no structural change)

- Filter bar: segmented source chips **All | Sales | POS**; compact fields.
- KPI cards: icon per metric, per-card accent color, trend delta vs previous
  equal-length period for Target/Actual/Net; Achievement card shows a progress
  ring.
- Styling: keep teal `#017e84` base; 12px radii, softer shadows, defined
  chart palette, filled gradient line charts, improved typography scale.
- Leaderboards: zebra rows, top-3 rank badges, hover states.

## 6. Security

`ir.model.access.csv` unchanged (result model access already defined). POS
records read in recompute run as sudo (system-generated aggregation), same as
existing paths.

## 7. Testing

`tests/test_pos_lite_recognition.py` (Odoo test runner, tagged post_install):

1. done POS order → result row with correct amounts/dimensions/source.
2. Return order → refund row; net across both rows correct.
3. Cancel done→cancelled order (return case) → rows removed.
4. draft/paid order → no row.
5. Existing SOL flow untouched (constraint coexistence).

Reuse existing warehouse/products on dev DB (orphaned-column quirk — avoid
creating stock.warehouse / product.product in tests).

## Out of scope

Employee-level targets, POS-specific KPI cards, full layout redesign,
pos.lite.payment analytics.
