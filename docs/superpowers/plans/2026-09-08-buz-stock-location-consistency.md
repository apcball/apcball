# buz_stock_location_consistency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship an Odoo 17 addon that blocks new `stock_move_line.location_id` / move-header divergence via ORM guards, with a read-only report of the existing mismatch backlog.

**Architecture:** `write()` overrides on `stock.move` and `stock.picking` intercept `location_id` changes: block on `done` moves, unreserve+reassign on reserved moves, re-point lines on unreserved moves. An `@api.constrains` backstop catches ORM paths that skip the `write` branch. A `_auto=False` SQL-view model (`buz.stock.location.mismatch`) plus a tree/search view surfaces the current backlog with no fix action.

**Tech Stack:** Odoo 17, Python 3, PostgreSQL 16. Odoo test runner only (no pytest). Deploy via `scripts/deploy.sh`.

**Spec:** `docs/superpowers/specs/2026-09-08-stock-location-consistency-design.md`

## Global Constraints

- Module name: `buz_stock_location_consistency`. Model namespace `buz.<name>`. XML IDs module-prefixed.
- Manifest `version`: `17.0.1.0.0`. `license`: `LGPL-3`. `depends`: `['stock', 'stock_fifo_by_location']` (exact — the `stock_fifo_by_location` dep forces load order after its existing `stock.move.line.write` override).
- Odoo 17 API only: `fields.Command`, not `(0,0,{})` tuples.
- Containment predicate is `child.parent_path.startswith(parent.parent_path)` — equality passes, `child_of` splits pass, only out-of-subtree fails. Never enforce equality.
- Guard blocks only writes that *introduce or worsen* divergence. Legacy already-divergent rows must remain editable on unrelated fields.
- Context bypass flag: `skip_location_consistency_check` (mirrors existing `bypass_done_move_line_guard` in `stock_fifo_by_location`).
- Error messages bilingual (Thai primary), matching the style in `stock_fifo_by_location/models/stock_move_line.py`.
- No hand-written `stock_quant` SQL anywhere in this module. Reservation moves go through `_do_unreserve()` / `_action_assign()`.
- Commit after every task. Do NOT push, do NOT deploy to prod without explicit user confirmation.
- Commit message trailer:
  ```
  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01EURL2V8aFmrCbGjLSSboBS
  ```

## Test Environment

- **Stack:** docker MOG_LIVE test stack on `mog-prod` — compose dir `/srv/docker/odoo_mogen`, container `odoo` (image `my-odoo:17`), addons mount `/srv/docker/odoo_mogen/custom-addons`, DB `MOG_LIVE`, own `postgres:16` cluster. NOT MOG_DEV (its picking type 105 is misconfigured `src=92 dest=92`).
- **Sync module to test stack:**
  ```bash
  rsync -az --delete ./buz_stock_location_consistency/ mog-prod:/srv/docker/odoo_mogen/custom-addons/buz_stock_location_consistency/
  ssh mog-prod "chmod -R +r /srv/docker/odoo_mogen/custom-addons/buz_stock_location_consistency"
  ```
- **Run this module's tests:**
  ```bash
  ssh mog-prod "docker exec odoo odoo -d MOG_LIVE -u buz_stock_location_consistency \
    --test-enable --test-tags /buz_stock_location_consistency --stop-after-init --no-http 2>&1 | tail -40"
  ```
- Tests are `TransactionCase` (rolled back), tagged `post_install, -at_install`. Side effects roll back, but `--test-enable` still runs against the real `MOG_LIVE` copy — never add a test that commits.

---

## File Structure

| File | Responsibility |
|---|---|
| `buz_stock_location_consistency/__manifest__.py` | Module metadata, deps, data list |
| `buz_stock_location_consistency/__init__.py` | `from . import models` |
| `buz_stock_location_consistency/models/__init__.py` | import the 3 model modules |
| `buz_stock_location_consistency/models/location_helpers.py` | `loc_contained(child, parent)` pure helper + shared bilingual message builder |
| `buz_stock_location_consistency/models/stock_move.py` | `stock.move` `write()` guard + `_check_move_line_location_containment` constrains |
| `buz_stock_location_consistency/models/stock_picking.py` | `stock.picking` `write()` guard |
| `buz_stock_location_consistency/models/stock_location_mismatch.py` | `buz.stock.location.mismatch` SQL-view model |
| `buz_stock_location_consistency/views/stock_move_line_mismatch_views.xml` | tree + search + action + menu |
| `buz_stock_location_consistency/security/ir.model.access.csv` | read-only ACL for the view model |
| `buz_stock_location_consistency/tests/__init__.py` | import test class |
| `buz_stock_location_consistency/tests/test_location_consistency.py` | all TransactionCase tests |
| `buz_stock_location_consistency/README.md` | scope + known limitation (raw SQL bypass) |

---

## Task 1: Module scaffold + containment helper

