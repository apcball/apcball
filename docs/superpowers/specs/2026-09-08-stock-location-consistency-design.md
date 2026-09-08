# buz_stock_location_consistency — Design Spec

**Date:** 2026-09-08
**Author:** Ball @ Mogen Co. (with Claude Sonnet 5)
**Status:** Approved for implementation
**Session:** https://claude.ai/code/session_01EURL2V8aFmrCbGjLSSboBS

---

## 1. Problem

On MOG_LIVE there are ~200 `done` `stock_move_line` rows where
`stock_move_line.location_id` sits **outside the subtree** of its
`stock_move.location_id` (the header). They were introduced by a single
bulk write on 2026-08-19 03:33:08 (uid 1 / OdooBot) that changed
`stock_move.location_id` without touching the matching move line —
likely a migration script or hand cleanup. 25 of those rows were
repaired per-case in a prior session (see memory
`type105-int-moveline-header-mismatch`); ~175 remain.

The downstream damage: the FIFO valuation report keys off
`stock_valuation_layer.warehouse_id` (derived from the move header)
while `imex_inventory_report` keys off `stock_move_line.location_id`.
When the two diverge across warehouses, the reports disagree and
physical stock no longer matches valuation.

### Root cause in Odoo core

`stock/models/stock_picking.py::write()` propagates a `location_id`
change to `self.move_ids` (the move **headers**) only — never to
`move_line_ids`. `_onchange_locations` raises a soft, ignorable warning
("You might want to update the locations of this transfer's
operations") and updates nothing. Core treats `location_dest_id` and
`location_id` asymmetrically: a `location_dest_id` change re-runs
putaway on the lines (`move_to_check_dest_location` branch in
`stock_move.py::write()`); a `location_id` change does nothing to the
lines. `stock/models/stock_move.py::write()` likewise has no handling
that keeps lines consistent with a changed header source.

So any actor — a UI user editing the picking's Source Location on a
picking that already has operations, or an ORM bulk write from a
migration — can leave the header and its lines in different locations
with no error and only a dismissable warning.

## 2. Scope

**In scope:** prevent *new* divergence from any write that goes through
the Odoo ORM (UI edits and `env['stock.move'].write(...)` /
`env['stock.picking'].write(...)` share the same code path). Provide a
read-only report of current divergence so the ~175-row backlog can be
watched as it is fixed.

**Out of scope:**
- Bulk-fixing the ~175 legacy rows. Each needs per-case backup →
  quant / reservation / SVL-warehouse check → apply → verify, as
  established in prior sessions. No safe blind bulk operation exists.
- Raw SQL writes straight to the DB. No Python guard fires on those.
  Documented as a known limitation; not worth a DB trigger or cron for
  the frequency observed (one event in the module's lifetime).
- Any change to the FIFO valuation engine or the reports.

## 3. The invariant

**Containment, not equality.** For a `done` move, every
`move_line.location_id` MUST be equal to, or a descendant of,
`move.location_id`.

Equality is the wrong test: Odoo's reservation engine legitimately
places lines at child locations, and at multiple locations, when stock
is spread across sub-locations. Measured on MOG_LIVE over 90 days of
`done` lines:

| relationship of line loc to header loc | count |
|---|---|
| equal | 38,345 |
| not equal, but `child_of` header (legit sub-location split) | 3 |
| not equal, **outside** header subtree (defect shape) | 34 |

The 3 `child_of` rows are legitimate and must not be blocked. The
defect is exactly "line location is outside the header's subtree",
which in practice means a **different warehouse**.

### Predicate

```python
def _loc_contained(child_loc, parent_loc):
    # both are stock.location records
    return bool(child_loc) and bool(parent_loc) and \
        child_loc.parent_path.startswith(parent_loc.parent_path)
```

`parent_path` is Odoo's materialized path (e.g. `"1/5/27/"`); a
descendant's path is prefixed by its ancestor's path. A location is its
own descendant under this test (`"1/5/27/".startswith("1/5/27/")`), so
equality passes, which is what we want.

## 4. Components

### 4.1 `models/stock_move.py` — `StockMove(_inherit='stock.move')`

#### `write(vals)` guard

Act only when `'location_id' in vals` and, per record, the new value
differs from the current one. For each such move:

| move state | reserved move lines? | behaviour |
|---|---|---|
| `done` | — | `raise ValidationError` (bilingual). Never auto-fix — retagging a done line correctly needs the quant + SVL analysis done per-case. |
| `draft`, `waiting`, `confirmed` | no | call `super().write(vals)`, then for any line now outside the new subtree set `line.location_id = vals['location_id']` directly (nothing is reserved, no quant bookkeeping needed). |
| `assigned`, `partially_available` | yes | `move._do_unreserve()` → `super().write(vals)` → `move._action_assign()`. Odoo does all quant / `reserved_quantity` bookkeeping. If re-assignment cannot cover the demand the move falls back to `confirmed`; post a chatter note on the picking. **No hand-written quant SQL.** |

**Legacy tolerance.** Before blocking, check whether the move is
*already* divergent (a legacy broken row): "is any line outside the
OLD header subtree". If yes, allow the write — a move that is already
broken cannot be made cleaner or worse by this guard, and the ~175
pre-existing rows must stay editable. Only a write that turns a
*clean* move divergent is blocked.

**Bypass.** Honour `self.env.context.get('skip_location_consistency_check')`
for deliberate repair scripts, mirroring the existing
`bypass_done_move_line_guard` flag in
`stock_fifo_by_location/models/stock_move_line.py`.

Batching: `write` can be called on a recordset. Iterate; collect
moves needing unreserve/reassign and process them; call `super().write`
once on the full set where possible, or per sub-group when the flow
differs. Correctness over a single super call.

#### `_check_move_line_location_containment` constrains backstop

```python
@api.constrains('location_id')
def _check_move_line_location_containment(self):
    if self.env.context.get('skip_location_consistency_check'):
        return
    for move in self:
        if move.state != 'done':
            continue
        bad = move.move_line_ids.filtered(
            lambda l: not _loc_contained(l.location_id, move.location_id))
        if bad:
            raise ValidationError(_bilingual_msg(move, bad))
```

This is a thin backstop for ORM paths that set `location_id` without
going through the `write` branch above (e.g. `create` of a done move,
unusual). It only inspects `done` moves. Because it triggers on the
`location_id` field write specifically — not on unrelated field edits —
it does not fire when someone touches another field on a legacy broken
row.

### 4.2 `models/stock_picking.py` — `StockPicking(_inherit='stock.picking')`

#### `write(vals)` guard

When `'location_id' in vals`:

1. For each picking whose new source differs from the current one,
   run its `move_ids` through the same decision table as §4.1 (done →
   block the whole write; assigned → unreserve now so the subsequent
   core propagation + our reassign land cleanly).
2. Call `super().write(vals)` — core propagates the new `location_id`
   to `move_ids` headers.
3. Re-assign the moves that were unreserved in step 1.

This closes the primary case-A path: a user opening a confirmed
picking and changing its Source Location.

### 4.3 `models/stock_location_mismatch.py` — `BuzStockLocationMismatch`

`_name = 'buz.stock.location.mismatch'`, `_auto = False`,
`_description = 'Stock Move Line / Header Location Mismatch'`.

```python
def init(self):
    tools.drop_view_if_exists(self.env.cr, self._table)
    self.env.cr.execute(f"""
        CREATE VIEW {self._table} AS
        SELECT ml.id                AS id,
               ml.picking_id         AS picking_id,
               ml.move_id            AS move_id,
               ml.product_id         AS product_id,
               ml.location_id        AS ml_location_id,
               m.location_id         AS header_location_id,
               ml.location_dest_id   AS ml_location_dest_id,
               m.location_dest_id    AS header_location_dest_id,
               ml.quantity           AS quantity,
               ml.state              AS state,
               m.write_uid           AS move_write_uid,
               m.write_date          AS move_write_date,
               p.picking_type_id     AS picking_type_id,
               m.company_id          AS company_id
        FROM stock_move_line ml
        JOIN stock_move m       ON m.id = ml.move_id
        JOIN stock_picking p    ON p.id = ml.picking_id
        JOIN stock_location lm  ON lm.id = m.location_id
        LEFT JOIN stock_location ls
               ON ls.id = ml.location_id
              AND ls.parent_path LIKE lm.parent_path || '%%'
        WHERE ml.state IN ('done', 'assigned', 'partially_available')
          AND ml.location_id <> m.location_id
          AND ls.id IS NULL
    """)
```

Fields: all read-only `Many2one` / `Char` / `Float` / `Datetime`
mirrors of the columns above. No compute, no store.

### 4.4 Views — `views/stock_move_line_mismatch_views.xml`

- `ir.ui.view` tree (editable=false): picking, product, ml location,
  header location, quantity, state, move write date, move write uid.
- `ir.ui.view` search: filters by `picking_type_id`, `company_id`,
  group-by `picking_type_id` / `header_location_id` /
  `move_write_date:day`.
- `ir.actions.act_window` → tree only, no form, `create`/`edit`/
  `delete` all `false` via context.
- `menuitem` under **Inventory → Reporting**, label
  "Location Mismatches" / "ตำแหน่งไม่ตรง (Move vs Header)".

**No fix button.** The backlog is worked per-case elsewhere.

### 4.5 `security/ir.model.access.csv`

One line: `buz.stock.location.mismatch`, group
`stock.group_stock_user`, `perm_read=1`, all others `0`.

## 5. Error message (bilingual, follows existing module style)

```
ไม่สามารถเปลี่ยนตำแหน่งต้นทาง (Source Location) ของเอกสารที่ยืนยันแล้ว (Done) ได้
อ้างอิง: {reference}
Move line อยู่ที่: {ml_location}
Header จะเปลี่ยนเป็น: {new_location}

สาเหตุ: การเปลี่ยน header อย่างเดียวจะทำให้ move line กับ valuation (FIFO)
ไม่ตรงกับ stock จริง โดยไม่มีการแจ้งเตือน
กรุณาใช้ Inventory Adjustment / Return เพื่อย้าย stock ให้ถูกต้อง
```

## 6. Manifest

```python
{
    'name': 'BUZ Stock Location Consistency',
    'version': '17.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Keep stock move line source consistent with move header; '
               'report existing mismatches',
    'depends': ['stock', 'stock_fifo_by_location'],
    'data': [
        'security/ir.model.access.csv',
        'views/stock_move_line_mismatch_views.xml',
    ],
    'license': 'LGPL-3',
    'installable': True,
}
```

`depends` on `stock_fifo_by_location` guarantees this module's
`stock.move.line` / `stock.move` overrides load after that module's
existing `stock_move_line.py::write` override — deterministic MRO.

## 7. Testing

**Environment:** docker MOG_LIVE stack at `mog-prod:/srv/docker/odoo_mogen`
(:8070, own postgres:16 cluster). **Not** MOG_DEV — its picking type
105 is misconfigured `src=92 dest=92` and is unrepresentative of the
real internal-transfer flow.

`tests/test_location_consistency.py` (Odoo `TransactionCase`,
tagged `post_install`, `-at_install`):

1. **UI-shape source change on assigned picking** — create INT
   picking RM02→PD01, confirm, reserve; `picking.write({'location_id':
   <RM03>})`; assert every move line's `location_id` is now `child_of`
   RM03 and `stock_quant.reserved_quantity` moved with it.
2. **Source change on done move blocked** — validate a transfer, then
   `move.write({'location_id': <other wh>})`; assert `ValidationError`.
3. **ORM bulk write on done blocked** — same via
   `self.env['stock.move'].browse(ids).write({...})`.
4. **Legacy row tolerated** — construct a move already divergent
   (via `skip_location_consistency_check` context), then write an
   unrelated field on it; assert no error.
5. **child_of split not blocked** — reserve a move whose line lands in
   a sub-location of the header; validate; assert no error and the row
   does **not** appear in `buz.stock.location.mismatch`.
6. **Mismatch view** — seed one out-of-subtree done row; assert it is
   returned by `buz.stock.location.mismatch.search([])`.
7. **Bypass flag** — `move.with_context(skip_location_consistency_check=
   True).write({'location_id': ...})` on a done move succeeds.

Module has `tests/__init__.py` importing the test class (Odoo test
runner only — no pytest).

## 8. Deploy

1. `bash scripts/deploy.sh dev buz_stock_location_consistency`, install
   on MOG_DEV, smoke test the view.
2. Run the test suite on the docker MOG_LIVE stack (:8070).
3. On approval: `bash scripts/deploy.sh prod buz_stock_location_consistency`,
   install on MOG_LIVE, `chmod -R +r` after rsync, restart handled per
   `Prod deploy sudo restart` memory note.
4. Verify **Inventory → Reporting → Location Mismatches** shows the
   ~175-row backlog and nothing from the last 90 days of clean
   pickings beyond it.

## 9. Docs framing (README)

State plainly: this module closes the gap Odoo core leaves on
`stock.move.location_id` — unlike `location_dest_id`, core never
re-points move lines when the header source changes. Raw SQL writes
straight to the database bypass this guard (known limitation). Do
**not** claim it would have prevented the 2026-08-19 event; the
evidence points to a migration / SQL bulk write, and only ORM-path
writes are covered.

## 10. Open risks

- **Batched `write` across mixed states.** A single `write` call
  hitting draft + assigned + done moves at once. Handled by
  sub-grouping in §4.1; test 3 covers the done subset. Keep the
  per-group logic readable even at the cost of multiple `super()`
  calls.
- **`_do_unreserve` / `_action_assign` side effects** in a module that
  also runs `stock_fifo_by_location`. The reassign happens before
  `_action_done`, so no SVL is created/destroyed by it — SVL is created
  once at validation. Confirm in test 1 that no `stock_valuation_layer`
  row is produced by the reassign.
- **`parent_path` null.** Newly created locations before
  `_parent_store` compute. Guard `_loc_contained` against `None`
  (already does via the `bool()` checks); a null path means "cannot
  prove containment" → treat as contained (do not block) to stay
  conservative.
