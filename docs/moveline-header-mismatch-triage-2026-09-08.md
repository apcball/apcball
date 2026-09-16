# Move-line / move-header location mismatch — bulk triage

**Date:** 2026-09-08
**Scope:** 200 `done` `stock_move_line` rows on MOG_LIVE where `stock_move_line.location_id != stock_move.location_id`

## Root cause (confirmed)

Every one of the 200 moves has `stock_move.write_date = 2026-08-19 03:33:08.183915`, `write_uid = 1` (OdooBot) —
a single bulk write that rewrote `stock_move.location_id` (the header source) and did **not** touch
`stock_move_line.location_id`. Not found as a committed migration; likely a server action or an
ad-hoc shell script. `stock_fifo_by_location/migrations/populate_location_id.py` only backfills
SVL.location_id (a different field) — not this.

0 of the 200 lines have a GL-posted valuation layer (`account_move_id IS NULL` everywhere).

## Shape

- 15 lines: `ml_src == ml_dst` (the no-op line — e.g. `76→76` on a `1220→76` move)
- 185 lines: `ml_src != ml_dst`, `ml_dst == m_dst`, `ml_src != m_src` — the line kept a real
  (different) source; the header was moved off it

## Buckets

### A — same-warehouse, clean quant math (46 lines)  — but almost all RBG void-chains
types: 273×44, 275×1, 325×1.
`ml_src=68 (FG30/Stock, wh8)` → `m_src ∈ {1039,1044,1061,1062,1208}` (FG30 show sub-locations, all wh8).
Same warehouse ⇒ no SVL warehouse / FIFO impact; fixing the line src is a pure location-tag move.
**BUT** the pickings are `RBG-690375 ยกเลิก`, `RBG-690442`, `RBG/2606136 ยกเลิก`, `RBG/2608049 (cancle)` …
— the same void / return / re-issue chains that `RBG-690439` needed (inv-adj + backdate + per-unit
reconcile). The SVL IN-layer on these also sits at the source, not the `76` dest — a second defect.
Not safe to batch blind; each picking needs the `RBG-690439` treatment.

Pickings: FG10/EMCP/00057, FG10/EMTN/00636, RBG-690375 ยกเลิก(7), RBG-690377 ยกเลิก(3),
RBG-690378 ยกเลิก(1), RBG-690390 ยกเลิก(1), RBG-690442(11), RBG-690443 ยกเลิก(6), RBG-690448 ยกเลิก(1),
RBG-690453(1), RBG-690454 ยกเลิก(2), RBG-690510 ยกเลิก(1), RBG/2606052 ยกเลิก(1), RBG/2606053 ยกเลิก(1),
RBG/2606054 ยกเลิก(1), RBG/2606136 ยกเลิก(4), RBG/2608049 (cancle)(3)

### B — cross-warehouse (52 lines) — SVL warehouse + FIFO impact, per-case
types: 105×16, 125×20, 225×6, 290×5, 324×2, 9×2, 2×1.

