# BUZ Stock Location Consistency

Keeps `stock.move.line.location_id` inside the subtree of its
`stock.move.location_id` (the header source).

## Why

Odoo core propagates a picking's Source Location change to the move
**headers** only, never to the move lines (`stock/models/stock_picking.py`
`write()` / `_onchange_locations`). Unlike `location_dest_id`, a
`location_id` change does not re-run line placement. So editing a
transfer's source after operations exist silently leaves the header and
its lines in different locations — which desynchronises the FIFO
valuation report (keyed on the SVL/header warehouse) from
`imex_inventory_report` (keyed on the move line location).

## What it does

- **`stock.move` / `stock.picking` `write()` guard** — on a
  `location_id` change: hard-block `done` moves that would gain a
  line outside the new subtree; `_do_unreserve()` + `_action_assign()`
  for reserved moves; re-point lines for unreserved moves. Only writes
  that *introduce* divergence are blocked — existing broken rows stay
  editable.
- **`@api.constrains` backstop** on `done` moves.
- **Inventory → Reporting → Location Mismatches** — read-only list of
  current mismatches. No fix button; each case is repaired manually
  with a backup and quant/SVL checks.

## Known limitation

Raw SQL writes straight to the database bypass the ORM and this guard.
Detection still catches them (they appear in the report); prevention
does not cover them.

## Bypass

Deliberate repair scripts: `record.with_context(
skip_location_consistency_check=True).write({...})`.