**Files:**
- Create: `buz_stock_location_consistency/__init__.py`
- Create: `buz_stock_location_consistency/__manifest__.py`
- Create: `buz_stock_location_consistency/models/__init__.py`
- Create: `buz_stock_location_consistency/models/location_helpers.py`
- Create: `buz_stock_location_consistency/tests/__init__.py`
- Create: `buz_stock_location_consistency/tests/test_location_consistency.py`

**Interfaces:**
- Produces: `loc_contained(child_loc, parent_loc) -> bool` in `models/location_helpers.py` — takes two `stock.location` recordsets (singleton or empty), returns `True` when `child_loc` is `parent_loc` or a descendant, or when containment cannot be proven (null `parent_path`). Conservative: unprovable ⇒ `True` (do not block).
- Produces: `build_mismatch_message(move, bad_lines, new_location) -> str` — bilingual `ValidationError` body.

- [ ] **Step 1: Create `models/location_helpers.py`**

```python
# -*- coding: utf-8 -*-
"""Pure helpers shared by the stock.move / stock.picking guards."""
from odoo import _


def loc_contained(child_loc, parent_loc):
    """Return True if child_loc is parent_loc or a descendant of it.

    Uses Odoo's materialized `parent_path` ("1/5/27/"): a descendant's
    path is prefixed by its ancestor's path, and a location's path is a
    prefix of itself, so equality also returns True.

    Conservative on missing data: if either record is empty or its
    parent_path is not yet computed, containment cannot be disproven,
    so return True (never block on incomplete data).
    """
    if not child_loc or not parent_loc:
        return True
    child_path = child_loc.parent_path
    parent_path = parent_loc.parent_path
    if not child_path or not parent_path:
        return True
    return child_path.startswith(parent_path)


def build_mismatch_message(move, bad_lines, new_location):
    ref = move.reference or move.display_name
    ml_locs = ", ".join(sorted(set(bad_lines.mapped("location_id.complete_name"))))
    return _(
        "ไม่สามารถเปลี่ยนตำแหน่งต้นทาง (Source Location) ของเอกสารที่ยืนยันแล้ว (Done) ได้\n"
        "อ้างอิง: %(ref)s\n"
        "Move line อยู่ที่: %(ml)s\n"
        "Header จะเปลี่ยนเป็น: %(new)s\n\n"
        "สาเหตุ: การเปลี่ยน header อย่างเดียวจะทำให้ move line กับ valuation (FIFO) "
        "ไม่ตรงกับ stock จริง โดยไม่มีการแจ้งเตือน\n"
        "กรุณาใช้ Inventory Adjustment / Return เพื่อย้าย stock ให้ถูกต้อง\n\n"
        "(To bypass in a deliberate repair script: "
        "with_context(skip_location_consistency_check=True))"
    ) % {"ref": ref, "ml": ml_locs, "new": new_location.complete_name or str(new_location.id)}
```

- [ ] **Step 2: Create `__init__.py`, `models/__init__.py`, `__manifest__.py`**

`buz_stock_location_consistency/__init__.py`:
```python
from . import models
```

`buz_stock_location_consistency/models/__init__.py`:
```python
from . import stock_location_mismatch
from . import stock_move
from . import stock_picking
```

`buz_stock_location_consistency/__manifest__.py`:
```python
{
    "name": "BUZ Stock Location Consistency",
    "version": "17.0.1.0.0",
    "category": "Inventory/Inventory",
    "summary": "Keep stock move line source consistent with the move header; "
               "report existing mismatches",
    "author": "Mogen Co.",
    "license": "LGPL-3",
    "depends": ["stock", "stock_fifo_by_location"],
    "data": [
        "security/ir.model.access.csv",
        "views/stock_move_line_mismatch_views.xml",
    ],
    "installable": True,
    "application": False,
}
```

- [ ] **Step 3: Create the test file with the helper's failing test**

`buz_stock_location_consistency/tests/__init__.py`:
```python
from . import test_location_consistency
```

`buz_stock_location_consistency/tests/test_location_consistency.py`:
```python
# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.tests import tagged
from odoo.exceptions import ValidationError

from odoo.addons.buz_stock_location_consistency.models.location_helpers import (
    loc_contained,
)


@tagged("post_install", "-at_install")
class TestLocationConsistency(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Location = cls.env["stock.location"]
        cls.stock = cls.env.ref("stock.stock_location_stock")
        cls.sub = cls.Location.create({
            "name": "CONSISTENCY_SUB", "location_id": cls.stock.id,
        })
        cls.other = cls.Location.create({
            "name": "CONSISTENCY_OTHER",
            "location_id": cls.env.ref("stock.stock_location_locations_virtual").id,
        })

    def test_loc_contained_true_cases(self):
        self.assertTrue(loc_contained(self.stock, self.stock))   # self
        self.assertTrue(loc_contained(self.sub, self.stock))     # descendant
        self.assertTrue(loc_contained(self.env["stock.location"], self.stock))  # empty child

    def test_loc_contained_false_case(self):
        self.assertFalse(loc_contained(self.other, self.stock))
```