> **2026-09-08 — bucket B splits into two sub-shapes. `fifo_validators.py` does NOT discriminate**
> (it compares the layer to the *current* header, so it passes whenever SVL agrees with the header
> — including when both are wrong). The real test: does the SVL OUT `warehouse_id` equal where the
> goods **physically were**, established independently of the header (receipt history, sibling
> pickings, quant reconcile at the line's original location)?
>
> - **B1 — SVL follows the correct source** (e.g. BI/2607088, BI/2608008). Header was right at
>   done-time; only the move_line drifted; SVL OUT/IN `warehouse_id` already correct. Fix =
>   `move_line.location_id → header` + quant shift. **No reprice.** `stock_fifo_by_location` keys
>   the FIFO queue on `warehouse_id` not `location_id` (`product_product.py:61`); the layer's
>   `location_id` is just the move source on both legs (healthy peer BI/2607079 identical).
> - **B2 — SVL follows a wrong source** (e.g. RM01260600092/094 + RM01260700275, all product
>   409250065, moves 242166/242180/298208). Header wrong ALREADY at validation (SVL create_date =
>   done date, not post-Aug-19); line RM01/Stock + quant correct; SVL OUT booked ST01(wh19) queue
>   instead of RM01(wh13). Total 84 units / 57.41 THB misrouted; RM01 FIFO queue inflated +51
>   units (3 IN layers 199066/199076/237785 unconsumed vs RM01/QC quant 0); no GL.
>
>   **2026-09-08: applied then ROLLED BACK — wrong direction.** User (warehouse authority)
>   confirmed 409250065 was physically picked from **ST01**, like the other two products in each
>   picking. So the header (ST01) was right and the **move_line (RM01/Stock) is the wrong field** —
>   plain B1, not B2. The RM01/Stock inference was wrong: quant reconciles at any untouched line
>   position, and RM01260600094 carries the same defect rather than being a healthy sibling flow.
>   Restored from `/tmp/bk409_*.csv` via `scratchpad/rollback_409250065.sql` (3 moves + 9 SVL
>   layers to exact pre-fix values). Correct fix now = `move_line.location_id 108→156` + quant
>   shift (RM01/Stock −qty / ST01 +qty) per picking, SVL untouched.
>
>   ~~FIXED on prod 2026-09-08~~ (superseded, kept for the lesson). The
>   "settle COGS first, by a person" the wizard demands = write SVL `value` on the 3 OUT legs to
>   the wh13 FIFO replay's COGS, mirror onto the paired IN legs (transfer stays net-zero), then
>   let the replay drive `remaining_qty`/`remaining_value` on both warehouses directly (bypassing
>   the wizard's reorder gate on wh19, which `inverted 2` would have tripped — aggregate reconciles
>   either way, the guess only decides which ST01 layer holds the restored 7 units).
>
>   Script: `scratchpad/fix_409250065.py` (idempotency guard: aborts unless all 3 headers still
>   at 156). Applied: headers 156→108; SVL OUT 199065/199075/237784 → wh13/loc108, value
>   −18.72/−28.08/−18.72; SVL IN 199066/199076/237785 → loc108, value +mirror; `remaining_*` on
>   6 layers (196630 63→12, IN legs remval bump, 160091 0→7, 260472 value 29.44→26.40).
>   Result: ST01 47/47 book −32.04→+25.37, RM01 116/116 book 147.18→89.77 (±57.41, un-misroute
>   signature), header/line mismatch 0, quant untouched, `fifo.recalculation.wizard` preview
>   now `layers_changed=0`. No GL. **June/August FIFO summary reports for ST01+RM01 shift ~57 THB
>   retroactively.** Docker-tested first (`docker exec odoo`, DB copy 2026-09-02). Backups:
>   `mog-prod:/tmp/bk409_{move,ml,svl,quant}.csv` (all 28 layers of 409250065 at wh13/19) +
>   `/tmp/bkrm_*.csv`.
>
>   **EXECUTED 2026-09-08 09:42 — RM01260600092 only (move 242166, ml 223334, 24u).**
>   Corrected-direction B1 fix per the rollback note above. Header already 156 (restored by
>   `rollback_409250065.sql`); SVL 199065 OUT already wh19/ST01 (physical source) — untouched.
>   Applied: `stock_move_line 223334`.location_id `108 → 156`; quant shift via shell
>   `_update_available_quantity` — ST01/Stock(156) `47 → 23`, RM01/Stock(108) `116 → 140`.
>   Verify: ml_src == m_src (156), mismatch row gone; quant == move_line net at both locations
>   (156 = 23, 108 = 140); SVL 199065/199066 unchanged; no GL; no reservations.
>   Backups: `mog-prod:~/backups/rm092_{ml,quant,svl}_20260908.csv`.
>   **EXECUTED 2026-09-08 ~10:00 — RM01260600094 (move 242180, ml 223382, 36u) +
>   RM01260700275 (move 298208, ml 274052, 24u).** Same B1 fix. `stock_move_line.location_id
>   108 → 156` on both; SVL 199075/199076 + 237784/237785 untouched (OUT already wh19/ST01).
>   Quant shift needed ST01/Stock 23 → −37 which trips Odoo's `_check_negative_qty` (no
>   negative stock allowed for this product/location) — the shell `_update_available_quantity`
>   path raised `ValidationError`. Applied via raw SQL one txn instead: quant 47041 (ST01/Stock)
>   `23 → -37`, quant 57741 (RM01/Stock) `140 → 200`. The −37 is the shortage the SVL ledger
>   already carried (wh19 SVL qty = −37), now surfaced in the quant — not a new loss.
>
>   **CONSTRAINT STILL ARMED.** `_check_negative_qty` (`@api.constrains('quantity')`;
>   `stock_location 156`.allow_negative_stock NULL, product flag off) fires on every future write
>   to this quant. ST01/Stock is effectively **frozen for 409250065**: any outbound, or any
>   inbound not reaching ≥ 0 in a single write, raises `ValidationError` and blocks the picking.
>   Only a write landing at ≥ 0 passes. Warehouse-authority choice: (a) leave frozen as a forcing
>   function for the recount; (b) set `allow_negative_stock` on product 10764 or location 156 so
>   normal ops continue while the −37 stays visible.
>   **RESOLVED 2026-09-08: user chose (b).** `product_template 10786`.allow_negative_stock →
>   True (product 10764). ST01/Stock ops for this SKU no longer blocked; −37 stays visible as
>   the recount signal.
>
>   Also checked: both pickings RM01260600094 / RM01260700275 have **0** header/line mismatch
>   rows across all products (not just 409250065) — the documents are fully clean.
>   Final reconcile (all 3 pickings): 0 header/line mismatch rows for product 10764;
>   quant == move_line net (ST01/Stock −37, RM01/Stock 200); quant == SVL per warehouse
>   (wh19 −37, wh13 200); company phys 163 == SVL 163; no GL.
>   Backups: `mog-prod:~/backups/rm094_275_{ml,quant,svl}_20260908.csv`.
`ml_src` and `m_src` are in different warehouses (e.g. 116 wh14 → 1205 wh15; 108 wh13 → 76 wh9;
188 wh23 → 8 wh1). Fixing either the line or the header changes which warehouse queue the layer
belongs to — cannot be done without re-pricing. Handle one picking at a time.

