# buz_stock_count_adjust — Design Spec

Date: 2026-09-04
Status: approved (approach A), pending user review of this spec
Author: Lime (มะนาว) / Ball

---

## 1. Purpose

Turn the manual "adjust FIFO qty + value at a cutoff date, then recompute
post-cutoff COGS, then reconcile physical stock" procedure — run by hand this
session for FCA0006100 @ FG10 on the docker MOG_LIVE test stack — into a
UI-driven Odoo module usable for many products at once, with backup / preview /
apply / rollback and an audit trail.

Target deployment: docker test stack first (`/srv/docker/odoo_mogen`, DB
MOG_LIVE), then prod-native `instance1` (MOG_LIVE, systemd). Prod-bound → full
safety rails.

## 2. Reference — the manual procedure (what the module automates)

For one product at one warehouse, as of a cutoff date (Asia/Bangkok, UTC+7):

1. **Backup** — snapshot every row the run will touch.
2. **Baseline** — run `stock.fifo.valuation.report.wizard` at `date_to = cutoff`
   to get authoritative ending qty `Q0` / value `V0` (buckets by
   `accounting_date`, NOT `create_date` — tz boundary matters). Delta
   `dQ = target_qty − Q0`, `dV = target_value − V0`.
3. **Void-and-reseed** (raw SQL INSERT — ORM `create()` on
   `stock.valuation.layer` stamps NOW() and fires the `_run_fifo` /
   `_run_fifo_vacuum` cascade):
   - one counter layer: `quantity = −Q0`, `value = −V0`, `remaining 0/0`
   - N bucket layers (from the target rows): `quantity == remaining_qty`,
     `value == remaining_value`, ordered
   - `create_date` just before the cutoff UTC instant, spaced by µs for bucket
     order; `accounting_date = <cutoff-date> 00:00:00`
   - then `UPDATE ... SET remaining_qty = 0, remaining_value = 0` on all
     pre-cutoff layers for the pair
   - Invariant: `SUM(inserted quantity) = dQ`, `SUM(inserted value) = dV`;
     every bucket layer `quantity == remaining_qty` and
     `value == remaining_value`.
4. **Scoped FIFO recal** — do NOT use
   `stock.valuation.layer._fifo_replay_remaining` (full history: reprices
   closed periods months back; its `inverted` count is inflated by the
   backdated inserts and `stock_fifo_by_warehouse_recal` will skip the pair
   anyway). Instead reuse its inner loop but:
   - seed the pool **literally** from the bucket layers
   - walk only layers with `create_date > cutoff`, ordered `create_date, id`
   - same semantics: live-rate `entry['value'] / available`, `EPS = 1e-4`,
     delete-on-exhaust
   - write `remaining_qty` / `remaining_value` per `expected`; write
     `value` + `unit_cost` per `cogs`
   - assert `shortage < 1e-3` or abort the line