- [ ] **Step 4: Sync + run — expect FAIL (module not installable yet: `stock_move.py` / `stock_picking.py` / view files referenced but absent)**

```bash
rsync -az --delete ./buz_stock_location_consistency/ mog-prod:/srv/docker/odoo_mogen/custom-addons/buz_stock_location_consistency/
ssh mog-prod "docker exec odoo odoo -d MOG_LIVE -i buz_stock_location_consistency --stop-after-init --no-http 2>&1 | tail -30"
```
Expected: install error — missing `models/stock_move.py` etc. (imported in `models/__init__.py`) and missing view/security files. This confirms the scaffold is wired; the next steps create those files.

- [ ] **Step 5: Create stub files so the module installs, then re-run helper tests**

Create `buz_stock_location_consistency/security/ir.model.access.csv`:
```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_buz_stock_location_mismatch,buz.stock.location.mismatch,model_buz_stock_location_mismatch,stock.group_stock_user,1,0,0,0
```

Create `buz_stock_location_consistency/models/stock_location_mismatch.py`:
```python
# -*- coding: utf-8 -*-
from odoo import fields, models, tools


class BuzStockLocationMismatch(models.Model):
    _name = "buz.stock.location.mismatch"
    _description = "Stock Move Line / Header Location Mismatch"
    _auto = False
    _order = "move_write_date desc"

    picking_id = fields.Many2one("stock.picking", readonly=True)
    move_id = fields.Many2one("stock.move", readonly=True)
    product_id = fields.Many2one("product.product", readonly=True)
    ml_location_id = fields.Many2one("stock.location", string="Move Line Source", readonly=True)
    header_location_id = fields.Many2one("stock.location", string="Header Source", readonly=True)
    ml_location_dest_id = fields.Many2one("stock.location", string="Move Line Dest", readonly=True)
    header_location_dest_id = fields.Many2one("stock.location", string="Header Dest", readonly=True)
    quantity = fields.Float(readonly=True)
    state = fields.Char(readonly=True)
    move_write_uid = fields.Many2one("res.users", string="Header Last Edited By", readonly=True)
    move_write_date = fields.Datetime(string="Header Last Edited", readonly=True)
    picking_type_id = fields.Many2one("stock.picking.type", readonly=True)
    company_id = fields.Many2one("res.company", readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE VIEW buz_stock_location_mismatch AS (
                SELECT ml.id                  AS id,
                       ml.picking_id          AS picking_id,
                       ml.move_id             AS move_id,
                       ml.product_id          AS product_id,
                       ml.location_id         AS ml_location_id,
                       m.location_id          AS header_location_id,
                       ml.location_dest_id    AS ml_location_dest_id,
                       m.location_dest_id     AS header_location_dest_id,
                       ml.quantity            AS quantity,
                       ml.state               AS state,
                       m.write_uid            AS move_write_uid,
                       m.write_date           AS move_write_date,
                       p.picking_type_id      AS picking_type_id,
                       m.company_id           AS company_id
                FROM stock_move_line ml
                JOIN stock_move m      ON m.id = ml.move_id
                JOIN stock_picking p   ON p.id = ml.picking_id
                JOIN stock_location lm ON lm.id = m.location_id
                LEFT JOIN stock_location ls
                       ON ls.id = ml.location_id
                      AND ls.parent_path LIKE lm.parent_path || '%%'
                WHERE ml.state IN ('done', 'assigned', 'partially_available')
                  AND ml.location_id <> m.location_id
                  AND ls.id IS NULL
            )
        """)
```

Create `buz_stock_location_consistency/models/stock_move.py`:
```python
# -*- coding: utf-8 -*-
from odoo import api, models


class StockMove(models.Model):
    _inherit = "stock.move"
    # guard added in Task 2
```

Create `buz_stock_location_consistency/models/stock_picking.py`:
```python
# -*- coding: utf-8 -*-
from odoo import models


class StockPicking(models.Model):
    _inherit = "stock.picking"
    # guard added in Task 3
```

Create `buz_stock_location_consistency/views/stock_move_line_mismatch_views.xml`:
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <!-- filled in Task 4 -->
</odoo>
```

- [ ] **Step 6: Sync + install + run helper tests — expect PASS**

```bash
rsync -az --delete ./buz_stock_location_consistency/ mog-prod:/srv/docker/odoo_mogen/custom-addons/buz_stock_location_consistency/
ssh mog-prod "docker exec odoo odoo -d MOG_LIVE -i buz_stock_location_consistency \
  --test-enable --test-tags /buz_stock_location_consistency --stop-after-init --no-http 2>&1 | tail -40"