Notable: BROJ0006706, BROJ0006833(10711), BROJ0008524/8639/8794/8798/8800, PD01/INT/260600001/480,
RM11/IMTN/00269(2028), RM11/IMTN/00270(4028), 15× ROJ01313xx, BI/2607088 ยกเลิก(4), BGD-00220x Return.

### C — target location empty / supplier (102 lines) — needs a decision
types: 273×71, 290×8, 324×5, 105×9, 125×4, 275×2, others.
The header now points at a location with **zero** stock for that product (no quant row), or at a
supplier/customer location. Fixing the line to the header drives that location negative.
Two possibilities per case: (a) the 2026-08-19 write over-corrected — revert
`stock_move.location_id` back to the line's source; (b) the sub-location was genuinely emptied by a
later picking (a timing negative), same as `RBG-690439`. Requires per-chain reconciliation.

Dominated by RBG void chains: RBG-690443 ยกเลิก(18), RBG-690454 ยกเลิก(11), RBG-690464 ยกเลิก(7),
RBG/2606136 ยกเลิก(9), plus EMTN017682/684/685/690/691 (the paused 5638 batch), BROJ0006925/6943,
BROJ0007011/7013.

## Recommendation

There is **no safe blind bulk SQL** for this. Every bucket needs the same per-picking verification
the individual fixes in this session used (backup → check quant math + reservations + SVL warehouse
→ apply → verify). The RBG (type 273) chains — 115 of the 200 lines — are the same tangled
void/return/re-issue pattern as `RBG-690439` and should be worked chain by chain with warehouse-team
input on where each physical unit actually is.

Fixed so far this session (per-case, backups in `mog-prod:/tmp/`):
PD01/INT/260600222, PD01/INT/260600458, BROJ0006698, BROJ0006833(9622), RM11/IMTN/00251,
RM11/IMTN/00256, ISP6900083, EMTN017693/694/698/712, RBG-690439, BI/2606048(5923).

**2026-09-08 — BI/2607088 (bucket B, type 225, lines 274378/274384/274392/274393).**
Origin BI/2607054 = FG10→OT01 loan of the same 4 units ("รับคืนสินค้ายืม"); BI/2607088 =
OUTLET→NC damaged return. Header (OT01→FG40) was correct at done-time; uid 29 (นภาพร) had
edited both header and line today leaving line src = FG10. SVL already correct (see caveat above).
Fix: `move_line.location_id 8→188` ×4 + `_update_available_quantity` OT01 −1 / FG10 +1 per
product (MAM011C115, MAC020C11, MA0433101, F043E5C022). Committed; 0 mismatch rows; quant ==
move_line net at every location; 8 SVL layers unchanged.
Backups: `mog-prod:/tmp/BI2607088_backup_20260908.sql` (full 4 tables, 968MB) +
`/tmp/bk_{move,ml,svl,quant}.csv` (touched rows).
New negative on-hand: OUTLET F043E5C022 → 0 (not negative); OUTLET balances now
MAM011C115=2, MAC020C11=1, MA0433101=3, F043E5C022=0 — warehouse to confirm physical count.