5. **Physical qty** (`stock_quant` is independent of SVL):
   - determine the correct adjustment delta from the **move-history running
     balance just before the cutoff** (not from `inventory_quantity` minus
     today's quant — those differ when history is off)
   - Odoo inventory adjustment via `quant.action_apply_inventory()` with
     `skip_warehouse_consistency_check` context
   - backdate the generated `stock_move.date` / `stock_move_line.date` to the
     cutoff
   - **neutralise the generated SVL** to `0/0/0/0` (valuation already at target
     from step 3)
   - re-run step 4 to restore bucket remaining the transient move consumed
6. **Reconcile & detect corrupted move-lines** — per post-cutoff SVL, compare
   `svl.quantity` to its `stock_move`'s net qty at the pair's stock location.
   A mismatch usually means a done `stock_move_line` whose
   `location_id` / `location_dest_id` disagree with the move header (this
   session: an inter-warehouse transfer line reading `RM01→RM01` instead of
   `FG10→RM01`, so the source quant was never decremented while the SVL
   correctly booked the outflow). **Detect + report only** — a human clicks
   "Fix" per row.

GL: product categories here are `manual_periodic` + `fifo` → most layers carry
no `account_move_id`, so no journal entry work. The module MUST check
`categ_id.property_valuation`; if `real_time`, it stops and reports (out of
scope for v1).

## 3. Module layout

`buz_stock_count_adjust/` (buz_ prefix per CLAUDE.md).

```
__manifest__.py         depends: stock, stock_account, stock_fifo_by_location,
                                 stock_fifo_by_warehouse_recal
models/
  stock_count_adjustment.py         # header
  stock_count_adjustment_line.py    # target rows (buckets)
  stock_count_adjustment_mismatch.py# step-6 findings
  stock_count_adjustment_backup.py  # + backup.line
  count_adjust_engine.py            # AbstractModel: the 6-step engine, dry_run flag
wizard/
  stock_count_adjustment_import.py  # xlsx/csv upload -> lines
security/
  count_adjust_security.xml         # group: Stock Count Adjustment (empty on install)
  ir.model.access.csv
views/
  stock_count_adjustment_views.xml  # form (tabs: Lines / Preview / Mismatches / Log), tree, menu
  stock_count_adjustment_backup_views.xml
data/
  (none — no cron; manual only)
tests/
  __init__.py
  test_count_adjust.py
```

## 4. Data model

### stock.count.adjustment (header)
| field | type | notes |
|---|---|---|
| name | Char | seq `SCA/####` |
| company_id | Many2one res.company | required, `_check_company` |
| cutoff_date | Date | required — the count date |
| state | Selection | draft / previewed / applied / rolled_back |
| line_ids | One2many line | |
| mismatch_ids | One2many mismatch | filled by preview/apply |
| backup_id | Many2one backup | set on apply |
| preview_log / apply_log | Text | readonly |
| valuation_delta / cogs_delta / qty_delta | Float | computed totals, readonly |

Buttons: `action_preview`, `action_apply`, `action_rollback`,
`action_import` (opens wizard).

### stock.count.adjustment.line
| field | type | notes |
|---|---|---|
| adjustment_id | Many2one | ondelete cascade |
| product_id | Many2one product.product | required |
| warehouse_id | Many2one stock.warehouse | required |
| bucket_seq | Integer | default 10, step 10 — order within a pair |
| target_qty | Float | |
| target_value | Float | |
| note | Char | |
| baseline_qty / baseline_value | Float | computed on preview |
| delta_qty / delta_value | Float | computed |
| state | Selection | pending / previewed / applied / skipped / error |
| result_note | Char | shortage, real_time category, etc. |

A (product_id, warehouse_id) group with >1 line = ordered FIFO buckets;
their target_qty / target_value must each be the **absolute** bucket contents,
not deltas. Sum across the group is the pair's ending state.

### stock.count.adjustment.mismatch
| field | type | notes |
|---|---|---|
| adjustment_id | Many2one | |
| product_id / warehouse_id | Many2one | |
| svl_id | Many2one stock.valuation.layer | |
| move_id | Many2one stock.move | |
| move_line_id | Many2one stock.move.line | the suspect line |
| svl_qty / move_net_qty / diff | Float | |
| suggested_location_id | Many2one stock.location | best guess (pair's lot_stock_id) — shown, not auto-applied |
| state | Selection | open / fixed / ignored |

Button `action_fix_move_line` (per row): sets `move_line_id.location_id` (or
dest) to `suggested_location_id`, adjusts both side quants by `diff`, marks
`fixed`. Button `action_ignore`.

### stock.count.adjustment.backup + .line
Snapshot BEFORE apply. Stores, per touched `stock.valuation.layer` row:
`layer_id, quantity, value, remaining_qty, remaining_value, unit_cost,
was_inserted (bool)`. Plus touched `stock_quant` (`quant_id, quantity`) and
`stock_move_line` (`move_line_id, location_id, location_dest_id`).
`action_restore`: `UPDATE` columns back; `DELETE` layers where
`was_inserted`; restore quant / move-line rows. State active → restored.

## 5. Engine (`count.adjust.engine`, AbstractModel)

One public entrypoint:

```python
def run(self, adjustment, dry_run=True):
    # per line-group (product, warehouse):
    #   _baseline(group, cutoff)         -> Q0, V0  (report wizard)
    #   _check_category(product)         -> abort group if real_time
    #   _void_and_reseed(group, ...)     -> counter + buckets (raw SQL), zero pre-cutoff
    #   _scoped_replay(group, cutoff)    -> remaining + cogs writes; abort if shortage
    #   _quant_adjust(group, cutoff)     -> inventory adj + backdate + neutralise SVL
    #   _scoped_replay(group, cutoff)    -> again (restore bucket remaining)
    #   _reconcile(group, cutoff)        -> emit mismatch rows
    # dry_run: whole thing in one savepoint, rolled back, results captured
```

- `_scoped_replay` reuses `stock.valuation.layer._fifo_replay_remaining`'s
  consume loop. Preferred: extract that loop into a shared classmethod on
  `stock.valuation.layer` (small PR to `stock_fifo_by_location`) that both the
  origin and this engine call, so they cannot drift. Fallback if that PR is not
  wanted: copy the loop verbatim with a comment pointing at the origin, plus
  test #4 pinning identical output on a fixture.
- All writes that ORM `create()` would corrupt (`stock.valuation.layer`
  create_date, cascade) go through `env.cr.execute` raw SQL, mirroring
  `fifo_reset_engine`.
- Backdate: raw `UPDATE stock_move / stock_move_line SET date = <cutoff>`
  after `action_apply_inventory`.

## 6. Import wizard

`stock.count.adjustment.import` — transient, `binary` field for the file,
`selection` for format (xlsx / csv). Columns (header row required):
`product_code, warehouse_code, target_qty, target_value, note`.
- `warehouse_code` matched against `stock.warehouse.code` (accept
  `FG10` or `FG10/Stock` — strip `/…`).
- multiple rows same (product_code, warehouse_code) → bucket_seq 10, 20, 30…
  in file order.
- unknown code → row rejected, listed in wizard result; nothing imported until
  all rows resolve OR user ticks "import valid rows only".
- appends to `adjustment.line_ids` (does not clear existing).

## 7. Safety / flow

```
draft ──action_preview──> previewed ──action_apply──> applied ──action_rollback──> rolled_back
  ^                          |                          |
  └──── edit lines ──────────┘                          └── (rollback also available from applied)
```

- **Preview** is mandatory before Apply (`state must be previewed`, and lines
  unchanged since — hash the line set; edit resets to draft).
- **Apply** always writes a backup record first; if the backup can't be
  written in full, nothing else runs.
- **Rollback** available from `applied`; restores SVL columns, deletes inserted
  layers, restores quant + move-line rows, sets `rolled_back`.
- External `pg_dump` is still recommended in the form's help text (table-scoped:
  `stock_valuation_layer account_move account_move_line stock_move
  stock_move_line stock_quant` — full dump blocks on `max_locks_per_transaction`
  on the docker cluster).
- Security: everything gated on group `Stock Count Adjustment`, empty on
  install, not granted by Inventory Manager.

## 8. Edge cases (must handle)

| case | behaviour |
|---|---|
| category `real_time` | skip group, `result_note`, don't touch it |
| `_scoped_replay` shortage > 1e-3 | skip group, error state, report |
| target rows for a pair sum to negative qty | allow (counter can exceed), but warn |
| pair has locked SVL layers | skip group, report (mirrors recal wizard) |
| `stock_quant` has reserved qty > target | apply anyway if target ≥ reserved; else error |
| no post-cutoff layers | steps 4/6 are no-ops, still fine |
| backdated LC layer (qty 0) inside window | replay handles via `stock_landed_cost_id` branch |
| running the same adjustment twice | Apply refuses when `state != previewed`; a fresh doc for the same pair/date should detect Q0 already == target and produce dQ≈0 |
| report wizard stale rows | engine creates a fresh wizard record per baseline call, never reuses |

## 9. Testing (`tests/test_count_adjust.py`, Odoo test runner)

Build a fixture in `setUp`: one FIFO product, one warehouse, a handful of
receipts + deliveries straddling a cutoff date, `manual_periodic` category.

1. `test_baseline_matches_report_wizard` — engine Q0/V0 == wizard output.
2. `test_void_reseed_invariant` — after reseed, report ending @cutoff ==
   target; `SUM(inserted quantity) == dQ`; buckets `quantity == remaining_qty`.
3. `test_scoped_replay_no_shortage` — post-cutoff outgoing repriced, shortage 0,
   ending on-hand == expected.
4. `test_scoped_replay_matches_origin` — same input → same output as
   `_fifo_replay_remaining`'s consume loop on a no-backdate fixture.
5. `test_quant_adjust_and_neutralise` — quant hits target; generated SVL is
   0/0/0/0; move backdated.
6. `test_reconcile_detects_corrupted_move_line` — plant a move_line with
   mismatched locations, assert one mismatch row with the right
   `move_line_id` and `diff`.
7. `test_rollback_restores` — snapshot, apply, rollback → every touched row
   back to pre-image, inserted layers gone.
8. `test_real_time_category_skipped`.
9. `test_preview_then_edit_resets_state`.

Note: `--test-enable` runs against the live DB — the fixture must be
self-contained and the test must clean up (or accept the standard Odoo
test-transaction rollback; no `cr.commit` in tests).

## 10. Deployment

1. `bash scripts/deploy.sh dev buz_stock_count_adjust`
2. `ssh dev "docker exec odoo odoo -d MOG_DEV -u buz_stock_count_adjust
   --test-enable --stop-after-init --no-http"` — but note the real target is
   the docker MOG_LIVE test stack on mog-prod, not MOG_DEV; deploy path there:
   `rsync -az --delete ./buz_stock_count_adjust/
   mog-prod:/srv/docker/odoo_mogen/custom-addons/buz_stock_count_adjust/`
   then `ssh mog-prod "docker exec odoo odoo -d MOG_LIVE -u
   buz_stock_count_adjust --stop-after-init --no-http"` and `chmod -R +r`.
3. Manual confirm before prod-native (`instance1`).
4. Version bumps: manual confirm (CLAUDE.md rule).

## 11. Out of scope (v1)

- `real_time` valuation categories / GL journal reposting
- automatic move-line repair (detect + manual only)
- scheduled / cron operation
- multi-company batch in one document (one company per doc)
- undo of a rollback

## 12. Reference material

- Session worktree plan: `plan_fca0006100_docker_31may.md` (the hand-run:
  SVL 261421 counter, 261422-24 buckets, 261426 qty-adj, move 327045,
  move_line 245369 fix).
- Memory: `fifo-void-reseed-and-scoped-recal`, `docker-mog-live-test-stack`,
  `fifo-single-product-revaluation-layer`, `fifo-warehouse-recal-module-danger`,
  `backup-before-prod-data-changes`.
- Existing patterns to follow: `stock_fifo_by_warehouse_recal`
  (`fifo.recalculation.wizard` preview/apply/backup/rollback,
  `fifo.recalculation.backup.action_restore`), `fifo_reset_engine`
  (raw-SQL SVL writes, tz cutoff handling), `stock_fifo_by_location`
  (`_fifo_replay_remaining`, `_get_fifo_queue`, `stock_quant._apply_inventory`
  override).