```
Expected: module installs; `test_loc_contained_true_cases` and `test_loc_contained_false_case` PASS. (An empty `<odoo/>` XML file is valid.)

- [ ] **Step 7: Commit**

```bash
git add buz_stock_location_consistency
git commit -m "$(cat <<'EOF'
feat(buz_stock_location_consistency): module scaffold + containment helper

New addon skeleton: manifest, containment predicate loc_contained()
(parent_path prefix test, conservative on null), bilingual message
builder, empty stock.move/stock.picking inherits, and the
buz.stock.location.mismatch SQL-view model. Guards and views land in
following commits.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01EURL2V8aFmrCbGjLSSboBS
EOF
)"
```

---

## Task 2: `stock.move` write guard + constrains backstop

**Files:**
- Modify: `buz_stock_location_consistency/models/stock_move.py`
- Modify: `buz_stock_location_consistency/tests/test_location_consistency.py`

**Interfaces:**
- Consumes: `loc_contained`, `build_mismatch_message` from `models/location_helpers.py`.
- Produces: `stock.move` behaviour — `write({'location_id': X})` raises `ValidationError` on any `done` move whose lines would end up out-of-subtree and that is not already divergent; unreserves+reassigns `assigned`/`partially_available` moves; re-points lines on unreserved moves. `@api.constrains('location_id')` `_check_move_line_location_containment` on `done` moves. Both honour `skip_location_consistency_check` context.

- [ ] **Step 1: Write the failing tests**

Add to `TestLocationConsistency` (helper method to build a done internal move first):

```python
def _make_done_internal_move(self, src=None, dest=None, qty=5.0):
    """Create + validate a same-warehouse internal transfer, return the move."""
    src = src or self.stock
    dest = dest or self.sub
    product = self.env["product.product"].create({
        "name": "CONSISTENCY_PROD", "type": "product",
    })
    self.env["stock.quant"]._update_available_quantity(product, src, qty)
    picking = self.env["stock.picking"].create({
        "picking_type_id": self.env.ref("stock.picking_type_internal").id,
        "location_id": src.id,
        "location_dest_id": dest.id,
        "move_ids": [(0, 0, {
            "name": product.name, "product_id": product.id,
            "product_uom_qty": qty, "product_uom": product.uom_id.id,
            "location_id": src.id, "location_dest_id": dest.id,
        })],
    })
    picking.action_confirm()
    picking.action_assign()
    for ml in picking.move_ids.move_line_ids:
        ml.quantity = ml.quantity_product_uom or qty
    picking.button_validate()
    self.assertEqual(picking.state, "done")
    return picking.move_ids

def test_done_move_source_change_blocked(self):
    move = self._make_done_internal_move()
    with self.assertRaises(ValidationError):
        move.write({"location_id": self.other.id})

def test_done_move_source_change_orm_bulk_blocked(self):
    move = self._make_done_internal_move()
    with self.assertRaises(ValidationError):
        self.env["stock.move"].browse(move.id).write({"location_id": self.other.id})

def test_done_move_bypass_flag_allows(self):
    move = self._make_done_internal_move()
    move.with_context(skip_location_consistency_check=True).write(
        {"location_id": self.other.id})
    self.assertEqual(move.location_id, self.other)

def test_legacy_divergent_move_unrelated_write_allowed(self):
    move = self._make_done_internal_move()
    # force a legacy divergence past the guard
    move.with_context(skip_location_consistency_check=True).write(
        {"location_id": self.other.id})
    # an unrelated field write must not raise
    move.write({"date_deadline": move.date})

def test_unreserved_move_source_change_repoints_lines(self):
    move = self._make_done_internal_move(qty=5.0)  # reuse builder for product/quant
    # new draft move, same product, not reserved
    product = move.product_id
    self.env["stock.quant"]._update_available_quantity(product, self.stock, 3.0)
    p2 = self.env["stock.picking"].create({
        "picking_type_id": self.env.ref("stock.picking_type_internal").id,
        "location_id": self.stock.id, "location_dest_id": self.sub.id,
        "move_ids": [(0, 0, {
            "name": product.name, "product_id": product.id,
            "product_uom_qty": 3.0, "product_uom": product.uom_id.id,
            "location_id": self.stock.id, "location_dest_id": self.sub.id,
        })],
    })
    p2.action_confirm()  # confirmed, not assigned
    p2.move_ids.write({"location_id": self.sub.id})
    self.assertEqual(p2.move_ids.location_id, self.sub)
    self.assertFalse(p2.move_ids.move_line_ids.filtered(
        lambda l: not loc_contained(l.location_id, self.sub)))
```

- [ ] **Step 2: Sync + run — expect FAIL**

```bash
rsync -az --delete ./buz_stock_location_consistency/ mog-prod:/srv/docker/odoo_mogen/custom-addons/buz_stock_location_consistency/
ssh mog-prod "docker exec odoo odoo -d MOG_LIVE -u buz_stock_location_consistency \
  --test-enable --test-tags /buz_stock_location_consistency --stop-after-init --no-http 2>&1 | tail -50"
