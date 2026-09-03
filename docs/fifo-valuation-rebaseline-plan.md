# FIFO Valuation Re-baseline — Plan

**Status:** draft for finance sign-off · **Author:** Ball + Lime · **Date:** 2026-09-03

## 1. Problem

`stock.valuation.layer` is the sole book of record for stock value (product
categories are FIFO + `manual_periodic`, most layers carry no journal entry).
The per-warehouse FIFO engine in `stock_fifo_by_location` has mis-costed
inter-warehouse transfers for a long time. Current exposure (MOG_LIVE,
2026-09-03 scan, 15 warehouses):

| Measure | Value |
| --- | --- |
| warehouse/product pairs with net qty 0 but value ≠ 0 | 450 |
| distinct products affected | 417 |
| products where `SUM(value) ≠ SUM(remaining_value)` (COGS desync) | 290 |
| outgoing layers whose value disagrees with a FIFO replay | 28,330 |
| gross value drift on those layers | ~9.13M THB |
| products with value stuck and no stock anywhere ("phantom") | 11 (~46.6k THB net) |
| value residual reported by the recal wizard | 460 pairs / ~545k THB |

The `stock_fifo_by_warehouse_recal` wizard **cannot** fix this: by design it
writes only `remaining_qty` / `remaining_value`, never `value`, because
rewriting outgoing `value` fabricates COGS with nothing to contradict it.
For most affected pairs the "correct" historical value is not recoverable by
replay (FIFO shortage, queue reordered by backdating, no anchor).

Root cause (code) is fixed forward on branch
`fix/fifo-empty-queue-fallback-loud` (module 17.0.2.6.0): the empty-queue
`standard_price` fallback is now loud and can be set to block. It does **not**
repair existing data.

## 2. Decision: re-baseline, do not back-fix

Attempting a per-layer historical correction across 417 products is a
multi-week reconciliation with no reliable source of truth and a real risk of
making the ledger worse. Instead: draw a line, establish correct value at that
line from a physical count, and let history before the line stand as-is
(reported as pre-cutoff opening balance).

## 3. What "cutoff" does and does not do

`stock_fifo_valuation_report.cutoff_date` (system parameter, already
supported) is **report-only**. It moves the report's opening-balance boundary;
it does not touch the FIFO engine. `_get_fifo_queue()` still consumes any
layer with `remaining_qty > 0` regardless of date.

A real re-baseline therefore needs **both**:

1. **Report boundary** — set `stock_fifo_valuation_report.cutoff_date`.
2. **Engine reset** — for every product/warehouse: zero `remaining_qty` /
   `remaining_value` on all layers dated before the cutoff, then insert one
   fresh opening layer per product/warehouse at the counted quantity and the
   agreed unit cost, dated at the cutoff. The engine's queue then starts clean.
   `value` on historical layers is left untouched (no COGS fabrication); only
   the queue state and the new opening layers change.

## 4. Open decisions (finance)

| # | Decision | Options | Note |
| --- | --- | --- | --- |
| D1 | Cutoff date | end of a closed accounting period (e.g. 2026-08-31) | must be a period with no further backdated entries expected |
| D2 | Cost basis for opening layers | (a) last valid FIFO unit cost per product/warehouse from the recal replay; (b) latest purchase price; (c) standard price; (d) finance-supplied list | (a) is closest to book, (b)/(c) simpler, (d) most defensible |
| D3 | Physical count scope | all 417 affected products, or all stocked products, or affected + high-value | a count that covers only the 417 leaves the rest un-validated |
| D4 | GL treatment of the write-off | the net re-baseline delta (opening value − pre-cutoff `SUM(value)`) is a one-time inventory adjustment; which journal / account, which date | transfers themselves carry no GL, but the re-baseline delta is a real P&L event finance must book |
| D5 | Phantom 11 products | fold into the same run, or clear first as a quick separate fix | ~46.6k THB, heterogeneous |
| D6 | Freeze window | inventory operations paused during count + apply, or count-in-place with a reconciliation pass | scale of count drives this |

## 5. Execution phases

### Phase 0 — Prep (no data change)
- Confirm D1–D6.
- Full `pg_dump` of MOG_LIVE (policy).
- Rebuild the docker sandbox (`/srv/docker/odoo_mogen`) from that dump.
- Freeze code: `stock_fifo_by_location` 17.0.2.6.0 deployed, param
  `empty_queue_fallback_mode` still `warning` (flip to `raise` only after
  Phase 3 succeeds).

