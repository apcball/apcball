# SP0019100 — FIFO per-warehouse valuation shift correction

Date: 2026-09-08
DB: MOG_LIVE (prod)
Product: SP0019100 (product_id 5942), company_id 1

## Symptom

FIFO on-hand report (stock.fifo.valuation.report, SVL-based) shows RM01 (คลังวัตถุดิบ 1,
warehouse_id 13) ending_qty **47**; actual on-hand stock_quant = **46**.

## Root cause

Move-line source location diverges from move header (known defect class:
type-105 INT moveline/header mismatch).

- stock_move **233445** — Internal Transfer `ROJ0133577`, done 2026-05-21
  - header: 156 (ST01/Stock, wh19) -> 1204 (RM01/QC, wh13), 45u
  - ML 214566: 156 -> 1204, 44u  (matches header)
  - ML **214564**: **108 (RM01/Stock, wh13)** -> 1204, 1u  (src != header src)

The custom warehouse-scoped FIFO engine keys the valuation layer off the move
**header** source, so SVL layer 188929 credited the full 45u as an inflow to
wh13 from outside. 1u of those 45 was already inside wh13 (loc 108) and merely
relocated — net 0 for wh13, not +1.

Effect: 1u of qty+value shifted from wh19 -> wh13 in the SVL ledger.

## Scope

Scan of both `ROJ0133577%` pickings (19801, 29185): **SP0019100 is the only
affected SKU**, single move line 214564.

## Verification of the "shift not loss" diagnosis

| scope | SVL qty | physical (internal quant) |
|---|---|---|
| company-wide (all wh) | 710 | 710  — MATCH, GL intact |
| wh13 RM01 | 47 | 46  (+1) |
| wh19 ST01 | 609 | 610  (-1) |

No account_move tied to move 233445 (internal transfer, no GL). Company total
SVL = physical = GL. Pure per-warehouse attribution error.

## Pre-flight facts (checked 2026-09-08)

- `stock_fifo_valuation_report.cutoff_date` = **2026-03-31**. Correction
  accounting_date `2026-05-21` is after it -> layers are visible in the report. OK.
- `imex_inventory_report.cutoff_date` = 2026-03-31 (same).
- `_check_warehouse_consistency` constraint: `if not layer.stock_move_id: continue`
  -> Row A/B (stock_move_id NULL) are exempt; raw SQL bypasses constraints anyway.
- Method: **raw SQL, one transaction**, not ORM. ORM `create()` on a negative-qty
  layer triggers this module's `_run_fifo()` (memory: known double-subtract bug),
  non-deterministic on which pool layer it consumes. SQL: every column set
  explicitly, deterministic, no hooks.
- Audit cols to set: create_uid=1, write_uid=1, create_date=now(), write_date=now().
- origin fields: Row A (qty<=0) origin_remaining_qty/value = 0; Row B (qty>0)
  origin_remaining_qty 1 / origin_remaining_value 8.46.
- The `stock.fifo.valuation.report` groups by `svl.warehouse_id`, SUMs `quantity`;
  it does NOT read origin_/position fields. Plain layers fix it. Position-layer
  replication (origin_valuation_layer_id etc.) deliberately skipped — over-scoped
  for 1 unit.

## Fix — 3 SQL writes, one transaction

Unit cost 8.46 (current standard_price, and the rate on both warehouses' pools).

1. **Row A** — new SVL, remove 1u from wh13:
   quantity -1, value -8.46, unit_cost 8.46, remaining_qty 0, remaining_value 0,
   warehouse_id 13, current_warehouse_id 13, stock_move_id NULL, account_move_id NULL,
   create_date = now(), accounting_date = '2026-05-21 17:00:00'

2. **Row B** — new SVL, add 1u to wh19 (open, FIFO-available):
   quantity 1, value 8.46, unit_cost 8.46, remaining_qty 1, remaining_value 8.46,
   warehouse_id 19, current_warehouse_id 19, stock_move_id NULL, account_move_id NULL,
   create_date = now(), accounting_date = '2026-05-21 17:00:00'

3. **Decrement wh13 open pool** by 1u (mirror a FIFO consumption for Row A):
   UPDATE layer **203715**: remaining_qty 1 -> 0, remaining_value 8.46 -> 0
   (oldest open wh13 layer; move 246303 transfer-in, qty 10 rem 1)

description on Rows A/B:
`CORRECTION 2026-09-08: move 233445 ML214564 sourced RM01/Stock not ST01 - shift 1u valuation wh13->wh19`

## Post-checks

- wh13 report ending_qty 46, wh19 610  (= physical both)
- company SVL qty 710, value 6119.63  (unchanged)
- wh13 remaining pool 46, wh19 pool 610
- GL untouched

## Rollback

Capture the two new ids at insert (RETURNING id). Then:

```sql
DELETE FROM stock_valuation_layer WHERE id IN (<A>, <B>);
UPDATE stock_valuation_layer SET remaining_qty = 1, remaining_value = 8.46 WHERE id = 203715;
```

Full dump is the backstop, not the tool.

## Finance note

Row A surfaces as `out_qty -1` on any RM01 report covering May 2026; Row B as
`in_qty +1` for ST01. Both are documentless correction lines — expected.

## feat/stock-location-consistency

Move 233445 will keep appearing in the moveline/header mismatch report (header
left at src 156 on purpose). Expected; not a regression.

## Backup

`~/backups/svl_before_sp0019100_fix_20260908_162454.dump` on mog-prod
(pg_dump -Fc -t stock_valuation_layer, 11M).

## EXECUTED 2026-09-08 16:25

One transaction, committed.

- Row A: stock_valuation_layer **id 264605** — wh13, qty -1, value -8.46
- Row B: stock_valuation_layer **id 264606** — wh19, qty +1, value +8.46
- layer 203715: remaining_qty 1->0, remaining_value 8.46->0

Post-checks (all pass):
- wh13 svl_qty 46, pool 46  (physical RM01 = 46)
- wh19 svl_qty 610, pool 610  (physical ST01 = 610)
- company total: qty 710, value 6119.63 — unchanged
- report query with cutoff 2026-03-31 applied: wh13 ending_qty 46, wh19 610

Rollback (if needed):
```sql
DELETE FROM stock_valuation_layer WHERE id IN (264605, 264606);
UPDATE stock_valuation_layer SET remaining_qty = 1, remaining_value = 8.46 WHERE id = 203715;
```

## Do NOT

Run any FIFO recal / regenerate wizard afterwards — it would recompute layers
from moves and re-introduce the shift (move 233445 header still says src 156).
The header is left as-is deliberately (physical history: 1u really did leave 108).