```
Expected: the 5 new tests FAIL (no guard yet — `write` succeeds where a raise is expected).

- [ ] **Step 3: Implement the guard**

Replace `buz_stock_location_consistency/models/stock_move.py` with:
```python
# -*- coding: utf-8 -*-
from odoo import api, models, _
from odoo.exceptions import ValidationError

from .location_helpers import loc_contained, build_mismatch_message


class StockMove(models.Model):
    _inherit = "stock.move"

    def _consistency_out_of_subtree_lines(self, parent_loc):
        """move lines of self whose source is outside parent_loc's subtree."""
        return self.move_line_ids.filtered(
            lambda l: not loc_contained(l.location_id, parent_loc))

    def write(self, vals):
        if "location_id" not in vals or self.env.context.get(
                "skip_location_consistency_check"):
            return super().write(vals)

        new_loc = self.env["stock.location"].browse(vals["location_id"])
        to_reassign = self.env["stock.move"]

        for move in self:
            if move.location_id.id == new_loc.id:
                continue

            already_bad = bool(move._consistency_out_of_subtree_lines(move.location_id))
            would_be_bad = move._consistency_out_of_subtree_lines(new_loc)

            if move.state == "done":
                # allow only if it does not create NEW out-of-subtree lines
                if would_be_bad and not already_bad:
                    raise ValidationError(
                        build_mismatch_message(move, would_be_bad, new_loc))
                continue

            if move.state in ("assigned", "partially_available") and move.move_line_ids:
                move._do_unreserve()
                to_reassign |= move

        res = super().write(vals)

        # re-point unreserved lines that are now out of subtree
        for move in self:
            if move.state in ("draft", "confirmed", "waiting") and move.move_line_ids:
                stale = move._consistency_out_of_subtree_lines(move.location_id)
                if stale:
                    stale.with_context(
                        skip_location_consistency_check=True
                    ).write({"location_id": move.location_id.id})

        if to_reassign:
            to_reassign._action_assign()
            for move in to_reassign:
                if move.state not in ("assigned", "done"):
                    move.picking_id.message_post(body=_(
                        "ตำแหน่งต้นทางถูกเปลี่ยน แต่ระบบจองสินค้าที่ตำแหน่งใหม่ไม่พอ "
                        "(move %(name)s กลับเป็นสถานะ %(state)s)",
                    ) % {"name": move.display_name, "state": move.state})
        return res

    @api.constrains("location_id")
    def _check_move_line_location_containment(self):
        if self.env.context.get("skip_location_consistency_check"):
            return
        for move in self:
            if move.state != "done":
                continue
            bad = move._consistency_out_of_subtree_lines(move.location_id)
            if bad:
                raise ValidationError(
                    build_mismatch_message(move, bad, move.location_id))
```

- [ ] **Step 4: Sync + run — expect PASS**

```bash
rsync -az --delete ./buz_stock_location_consistency/ mog-prod:/srv/docker/odoo_mogen/custom-addons/buz_stock_location_consistency/
ssh mog-prod "docker exec odoo odoo -d MOG_LIVE -u buz_stock_location_consistency \
  --test-enable --test-tags /buz_stock_location_consistency --stop-after-init --no-http 2>&1 | tail -50"
```
Expected: all Task 1 + Task 2 tests PASS. If `test_legacy_divergent_move_unrelated_write_allowed` fails on the constrains, confirm the constrains only triggers on `location_id` writes (it should not fire on a `date_deadline` write).

- [ ] **Step 5: Commit**

```bash
git add buz_stock_location_consistency
git commit -m "$(cat <<'EOF'
feat(buz_stock_location_consistency): stock.move location_id guard

write() intercepts location_id changes: hard-block on done moves that
would gain new out-of-subtree lines, unreserve+_action_assign on
reserved moves, re-point lines on unreserved moves. Legacy already-
divergent moves stay editable. @api.constrains backstop on done moves.
skip_location_consistency_check context bypasses both.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01EURL2V8aFmrCbGjLSSboBS
EOF
)"
```

---

## Task 3: `stock.picking` write guard

**Files:**
- Modify: `buz_stock_location_consistency/models/stock_picking.py`
- Modify: `buz_stock_location_consistency/tests/test_location_consistency.py`

**Interfaces:**
- Consumes: `stock.move` guard from Task 2 (the picking guard delegates the reserved-move handling to it by letting core propagate `location_id` to `move_ids`, which re-enters `StockMove.write`).
- Produces: `stock.picking.write({'location_id': X})` — a done picking whose moves would become out-of-subtree raises `ValidationError`; a reserved picking's lines follow the new source with reservations intact.

- [ ] **Step 1: Write the failing tests**

```python
def test_picking_source_change_on_done_blocked(self):
    move = self._make_done_internal_move()
    with self.assertRaises(ValidationError):
        move.picking_id.write({"location_id": self.other.id})