**2026-09-08 — BI/2608008 (same pattern, 1 line 277597, product VTMAE08R1).**
Origin BI/2608001 = FG10→OT01 loan; chatter "คืนตัวโชว์ ขอบบิ่น / รับคืนสินค้ายืม". Header
(OT01→FG40) touched by the Aug-19 OdooBot bulk write but SVL wh already correct (OUT=OT01 wh23,
IN=NC wh9, no GL). Line kept FG10 (done-time, uid 35). Fix: `ml.location_id 8→188` + quant
OT01 −1 (2→1) / FG10 +1 (9→10). SVL 241001/241002 untouched. 0 mismatch; quant == ml net.
Backups `mog-prod:/tmp/bk8_{move,ml,svl,quant}.csv`. OUTLET VTMAE08R1 now = 1 — warehouse to confirm.

**2026-09-08 — RM11/IMTN/00269 (type 324, shape A, move 274135 / line 253116, product 2028
ACS03602100).** Claim chain origin POS0021050: FG10/EMTN/00051 (8→1220, re-done 2026-09-07) →
RM11/IMTN/00269 (1220→76, claim→NC). Line was no-op `76→76`; header `1220→76` correct. SVL
220313/220314 warehouse_id (OUT 16 / IN 9) + source_warehouse_id already correct — only the IN
layer's `location_id` tag was stale (1220 not 76). Earlier PAUSE reason ("2028 no inbound at 1220
→ goes −1") went stale once 00051 landed the unit at 1220. Fix: `ml.location_id 76→1220`; quant
RM11/EMTN(1220) `1→0`, FG40/Stock(76) `2→3`; `SVL 220314.location_id 1220→76` +
complete_name `FG40/Stock`. Header + SVL warehouse/qty/value untouched; no GL. 0 mismatch for
274135; quant == ml net. Backups `mog-prod:~/backups/imtn269_{ml,quant,svl}_20260908.csv`.
**2026-09-08 — RM11/IMTN/00270 (type 324, shape A, move 274140 / line 253117, product 4028
MA00001B0010000).** Same as 00269 (chain origin POS0023154, FG10/CM11/00542 claim return).
Line `76→76` → `1220→76`; `SVL 220296.location_id 1220→76` + complete_name `FG40/Stock`
(warehouse_id 9 / src_wh 16 unchanged, OUT 220295 untouched). quant RM11/EMTN(1220) `2→1`,
FG40/Stock(76) `0→1` (new row). Pause reason (open RM11/IMTN/00614 reserving 1 unit at 1220)
handled: `do_unreserve` 00614 → fix → `_update_available_quantity` → `action_assign` 00614
re-grabbed the remaining unit. Final: 1220 qty 1 / reserved 1, 76 qty 1; 00614 assigned;
0 mismatch for 274140; quant == ml net. No GL.
Backups `mog-prod:~/backups/imtn270_{ml,quant,svl}_20260908.csv`.

**2026-09-08 — EMTN017682/684/685/690/691 (type 324, shape A, product 5638 ×5). Type-324
mismatch list now EMPTY.** Each: claim move `8→1220`, move line `1220→1220` no-op. All 5 SVL
pairs already booked OUT wh1 (FG10) / IN wh16 (RM11) at done-time (value 460.41 ea, no GL) —
so SVL wh1 for 5638 was already −5 while quant loc 8 = 0. User (warehouse authority) confirmed
5638 picked from FG10/Stock (same as co-product 6233 whose line was correct). Fix: `ml.location_id
1220→8` ×5 (lines 253363/253350/253215/252830/252829); SVL IN layers
220999/221015/221023/221031/221039 `location_id 8→1220` + complete_name `RM11/EMTN` (warehouse_id
16 + OUT layers untouched); quant FG10/Stock(8) `0→−5` (now matches SVL wh1 −5),
RM11/EMTN(1220) `6→11`. `product_template`.allow_negative_stock → True on 5638 (the −5 is a
surfaced shortage / recount item, same as RM01260600094/275). EMTN017715 move 306007 had a
phantom reservation at loc 8 (qty 0 / reserved 1) → `do_unreserve`; that 5638 move stays
`confirmed`, its other 2 product moves remain assigned. Company phys 467 == SVL 467.
Backups `mog-prod:~/backups/emtn5638_{ml,quant,svl,prodflag}_20260908.csv`.

**Type-324 batch (picking_type_id 324) is now fully cleared** — the find-offenders query returns 0.

Raw dataset: `scratchpad/bulk_analysis.csv` (201 rows, all fields).
Query to regenerate the population:
```sql
SELECT ml.id, sp.name, sp.picking_type_id, m.location_id m_src, ml.location_id ml_src,
       m.location_dest_id m_dst, ml.location_dest_id ml_dst
FROM stock_move_line ml
JOIN stock_move m ON m.id = ml.move_id
JOIN stock_picking sp ON sp.id = ml.picking_id
WHERE ml.state = 'done' AND ml.location_id <> m.location_id;
```