### Phase 1 — Count
- Physical count per D3, entered as a dated stock-count sheet per warehouse.
- Reconcile count vs `stock_quant` on-hand; investigate every discrepancy
  above tolerance before proceeding (a count error becomes a permanent
  valuation error).

### Phase 2 — Build the re-baseline set (sandbox, dry-run)
- Script produces, per product/warehouse:
  - list of pre-cutoff layers to have `remaining_qty`/`remaining_value` zeroed
  - one opening layer: `quantity` = counted qty, `unit_cost` = D2 basis,
    `value` = qty × unit_cost, `create_date` = `accounting_date` = cutoff,
    `remaining_qty` / `remaining_value` = same, `warehouse_id` set,
    `description` = "Re-baseline opening YYYY-MM-DD".
  - per-product delta: opening value − pre-cutoff `SUM(value)` (feeds D4).
- Output: reconciliation workbook (before / after / delta per product,
  warehouse subtotals, grand total).
- Run the FIFO valuation report on the sandbox with the cutoff set; confirm
  every affected warehouse now reads `ending_qty` = counted, `ending_value` =
  counted × cost, `remaining_value_check` matching.
- Finance signs the workbook.

### Phase 3 — Apply (production, in one transaction)
- Backup tables: `svl_bak_rebaseline_<date>`, and a full `pg_dump`.
- Set `stock_fifo_valuation_report.cutoff_date`.
- Zero pre-cutoff `remaining_*`; insert opening layers (INSERT … SELECT / batch,
  ORM-bypassed, then `invalidate_model`).
- Post the D4 journal entry for the net delta.
- Re-run the valuation report; diff against the signed workbook — must match
  to the cent.
- Bump a cache signal if the report view is materialised.

### Phase 4 — Close out
- Flip `empty_queue_fallback_mode` to `raise` (new empty-queue consumption now
  blocks instead of drifting).
- Monitor the recal wizard's monthly report-only cron: the drift count should
  stay flat. Any new non-zero pair = investigate that transaction immediately.
- Keep the 7381 pilot fix (already on prod) documented as the first instance.

## 6. Rollback

Phase 3 is one transaction. Backup tables restore `remaining_*` and remove the
opening layers; the D4 journal entry is reversed. The report cutoff param is
deleted. Full `pg_dump` is the last resort.

## 6a. Single-product instance log

Applied ad-hoc corrections that follow this plan's spirit (one manual
`quantity = 0` revaluation layer, `remaining_* = 0`, no GL, report picks it up
in the `revaluation_value` bucket):

| Date | Product | WH | Period | Before | After | Layer id | Adjust qty / value |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-09-03 | FCA0006100 (id 1408) | FG10 (id 1) | 01/04–31/05/2026 | qty 229 / val 81,658.26 | qty 217 / val 78,956.23 | 262199 | −12 / −2,702.03 |

Notes: finance-supplied basis 217 @ 363.85 = 78,956.23. The **authoritative
"before" numbers come from running the summary wizard** (`env['stock.fifo.
valuation.report'].init_results(wiz)`), NOT a hand SQL — the report converts
the `cutoff_date` via `_bangkok_day_start_to_utc` (cutoff 2026-03-31 →
`2026-03-30 17:00:00 UTC`), so a layer stored at exactly `2026-03-30 17:00 UTC`
(= 31/03 00:00 Bangkok) is in scope. A naive `COALESCE(...)::date >=
'2026-03-31'` drops it and gives the wrong baseline (first attempt: layer 262198
+1,532.99 off a bad baseline of 77,423.24 — deleted, then redone as 262199).
Adjustment layer: `quantity = −12`, `value = −2,702.03`, `unit_cost ≈ 225.17`,
`accounting_date = 2026-05-31`, `remaining_* = 0`, no move, no GL. Report
`out_qty` for the period rises 212 → 224 (the −12 lands in the outgoing bucket).
FIFO engine untouched (`SUM(remaining_qty)` 178 / `SUM(remaining_value)`
63,818.23 unchanged). Backup: `svl_bak_fca0006100_20260903` +
`/tmp/MOG_LIVE_pre_fca0006100_20260903.dump` (172M) on mog-prod. Rollback:
`DELETE FROM stock_valuation_layer WHERE id = 262199;`.

## 7. Out of scope

- Rewriting historical `value` on any layer.
- Fixing the 11,286 layers whose id order disagrees with `create_date` order
  (separate backdating-tool artifact; does not block this plan).
- Changing product cost method or valuation method.