def test_picking_source_change_on_reserved_follows(self):
    product = self.env["product.product"].create({
        "name": "CONSISTENCY_RES", "type": "product"})
    self.env["stock.quant"]._update_available_quantity(product, self.sub, 4.0)
    picking = self.env["stock.picking"].create({
        "picking_type_id": self.env.ref("stock.picking_type_internal").id,
        "location_id": self.stock.id, "location_dest_id": self.sub.id,
        "move_ids": [(0, 0, {
            "name": product.name, "product_id": product.id,
            "product_uom_qty": 4.0, "product_uom": product.uom_id.id,
            "location_id": self.stock.id, "location_dest_id": self.sub.id,
        })],
    })
    picking.action_confirm()
    picking.action_assign()  # reserves at self.stock (0 available) -> not assigned
    picking.write({"location_id": self.sub.id})
    picking.action_assign()
    self.assertEqual(picking.move_ids.location_id, self.sub)
    self.assertFalse(picking.move_ids.move_line_ids.filtered(
        lambda l: not loc_contained(l.location_id, self.sub)))
```

- [ ] **Step 2: Sync + run — expect FAIL**

```bash
rsync -az --delete ./buz_stock_location_consistency/ mog-prod:/srv/docker/odoo_mogen/custom-addons/buz_stock_location_consistency/
ssh mog-prod "docker exec odoo odoo -d MOG_LIVE -u buz_stock_location_consistency \
  --test-enable --test-tags /buz_stock_location_consistency --stop-after-init --no-http 2>&1 | tail -50"
```
Expected: `test_picking_source_change_on_done_blocked` FAILS (no raise — core's `picking.write` propagates to `move_ids` but our `StockMove.write` only raises when `move.move_line_ids` are already reserved at validate; a done move's lines ARE present so it should already raise via Task 2... if it does, keep the test as a regression guard and this task only adds the reserved-follow path). Run first to see which of the two actually fails.

- [ ] **Step 3: Implement**

Replace `buz_stock_location_consistency/models/stock_picking.py` with:
```python
# -*- coding: utf-8 -*-
from odoo import models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def write(self, vals):
        if "location_id" not in vals or self.env.context.get(
                "skip_location_consistency_check"):
            return super().write(vals)

        new_loc_id = vals["location_id"]
        to_reassign = self.env["stock.move"]
        for picking in self:
            if picking.location_id.id == new_loc_id:
                continue
            moves = picking.move_ids.filtered(lambda m: not m.scrapped)
            reserved = moves.filtered(
                lambda m: m.state in ("assigned", "partially_available")
                and m.move_line_ids)
            if reserved:
                reserved._do_unreserve()
                to_reassign |= reserved

        # core propagates location_id to move_ids -> re-enters StockMove.write,
        # which raises for done moves that would become out-of-subtree.
        res = super().write(vals)

        if to_reassign:
            to_reassign._action_assign()
        return res
```

- [ ] **Step 4: Sync + run — expect PASS**

```bash
rsync -az --delete ./buz_stock_location_consistency/ mog-prod:/srv/docker/odoo_mogen/custom-addons/buz_stock_location_consistency/
ssh mog-prod "docker exec odoo odoo -d MOG_LIVE -u buz_stock_location_consistency \
  --test-enable --test-tags /buz_stock_location_consistency --stop-after-init --no-http 2>&1 | tail -50"
```
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add buz_stock_location_consistency
git commit -m "$(cat <<'EOF'
feat(buz_stock_location_consistency): stock.picking source-change guard

picking.write({location_id}) unreserves reserved moves before core
propagates the new source to the move headers, then reassigns. Done
pickings are blocked via the re-entrant stock.move guard.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01EURL2V8aFmrCbGjLSSboBS
EOF
)"
```

---

## Task 4: Mismatch report view + menu

**Files:**
- Modify: `buz_stock_location_consistency/views/stock_move_line_mismatch_views.xml`
- Modify: `buz_stock_location_consistency/tests/test_location_consistency.py`

**Interfaces:**
- Consumes: `buz.stock.location.mismatch` model from Task 1.
- Produces: menu **Inventory → Reporting → Location Mismatches**; tree + search views; `create`/`edit`/`delete` disabled.

- [ ] **Step 1: Write the failing test**

```python
def test_mismatch_view_lists_out_of_subtree_row(self):
    move = self._make_done_internal_move()
    move.with_context(skip_location_consistency_check=True).write(
        {"location_id": self.other.id})
    self.env.cr.execute("SELECT 1")  # flush
    rows = self.env["buz.stock.location.mismatch"].search(
        [("move_id", "=", move.id)])
    self.assertTrue(rows)
    self.assertEqual(rows[0].header_location_id, self.other)

def test_mismatch_view_ignores_child_of_split(self):
    move = self._make_done_internal_move(src=self.stock, dest=self.sub)
    # line source == header source (self.stock) -> not in view
    rows = self.env["buz.stock.location.mismatch"].search(
        [("move_id", "=", move.id)])
    self.assertFalse(rows)
```

