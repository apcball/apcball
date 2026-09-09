# BUZ Stock Location Consistency

Keeps every `stock.move.line` location (source **and** destination)
inside the subtree of the matching `stock.move` header location.

## Why

The FIFO valuation layer (`stock.valuation.layer`) takes its warehouse
from the **move header**; physical stock (`stock.quant`) follows the
**move line**. When the two land in different warehouses the value and
the quantity silently split: the FIFO valuation report shows the value
in one warehouse, `imex_inventory_report` shows the quantity in another,
and neither matches the other.

Two ways this divergence appears:

- **Source axis.** Odoo core propagates a picking's Source Location
  change to the move **headers** only, never the move lines
  (`stock/models/stock_picking.py` `write()` / `_onchange_locations`).
  Unlike `location_dest_id`, a `location_id` change does not re-run line
  placement.
- **Destination axis.** A move line's destination edited (manually, or
  by a custom flow) to a location outside the header dest subtree — e.g.
  unbuild POJ0012387, whose byproduct produce move headed to FG50 while
  two of its lines were pointed at RM01.

## What it does

- **`stock.move.line` `create()` / `write()` hook** — blocks a line
  whose `location_id` is outside the move header `location_id` subtree,
  or whose `location_dest_id` is outside the header `location_dest_id`
  subtree. Containment, not equality: putaway / reservation splits to a
  child location are fine; a different warehouse is not.
- **`stock.move` / `stock.picking` `write()` guard** — on a
  `location_id` **or** `location_dest_id` change: hard-block `done`
  moves that would gain an out-of-subtree line; `_do_unreserve()` +
  `_action_assign()` for reserved moves on a source change; re-point
  lines for unreserved moves. Only writes that *introduce* divergence
  are blocked — existing broken rows stay editable.
- **`@api.constrains` backstop** on `done` moves.
- **Inventory → Reporting → Location Mismatches** — read-only list of
  current mismatches, with an `axis` column (source / dest / both) and a
  `cross_warehouse` flag (the valuation-breaking subset). Each case is
  repaired manually with a backup and quant/SVL checks. When a case is
  done, select its rows and **Mark Cleared** — a
  `buz.stock.location.mismatch.clearance` row is written per move
  (who / when / optional note), the rows go grey and drop out of the
  default **Open (not cleared)** filter. **Reopen** removes the tag. The
  underlying mismatch is still listed under the **Cleared** filter, so
  nothing is hidden permanently.

## Unbuild into multiple warehouses

Unbuild is designed to return components to several warehouses — one
produce move per component (`buz_mrp_unbuild_enhancement`), each with its
own destination.

- When the destination is set on the **component line**, that module
  already puts it on the produce move **header**, so header == line.
- When the operator instead sets the destination on the **raw move line**
  (Detailed Operations) before posting, the move line is the source of
  truth: for a **not-yet-done** unbuild move whose lines all agree on one
  location, this module **realigns the move header to the line**
  (unreserving/reassigning if needed) so the valuation layer lands in the
  right warehouse. It does not block.
- A **done** unbuild move, or one whose lines point at more than one
  location, is still blocked — retagging those needs the per-case
  quant/SVL analysis.

## Known limitation

Raw SQL writes straight to the database bypass the ORM and this guard.
Detection still catches them (they appear in the report); prevention
does not cover them.

## Bypass

Deliberate repair scripts: `record.with_context(
skip_location_consistency_check=True).write({...})`.