- [ ] **Step 2: Sync + run — expect `test_mismatch_view_lists_out_of_subtree_row` behaviour**

```bash
rsync -az --delete ./buz_stock_location_consistency/ mog-prod:/srv/docker/odoo_mogen/custom-addons/buz_stock_location_consistency/
ssh mog-prod "docker exec odoo odoo -d MOG_LIVE -u buz_stock_location_consistency \
  --test-enable --test-tags /buz_stock_location_consistency --stop-after-init --no-http 2>&1 | tail -50"
```
Expected: model tests may already PASS (the SQL view exists from Task 1). The purpose of this task is the UI; if both tests pass, keep them as regression and proceed to the view XML.

- [ ] **Step 3: Fill in the view XML**

`buz_stock_location_consistency/views/stock_move_line_mismatch_views.xml`:
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="view_buz_stock_location_mismatch_tree" model="ir.ui.view">
        <field name="name">buz.stock.location.mismatch.tree</field>
        <field name="model">buz.stock.location.mismatch</field>
        <field name="arch" type="xml">
            <tree string="Location Mismatches" create="false" edit="false" delete="false">
                <field name="picking_id"/>
                <field name="picking_type_id"/>
                <field name="product_id"/>
                <field name="ml_location_id"/>
                <field name="header_location_id"/>
                <field name="quantity"/>
                <field name="state"/>
                <field name="move_write_date"/>
                <field name="move_write_uid"/>
                <field name="company_id" groups="base.group_multi_company"/>
            </tree>
        </field>
    </record>

    <record id="view_buz_stock_location_mismatch_search" model="ir.ui.view">
        <field name="name">buz.stock.location.mismatch.search</field>
        <field name="model">buz.stock.location.mismatch</field>
        <field name="arch" type="xml">
            <search>
                <field name="picking_id"/>
                <field name="product_id"/>
                <field name="header_location_id"/>
                <field name="ml_location_id"/>
                <filter name="done" string="Done" domain="[('state','=','done')]"/>
                <filter name="reserved" string="Reserved"
                        domain="[('state','in',['assigned','partially_available'])]"/>
                <group expand="0" string="Group By">
                    <filter name="g_ptype" string="Operation Type"
                            context="{'group_by':'picking_type_id'}"/>
                    <filter name="g_header" string="Header Source"
                            context="{'group_by':'header_location_id'}"/>
                    <filter name="g_wdate" string="Header Edited On"
                            context="{'group_by':'move_write_date:day'}"/>
                </group>
            </search>
        </field>
    </record>

    <record id="action_buz_stock_location_mismatch" model="ir.actions.act_window">
        <field name="name">Location Mismatches</field>
        <field name="res_model">buz.stock.location.mismatch</field>
        <field name="view_mode">tree</field>
        <field name="context">{'create': False, 'edit': False, 'delete': False}</field>
        <field name="help" type="html">
            <p class="o_view_nocontent_smiley_face">No move line / header location mismatches</p>
            <p>Rows here have a move line whose source location is outside the
               move header's location subtree. Each is fixed case-by-case.</p>
        </field>
    </record>

    <menuitem id="menu_buz_stock_location_mismatch"
              name="Location Mismatches"
              parent="stock.menu_warehouse_report"
              action="action_buz_stock_location_mismatch"
              sequence="95"/>
</odoo>
```

- [ ] **Step 4: Sync + run — expect PASS + module loads with menu**

```bash
rsync -az --delete ./buz_stock_location_consistency/ mog-prod:/srv/docker/odoo_mogen/custom-addons/buz_stock_location_consistency/
ssh mog-prod "docker exec odoo odoo -d MOG_LIVE -u buz_stock_location_consistency \
  --test-enable --test-tags /buz_stock_location_consistency --stop-after-init --no-http 2>&1 | tail -50"
```
Expected: all tests PASS; no view-parse errors. Verify `stock.menu_warehouse_report` is the correct parent xmlid (Odoo 17 stock: Inventory → Reporting). If it errors as not found, use `stock.menu_warehouse_report` alternative `stock.menu_valuation` is wrong — grep the installed `stock` module: `ssh mog-prod "docker exec odoo grep -rn 'menu_warehouse_report' /usr/lib/python3/dist-packages/odoo/addons/stock/views/"`.

- [ ] **Step 5: Commit**

```bash
git add buz_stock_location_consistency
git commit -m "$(cat <<'EOF'
feat(buz_stock_location_consistency): read-only mismatch report + menu

Tree/search views over buz.stock.location.mismatch under Inventory >
Reporting. No create/edit/delete, no fix action - the backlog is worked
case-by-case elsewhere.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01EURL2V8aFmrCbGjLSSboBS
EOF
)"
```

---

## Task 5: README + full-suite verification + DEV deploy

**Files:**
- Create: `buz_stock_location_consistency/README.md`

**Interfaces:** none (documentation + verification only).

- [ ] **Step 1: Write `buz_stock_location_consistency/README.md`**

```markdown
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
```

- [ ] **Step 2: Full suite run on the docker MOG_LIVE stack**

```bash
rsync -az --delete ./buz_stock_location_consistency/ mog-prod:/srv/docker/odoo_mogen/custom-addons/buz_stock_location_consistency/
ssh mog-prod "docker exec odoo odoo -d MOG_LIVE -u buz_stock_location_consistency \
  --test-enable --test-tags /buz_stock_location_consistency --stop-after-init --no-http 2>&1 | tail -60"
```
Expected: `0 failed, 0 error` for the module's tests. Record the pass count.

- [ ] **Step 3: Sanity-check the report against real data**

```bash
ssh mog-prod "docker exec odoo odoo shell -d MOG_LIVE --no-http" <<'PY'
M = env['buz.stock.location.mismatch'].search([])
print('mismatch rows:', len(M))
print('by picking type:', {k.name: v for k, v in
      __import__('collections').Counter(M.mapped('picking_type_id')).items()})
PY
```
Expected: roughly the ~175-row backlog (minus anything since fixed), dominated by type 273 / type 105. No rows dated in the last 90 days beyond the known event.

- [ ] **Step 4: Deploy to DEV**

```bash
bash scripts/deploy.sh dev buz_stock_location_consistency
```
Note (`Dev deploy no restart` memory): `deploy.sh dev` does not restart the container; the `-u` in the script handles the module reload. If the menu doesn't appear, `ssh dev "docker restart odoo"`.

- [ ] **Step 5: Commit + report**

```bash
git add buz_stock_location_consistency/README.md
git commit -m "$(cat <<'EOF'
docs(buz_stock_location_consistency): README (scope + SQL-bypass caveat)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01EURL2V8aFmrCbGjLSSboBS
EOF
)"
```

Then report to the user: test pass count, mismatch-row count on MOG_LIVE, DEV deploy status. **Do not deploy to PROD** — wait for explicit confirmation. **Do not push** — wait for explicit confirmation.

---

## Self-Review

**1. Spec coverage**

| Spec section | Task |
|---|---|
| §3 containment predicate | Task 1 (`loc_contained`) |
| §4.1 `stock.move.write` guard (done/draft/assigned table) | Task 2 |
| §4.1 legacy tolerance | Task 2 (`already_bad` check) + test `test_legacy_divergent_move_unrelated_write_allowed` |
| §4.1 constrains backstop | Task 2 |
| §4.1 bypass flag | Task 2 + test `test_done_move_bypass_flag_allows` |
| §4.2 `stock.picking.write` guard | Task 3 |
| §4.3 `buz.stock.location.mismatch` model | Task 1 |
| §4.4 views + menu | Task 4 |
| §4.5 security csv | Task 1 (created in Step 5) |
| §5 bilingual message | Task 1 (`build_mismatch_message`) |
| §6 manifest | Task 1 |
| §7 tests (7 scenarios) | Tasks 1–4 cover: source-change-done, ORM-bulk-done, legacy-tolerated, child_of-not-blocked, mismatch-view-returns-row, bypass-flag, reserved-follows |
| §9 README framing | Task 5 |
| §10 risk: no SVL from reassign | add assertion in Task 3 Step 1 `test_picking_source_change_on_reserved_follows` — see note below |
| §10 risk: null parent_path | Task 1 `loc_contained` + `test_loc_contained` empty-child case |

Gap found + fixed: §10 "confirm no `stock_valuation_layer` row is produced by the reassign" — add to Task 3 Step 1 test body:
```python
    svl_before = self.env["stock.valuation.layer"].search_count([])
    picking.write({"location_id": self.sub.id})
    picking.action_assign()
    self.assertEqual(self.env["stock.valuation.layer"].search_count([]), svl_before)
```

**2. Placeholder scan** — no TBD/TODO. All code blocks concrete. Menu parent xmlid flagged with a verification command in Task 4 Step 4 rather than left ambiguous.

**3. Type consistency** — `loc_contained(child, parent)` order consistent across Tasks 1–4. `_consistency_out_of_subtree_lines(parent_loc)` defined once in Task 2, used in Task 2 only. `build_mismatch_message(move, bad_lines, new_location)` signature consistent between helper and both call sites (guard + constrains). `skip_location_consistency_check` spelled identically everywhere. Model `_name` `buz.stock.location.mismatch` ↔ table `buz_stock_location_mismatch` ↔ access csv `model_buz_stock_location_mismatch` consistent.

**4. Ambiguity** — "reserved" defined as `state in ('assigned','partially_available') and move_line_ids`. "Legacy tolerance" defined operationally as `would_be_bad and not already_bad`.
