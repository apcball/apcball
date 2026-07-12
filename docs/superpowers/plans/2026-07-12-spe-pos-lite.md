# SPE × pos_lite + Dashboard Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recognize POS Lite (`pos.lite.order`) sales in `buz.sales.performance.result` with the same delivered-AND-invoiced rule, add a source filter to the dashboard, and modernize the dashboard styling.

**Architecture:** Extend the existing result summary model with a `source` dimension and POS line links; add a POS-specific SQL aggregation/upsert mirroring `_recompute_for_sol`; hook `pos.lite.order.write` on state changes. Dashboard controller gains a `source` filter param; OWL dashboard gets source chips, KPI icons/deltas/progress ring, and a refreshed SCSS.

**Tech Stack:** Odoo 17, OWL, Chart.js (bundled), PostgreSQL, pylint-odoo.

## Global Constraints

- Odoo 17 API only (`fields.Command`, no old tuple syntax).
- Spec: `docs/superpowers/specs/2026-07-12-spe-pos-lite-design.md`.
- Module: `buz_sales_performance_engine`; version bump 17.0.1.0.0 → 17.0.2.0.0 (Task 7).
- **Commits require user confirmation (CLAUDE.md hard rule).** Prepare commits per task but ask the user before running `git commit`.
- Tests run with the Odoo test runner only (no pytest). Against dev: `ssh dev "docker exec odoo odoo -d MOG_DEV -u buz_sales_performance_engine --test-enable --stop-after-init --no-http"` — irreversible on MOG_DEV; prefer `docker-compose.test.yml` isolated Postgres if practical.
- Dev-DB quirk: do NOT create `stock.warehouse` or `product.product` in tests — reuse existing records (orphaned-column issue on MOG_DEV).
- Deploy: `bash scripts/deploy.sh dev buz_sales_performance_engine` (Task 7 only, after tests pass).

---

### Task 1: Result model — source dimension + POS links

**Files:**
- Modify: `buz_sales_performance_engine/models/sale_performance_result.py`

**Interfaces:**
- Produces: fields `source` (`'sale'`/`'pos'`), `pos_order_id`, `pos_order_line_id` on `buz.sales.performance.result`; SQL constraint `uniq_pos_line_company`. Later tasks (recompute, controller, views, tests) rely on these exact names.

- [ ] **Step 1: Add fields**

In `sale_performance_result.py`, after the `sale_order_line_id` field definition (line ~40), add:

```python
    source = fields.Selection(
        [("sale", "Sales Order"), ("pos", "POS Lite")],
        string="Source", required=True, default="sale", index=True,
    )
    pos_order_id = fields.Many2one(
        "pos.lite.order", string="POS Order", index=True, ondelete="cascade",
    )
    pos_order_line_id = fields.Many2one(
        "pos.lite.order.line", string="POS Order Line", index=True, ondelete="cascade",
    )
```

- [ ] **Step 2: Add unique constraint for POS lines**

Replace the `_sql_constraints` block with:

```python
    _sql_constraints = [
        (
            "uniq_sol_company",
            "UNIQUE(sale_order_line_id, company_id)",
            "A performance result already exists for this sale order line.",
        ),
        (
            "uniq_pos_line_company",
            "UNIQUE(pos_order_line_id, company_id)",
            "A performance result already exists for this POS order line.",
        ),
    ]
```

(Postgres UNIQUE ignores NULLs, so SO rows and POS rows never collide.)

- [ ] **Step 3: Make `_rec_name` safe for POS rows**

`_rec_name = "sale_order_line_id"` breaks display for POS rows. Replace with a computed display name. Change `_rec_name = "sale_order_line_id"` to `_rec_name = "display_label"` and add:

```python
    display_label = fields.Char(compute="_compute_display_label")

    @api.depends("sale_order_line_id", "pos_order_line_id")
    def _compute_display_label(self):
        for rec in self:
            line = rec.sale_order_line_id or rec.pos_order_line_id
            rec.display_label = line.display_name if line else f"SPE #{rec.id}"
```

- [ ] **Step 4: Syntax check**

Run: `python3 -m py_compile buz_sales_performance_engine/models/sale_performance_result.py`
Expected: no output (success).

- [ ] **Step 5: Stage (commit deferred to user confirmation)**

```bash
git add buz_sales_performance_engine/models/sale_performance_result.py
```

---

### Task 2: POS recompute engine + write hook + cron/wizard extension

**Files:**
- Modify: `buz_sales_performance_engine/models/sale_performance_result.py`
- Create: `buz_sales_performance_engine/models/pos_lite_order.py`
- Modify: `buz_sales_performance_engine/models/__init__.py`
- Modify: `buz_sales_performance_engine/wizard/spe_recompute_wizard.py`
- Modify: `buz_sales_performance_engine/__manifest__.py` (depends only; version bump in Task 7)

**Interfaces:**
- Consumes: Task 1 fields (`source`, `pos_order_id`, `pos_order_line_id`).
- Produces: `buz.sales.performance.result._recompute_for_pos_lines(pos_line_ids)` and `_recompute_for_pos_orders(pos_order_ids)` — both `@api.model`, take list/tuple of ints, return the result recordset model. Tests and hooks call these.

- [ ] **Step 1: Add `pos_lite` dependency**

In `__manifest__.py` `depends` list, add `"pos_lite"`:

```python
    "depends": [
        "sale_management",
        "sale_stock",
        "account",
        "crm",
        "pos_lite",
    ],
```

- [ ] **Step 2: Implement `_recompute_for_pos_lines`**

In `sale_performance_result.py`, after `_recompute_for_orders`, add:

```python
    @api.model
    def _recompute_for_pos_lines(self, pos_line_ids):
        """Re-aggregate performance rows for the given POS Lite order lines.

        A row exists only while the order state is 'done' (pos_lite marks
        'done' when the invoice is posted AND the picking is validated).
        Return orders (is_return) contribute refund_amount; normal orders
        contribute invoice_amount.
        """
        if not pos_line_ids:
            return self.env["buz.sales.performance.result"]
        pos_line_ids = tuple(int(i) for i in pos_line_ids if i)
        if not pos_line_ids:
            return self.env["buz.sales.performance.result"]

        env = self.env
        env.cr.execute(
            """
            SELECT
                pol.id                          AS pol_id,
                pol.order_id,
                pol.product_id,
                COALESCE(pol.qty, 0.0)          AS qty,
                COALESCE(pol.price_subtotal, 0.0) AS price_subtotal,
                po.company_id,
                po.partner_id,
                po.is_return,
                po.date_order,
                emp.user_id                     AS salesperson_id,
                ru.sale_team_id                 AS team_id,
                pt.categ_id,
                am.invoice_date                 AS date_invoiced,
                sp.date_done                    AS date_delivered
            FROM pos_lite_order_line pol
            JOIN pos_lite_order po ON po.id = pol.order_id
            LEFT JOIN hr_employee emp ON emp.id = po.employee_id
            LEFT JOIN res_users ru ON ru.id = emp.user_id
            LEFT JOIN product_product pp ON pp.id = pol.product_id
            LEFT JOIN product_template pt ON pt.id = pp.product_tmpl_id
            LEFT JOIN account_move am ON am.id = po.invoice_id
            LEFT JOIN stock_picking sp ON sp.id = po.picking_id
            WHERE pol.id IN %s
              AND po.state = 'done'
            """,
            (pos_line_ids,),
        )
        rows = env.cr.dictfetchall()

        # Drop rows whose line no longer qualifies (order not done anymore).
        keep_ids = [r["pol_id"] for r in rows]
        env.cr.execute(
            """
            DELETE FROM buz_sales_performance_result
            WHERE pos_order_line_id IN %s
              AND pos_order_line_id NOT IN %s
            """,
            (pos_line_ids, tuple(keep_ids) or (0,)),
        )

        existing = {
            r["pos_order_line_id"]: r["id"]
            for r in self.sudo().search_read(
                [("pos_order_line_id", "in", keep_ids)],
                ["id", "pos_order_line_id"],
            )
        }

        vals_list = []
        for row in rows:
            inv_dt = row["date_invoiced"]
            bucket_dt = inv_dt and fields.Datetime.to_datetime(inv_dt)
            if bucket_dt:
                period, year, month, quarter = (
                    "monthly", bucket_dt.year, bucket_dt.month,
                    (bucket_dt.month - 1) // 3 + 1,
                )
            else:
                period, year, month, quarter = False, 0, 0, 0
            is_return = bool(row["is_return"])
            subtotal = row["price_subtotal"] or 0.0
            vals = {
                "source": "pos",
                "company_id": row["company_id"],
                "salesperson_id": row["salesperson_id"],
                "team_id": row["team_id"],
                "partner_id": row["partner_id"],
                "product_id": row["product_id"],
                "categ_id": row["categ_id"],
                "pos_order_id": row["order_id"],
                "pos_order_line_id": row["pol_id"],
                "invoice_amount": 0.0 if is_return else subtotal,
                "refund_amount": subtotal if is_return else 0.0,
                "delivered_qty": row["qty"],
                "invoiced_qty": row["qty"],
                "ordered_qty": row["qty"],
                "date_order": row["date_order"],
                "date_delivered": row["date_delivered"],
                "date_invoiced": inv_dt,
                "period": period,
                "year": year,
                "month": month,
                "quarter": quarter,
            }
            pol_id = row["pol_id"]
            if pol_id in existing:
                self.browse(existing[pol_id]).sudo().write(vals)
            else:
                vals_list.append(vals)

        if vals_list:
            self.sudo().create(vals_list)
        return self

    @api.model
    def _recompute_for_pos_orders(self, pos_order_ids):
        """Recompute performance for every line of the given POS orders."""
        if not pos_order_ids:
            return self.env["buz.sales.performance.result"]
        pol_ids = self.env["pos.lite.order.line"].sudo().search(
            [("order_id", "in", list(pos_order_ids))]
        ).ids
        return self._recompute_for_pos_lines(pol_ids)
```

- [ ] **Step 3: Extend `_cron_rebuild_all` to cover POS lines**

In `_cron_rebuild_all`, after the existing SOL while-loop (before `return True`), add:

```python
        pos_domain = [("order_id.state", "in", ["done", "cancelled"])]
        PosLine = self.env["pos.lite.order.line"].sudo()
        pos_total = PosLine.search_count(pos_domain)
        offset = 0
        while offset < pos_total:
            pol_ids = PosLine.search(pos_domain, offset=offset, limit=batch_size).ids
            self._recompute_for_pos_lines(pol_ids)
            offset += batch_size
```

- [ ] **Step 4: Create the write hook**

Create `buz_sales_performance_engine/models/pos_lite_order.py`:

```python
from odoo import models


class PosLiteOrder(models.Model):
    _inherit = "pos.lite.order"

    def write(self, vals):
        res = super().write(vals)
        if "state" in vals:
            line_ids = self.sudo().mapped("line_ids").ids
            if line_ids:
                self.env["buz.sales.performance.result"]._recompute_for_pos_lines(line_ids)
        return res
```

(pos_lite sets `state = 'paid'` then `state = 'done'` via attribute writes in `_process_one_order`; each triggers this hook. Recompute is idempotent, so the double call is harmless.)

- [ ] **Step 5: Register the model**

In `buz_sales_performance_engine/models/__init__.py`, add:

```python
from . import pos_lite_order
```

- [ ] **Step 6: Extend recompute wizard 'range' mode**

In `spe_recompute_wizard.py` `action_recompute`, at the end of the `elif self.mode == "range":` branch (after the existing `Result._recompute_for_sol(sol_ids)` call), add:

```python
            self.env.cr.execute(
                """
                SELECT pol.id
                FROM pos_lite_order_line pol
                JOIN pos_lite_order po ON po.id = pol.order_id
                LEFT JOIN account_move am ON am.id = po.invoice_id
                WHERE po.state IN ('done', 'cancelled')
                  AND am.invoice_date BETWEEN %s AND %s
                """,
                (self.date_from, self.date_to),
            )
            pol_ids = [r[0] for r in self.env.cr.fetchall()]
            if pol_ids:
                Result._recompute_for_pos_lines(pol_ids)
```

('all' mode already covers POS via the Task 2 Step 3 cron extension.)

- [ ] **Step 7: Syntax check**

Run:
```bash
python3 -m py_compile \
  buz_sales_performance_engine/models/sale_performance_result.py \
  buz_sales_performance_engine/models/pos_lite_order.py \
  buz_sales_performance_engine/wizard/spe_recompute_wizard.py
```
Expected: no output.

- [ ] **Step 8: Stage**

```bash
git add buz_sales_performance_engine/models/ \
        buz_sales_performance_engine/wizard/spe_recompute_wizard.py \
        buz_sales_performance_engine/__manifest__.py
```

---

### Task 3: Tests — POS recognition scenarios

**Files:**
- Create: `buz_sales_performance_engine/tests/test_pos_lite_recognition.py`
- Modify: `buz_sales_performance_engine/tests/__init__.py`

**Interfaces:**
- Consumes: `_recompute_for_pos_lines`, `source`/`pos_order_line_id` fields; pos_lite models `pos.lite.order`, `pos.lite.order.line`.

- [ ] **Step 1: Write the test file**

Create `buz_sales_performance_engine/tests/test_pos_lite_recognition.py`:

```python
from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPosLiteRecognition(TransactionCase):
    """POS Lite orders are recognized in SPE only when state == 'done'."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Result = cls.env["buz.sales.performance.result"]
        cls.company = cls.env.company
        # Reuse existing records (MOG_DEV orphaned-column quirk: do not
        # create product.product / stock.warehouse in tests).
        cls.product = cls.env["product.product"].search(
            [("sale_ok", "=", True), ("type", "!=", "service")], limit=1,
        )
        cls.partner = cls.env["res.partner"].search(
            [("customer_rank", ">", 0)], limit=1,
        ) or cls.env["res.partner"].search([], limit=1)
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.company.id)], limit=1,
        )

    def _make_order(self, is_return=False, state="draft"):
        order = self.env["pos.lite.order"].create({
            "company_id": self.company.id,
            "partner_id": self.partner.id,
            "warehouse_id": self.warehouse.id,
            "is_return": is_return,
            "line_ids": [fields.Command.create({
                "product_id": self.product.id,
                "qty": 2.0,
                "price_unit": 100.0,
            })],
        })
        if state != "draft":
            order.write({"state": state})
        return order

    def _results_for(self, order):
        return self.Result.search(
            [("pos_order_line_id", "in", order.line_ids.ids)]
        )

    def test_01_draft_and_paid_not_recognized(self):
        order = self._make_order()
        self.assertFalse(self._results_for(order))
        order.write({"state": "paid"})
        self.assertFalse(self._results_for(order))

    def test_02_done_order_recognized(self):
        order = self._make_order(state="done")
        res = self._results_for(order)
        self.assertEqual(len(res), 1)
        self.assertEqual(res.source, "pos")
        self.assertEqual(res.pos_order_id, order)
        self.assertAlmostEqual(res.invoice_amount, order.line_ids.price_subtotal)
        self.assertAlmostEqual(res.refund_amount, 0.0)
        self.assertAlmostEqual(res.net_sales, order.line_ids.price_subtotal)
        self.assertAlmostEqual(res.delivered_qty, 2.0)
        self.assertAlmostEqual(res.ordered_qty, 2.0)

    def test_03_return_order_recognized_as_refund(self):
        order = self._make_order(is_return=True, state="done")
        res = self._results_for(order)
        self.assertEqual(len(res), 1)
        self.assertAlmostEqual(res.invoice_amount, 0.0)
        self.assertAlmostEqual(res.refund_amount, order.line_ids.price_subtotal)
        self.assertAlmostEqual(res.net_sales, -order.line_ids.price_subtotal)

    def test_04_cancel_removes_rows(self):
        order = self._make_order(state="done")
        self.assertTrue(self._results_for(order))
        order.write({"state": "cancelled"})
        self.assertFalse(self._results_for(order))

    def test_05_sale_flow_untouched(self):
        # Constraint coexistence: creating an SO-based row still works and
        # defaults to source='sale'.
        so = self.env["sale.order"].search([("state", "=", "sale")], limit=1)
        if not so:
            self.skipTest("No confirmed sale order available on this DB")
        row = self.Result.search([("sale_order_id", "=", so.id)], limit=1)
        if row:
            self.assertEqual(row.source, "sale")
```

Note: tests drive `state` via `write()` directly (not `action_process_order`) so no real invoice/picking is created — recognition logic only needs `po.state = 'done'`; `date_invoiced`/`date_delivered` stay NULL, which the model allows.

- [ ] **Step 2: Register tests**

In `buz_sales_performance_engine/tests/__init__.py`, add:

```python
from . import test_pos_lite_recognition
```

- [ ] **Step 3: Run the test suite on DEV** (needs module deployed first — coordinate with Task 7 if running remotely; for local isolated run use `docker-compose.test.yml`)

Run:
```bash
bash scripts/deploy.sh dev buz_sales_performance_engine
ssh dev "docker exec odoo odoo -d MOG_DEV -u buz_sales_performance_engine --test-enable --stop-after-init --no-http" 2>&1 | grep -E "FAIL|ERROR|test_pos_lite|odoo.tests"
```
Expected: `0 failed, 0 error(s)` for `test_pos_lite_recognition`.

- [ ] **Step 4: Stage**

```bash
git add buz_sales_performance_engine/tests/
```

---

### Task 4: Controller — source filter + POS-aware drill-downs

**Files:**
- Modify: `buz_sales_performance_engine/controllers/spe_dashboard_controller.py`

**Interfaces:**
- Consumes: `source`, `pos_order_id` fields.
- Produces: `filters.source` param (`""`/`"sale"`/`"pos"`) accepted by all endpoints; `action_drill` kind `"orders"` returns POS orders when `filters.source == "pos"`.

- [ ] **Step 1: Add source to the base domain**

In `_base_result_domain`, after the `categ_id` block, add:

```python
        if filters.get("source") in ("sale", "pos"):
            domain.append(("source", "=", filters["source"]))
        return domain
```

(replacing the existing `return domain`).

- [ ] **Step 2: Make drill-downs POS-aware**

Replace the beginning of `action_drill` (the `rows = ...` / `sol_ids` / `so_ids` lines) with:

```python
        rows = Result.search_read(
            domain, ["sale_order_line_id", "sale_order_id", "pos_order_id"], limit=None,
        )
        sol_ids = [r["sale_order_line_id"][0] for r in rows if r["sale_order_line_id"]]
        so_ids = list({r["sale_order_id"][0] for r in rows if r["sale_order_id"]})
        pos_order_ids = list({r["pos_order_id"][0] for r in rows if r["pos_order_id"]})
        pos_orders = request.env["pos.lite.order"].sudo().browse(pos_order_ids)
        pos_invoice_ids = pos_orders.mapped("invoice_id").ids
        pos_picking_ids = pos_orders.mapped("picking_id").ids
```

Then update the three document drills to include POS documents:

```python
        if kind == "invoices":
            return {
                "type": "ir.actions.act_window",
                "name": "Posted Invoices",
                "res_model": "account.move",
                "view_mode": "tree,form",
                "domain": [
                    ("move_type", "=", "out_invoice"),
                    ("state", "=", "posted"),
                    "|",
                    ("line_ids.sale_line_ids", "in", sol_ids),
                    ("id", "in", pos_invoice_ids),
                ],
                "context": {"default_move_type": "out_invoice"},
            }
        if kind == "credit_notes":
            return {
                "type": "ir.actions.act_window",
                "name": "Credit Notes",
                "res_model": "account.move",
                "view_mode": "tree,form",
                "domain": [
                    ("move_type", "=", "out_refund"),
                    ("state", "=", "posted"),
                    "|",
                    ("line_ids.sale_line_ids", "in", sol_ids),
                    ("id", "in", pos_invoice_ids),
                ],
                "context": {"default_move_type": "out_refund"},
            }
        if kind == "deliveries":
            return {
                "type": "ir.actions.act_window",
                "name": "Deliveries",
                "res_model": "stock.picking",
                "view_mode": "tree,form",
                "domain": [
                    ("state", "=", "done"),
                    "|",
                    ("move_ids.sale_line_id", "in", sol_ids),
                    ("id", "in", pos_picking_ids),
                ],
            }
```

And the `orders` drill:

```python
        if kind == "orders":
            if filters.get("source") == "pos":
                return {
                    "type": "ir.actions.act_window",
                    "name": "POS Orders",
                    "res_model": "pos.lite.order",
                    "view_mode": "tree,form",
                    "domain": [("id", "in", pos_order_ids)],
                }
            return {
                "type": "ir.actions.act_window",
                "name": "Sale Orders",
                "res_model": "sale.order",
                "view_mode": "tree,form",
                "domain": [("id", "in", so_ids)],
            }
```

- [ ] **Step 3: Syntax check**

Run: `python3 -m py_compile buz_sales_performance_engine/controllers/spe_dashboard_controller.py`
Expected: no output.

- [ ] **Step 4: Stage**

```bash
git add buz_sales_performance_engine/controllers/spe_dashboard_controller.py
```

---

### Task 5: Backend views — expose source / POS fields

**Files:**
- Modify: `buz_sales_performance_engine/views/sale_performance_result_views.xml`

**Interfaces:**
- Consumes: Task 1 fields.

- [ ] **Step 1: Tree view**

In `view_spe_result_tree`, after `<field name="date_invoiced"/>`, add:

```xml
                <field name="source" widget="badge"
                       decoration-info="source == 'sale'"
                       decoration-success="source == 'pos'"/>
                <field name="pos_order_id" optional="hide"/>
```

- [ ] **Step 2: Form view**

In `view_spe_result_form`, inside the `Source` group after `<field name="sale_order_line_id"/>`, add:

```xml
                            <field name="source"/>
                            <field name="pos_order_id" invisible="source != 'pos'"/>
                            <field name="pos_order_line_id" invisible="source != 'pos'"/>
```

Also make the header buttons source-aware (SO drill buttons are meaningless for POS rows). Replace the `<header>` content with:

```xml
                    <button name="action_open_invoices" string="Invoices" type="object" class="btn-primary" invisible="source == 'pos'"/>
                    <button name="action_open_credit_notes" string="Credit Notes" type="object" invisible="source == 'pos'"/>
                    <button name="action_open_deliveries" string="Deliveries" type="object" invisible="source == 'pos'"/>
                    <button name="action_open_sale_order" string="Sale Order" type="object" invisible="source == 'pos'"/>
                    <button name="action_open_pos_order" string="POS Order" type="object" class="btn-primary" invisible="source != 'pos'"/>
```

- [ ] **Step 3: Add the POS drill action on the model**

In `sale_performance_result.py`, after `action_open_sale_order`, add:

```python
    def action_open_pos_order(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "POS Order",
            "res_model": "pos.lite.order",
            "res_id": self.pos_order_id.id,
            "view_mode": "form",
        }
```

- [ ] **Step 4: Search view**

In `view_spe_result_search`, after the `Has Refund` filter, add:

```xml
                <separator/>
                <filter string="Sales Orders" name="filter_source_sale"
                        domain="[('source','=','sale')]"/>
                <filter string="POS Lite" name="filter_source_pos"
                        domain="[('source','=','pos')]"/>
```

and after the `By Category` group-by filter:

```xml
                <filter string="By Source" name="groupby_source"
                        context="{'group_by': 'source'}"/>
```

- [ ] **Step 5: XML well-formedness check**

Run: `python3 -c "import lxml.etree as e; e.parse('buz_sales_performance_engine/views/sale_performance_result_views.xml')"`
Expected: no output.

- [ ] **Step 6: Stage**

```bash
git add buz_sales_performance_engine/views/sale_performance_result_views.xml \
        buz_sales_performance_engine/models/sale_performance_result.py
```

---

### Task 6: Dashboard UI — source chips + modern polish

**Files:**
- Modify: `buz_sales_performance_engine/static/src/xml/spe_dashboard.xml`
- Modify: `buz_sales_performance_engine/static/src/js/spe_dashboard.js`
- Modify: `buz_sales_performance_engine/static/src/scss/spe_dashboard.scss`

**Interfaces:**
- Consumes: `filters.source` accepted by all `/spe/dashboard/*` endpoints (Task 4).

- [ ] **Step 1: JS — source filter state + previous-period deltas**

In `spe_dashboard.js`:

1. Add `source: ""` to `state.filters` (after `company_id: ""`).
2. Add `kpiPrev: {}` to the state object (after `kpi: {}`).
3. Add a chip handler method after `onFilter`:

```javascript
    async setSource(src) {
        this.state.filters.source = src;
        await this.loadAll();
    }
```

4. In `loadAll`, after `this.state.kpi = kpi;`, load previous-period KPIs for trend deltas:

```javascript
            this.state.kpiPrev = await this._loadPrevKpi();
```

and add the helper method after `loadAll`:

```javascript
    async _loadPrevKpi() {
        const f = this.state.filters;
        if (!f.date_from || !f.date_to) { return {}; }
        const from = new Date(f.date_from);
        const to = new Date(f.date_to);
        const spanMs = to.getTime() - from.getTime() + 24 * 3600 * 1000;
        const prevTo = new Date(from.getTime() - 24 * 3600 * 1000);
        const prevFrom = new Date(from.getTime() - spanMs);
        try {
            return await this.rpc("/spe/dashboard/kpi", {
                filters: {...f, date_from: this._fmt(prevFrom), date_to: this._fmt(prevTo)},
            });
        } catch (e) { return {}; }
    }

    delta(field) {
        const cur = (this.state.kpi || {})[field] || 0;
        const prev = (this.state.kpiPrev || {})[field] || 0;
        if (!prev) { return null; }
        return ((cur - prev) / Math.abs(prev)) * 100.0;
    }

    fmtDelta(field) {
        const d = this.delta(field);
        if (d === null) { return ""; }
        const arrow = d >= 0 ? "▲" : "▼";
        return `${arrow} ${Math.abs(d).toFixed(1)}%`;
    }

    deltaClass(field) {
        const d = this.delta(field);
        if (d === null) { return "spe-delta"; }
        return d >= 0 ? "spe-delta spe-up" : "spe-delta spe-down";
    }
```

5. Chart palette: replace the `_pie` backgroundColor array with the shared palette and define it once in `setup()` after `this.charts = {};`:

```javascript
        this.palette = ["#017e84", "#22a2a9", "#66c7cc", "#f2a541", "#e57373",
                        "#7986cb", "#4db6ac", "#9575cd"];
```

and in `_pie` use `backgroundColor: this.palette`.

6. Chart defaults: in `_chart`, replace the `options` object with:

```javascript
        this.charts[ref] = new Chart(el.getContext("2d"), {
            type, data,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {legend: {labels: {boxWidth: 12, usePointStyle: true}}},
                scales: type === "doughnut" ? {} : {
                    y: {grid: {color: "rgba(0,0,0,0.05)"}},
                    x: {grid: {display: false}},
                },
            },
        });
```

- [ ] **Step 2: XML — source chips, KPI icons, progress ring**

In `spe_dashboard.xml`:

1. At the top of the filter bar (first child of `<div class="spe-filters">`), add the source chips:

```xml
                    <div class="spe-field">
                        <label>Source</label>
                        <div class="spe-chips">
                            <button t-att-class="state.filters.source === '' ? 'spe-chip active' : 'spe-chip'"
                                    t-on-click="() => this.setSource('')">All</button>
                            <button t-att-class="state.filters.source === 'sale' ? 'spe-chip active' : 'spe-chip'"
                                    t-on-click="() => this.setSource('sale')">Sales</button>
                            <button t-att-class="state.filters.source === 'pos' ? 'spe-chip active' : 'spe-chip'"
                                    t-on-click="() => this.setSource('pos')">POS</button>
                        </div>
                    </div>
```

2. Replace the entire `<div class="spe-kpi-row">…</div>` block with icon + delta cards:

```xml
                <div class="spe-kpi-row">
                    <div class="spe-kpi-card spe-accent-slate spe-clickable" t-on-click="() =&gt; drill('orders')">
                        <div class="spe-kpi-icon"><i class="fa fa-bullseye"/></div>
                        <div class="spe-kpi-body">
                            <div class="spe-kpi-label">Target</div>
                            <div class="spe-kpi-value" t-esc="fmtMoney(state.kpi.target)"/>
                        </div>
                    </div>
                    <div class="spe-kpi-card spe-accent-teal spe-clickable" t-on-click="() =&gt; drill('results')">
                        <div class="spe-kpi-icon"><i class="fa fa-line-chart"/></div>
                        <div class="spe-kpi-body">
                            <div class="spe-kpi-label">Actual</div>
                            <div class="spe-kpi-value" t-esc="fmtMoney(state.kpi.actual)"/>
                            <div t-att-class="deltaClass('actual')" t-esc="fmtDelta('actual')"/>
                        </div>
                    </div>
                    <div class="spe-kpi-card spe-accent-teal">
                        <div class="spe-kpi-ring"
                             t-attf-style="--pct: {{ Math.min(state.kpi.achievement || 0, 100) }}">
                            <span t-esc="fmtPct(state.kpi.achievement)"/>
                        </div>
                        <div class="spe-kpi-body">
                            <div class="spe-kpi-label">Achievement</div>
                        </div>
                    </div>
                    <div class="spe-kpi-card spe-accent-indigo">
                        <div class="spe-kpi-icon"><i class="fa fa-flag-checkered"/></div>
                        <div class="spe-kpi-body">
                            <div class="spe-kpi-label">Forecast</div>
                            <div class="spe-kpi-value" t-esc="fmtMoney(state.kpi.forecast)"/>
                        </div>
                    </div>
                    <div class="spe-kpi-card spe-accent-green spe-clickable" t-on-click="() =&gt; drill('invoices')">
                        <div class="spe-kpi-icon"><i class="fa fa-file-text-o"/></div>
                        <div class="spe-kpi-body">
                            <div class="spe-kpi-label">Invoice</div>
                            <div class="spe-kpi-value" t-esc="fmtMoney(state.kpi.invoice_amount)"/>
                            <div t-att-class="deltaClass('invoice_amount')" t-esc="fmtDelta('invoice_amount')"/>
                        </div>
                    </div>
                    <div class="spe-kpi-card spe-accent-red spe-clickable" t-on-click="() =&gt; drill('credit_notes')">
                        <div class="spe-kpi-icon"><i class="fa fa-undo"/></div>
                        <div class="spe-kpi-body">
                            <div class="spe-kpi-label">Refund</div>
                            <div class="spe-kpi-value" t-esc="fmtMoney(state.kpi.refund_amount)"/>
                        </div>
                    </div>
                    <div class="spe-kpi-card spe-accent-amber spe-clickable" t-on-click="() =&gt; drill('deliveries')">
                        <div class="spe-kpi-icon"><i class="fa fa-truck"/></div>
                        <div class="spe-kpi-body">
                            <div class="spe-kpi-label">Delivery %</div>
                            <div class="spe-kpi-value" t-esc="fmtPct(state.kpi.delivery_pct)"/>
                        </div>
                    </div>
                    <div class="spe-kpi-card spe-accent-slate">
                        <div class="spe-kpi-icon"><i class="fa fa-hourglass-half"/></div>
                        <div class="spe-kpi-body">
                            <div class="spe-kpi-label">Remaining</div>
                            <div class="spe-kpi-value" t-esc="fmtMoney(state.kpi.remaining)"/>
                        </div>
                    </div>
                    <div class="spe-kpi-card spe-accent-indigo">
                        <div class="spe-kpi-icon"><i class="fa fa-calendar-o"/></div>
                        <div class="spe-kpi-body">
                            <div class="spe-kpi-label">Avg Daily</div>
                            <div class="spe-kpi-value" t-esc="fmtMoney(state.kpi.avg_daily)"/>
                        </div>
                    </div>
                </div>
```

3. Leaderboard rank cells: replace `<td t-esc="row_index + 1"/>` (both tables) with:

```xml
                                    <td><span t-att-class="'spe-rank spe-rank-' + Math.min(row_index + 1, 4)" t-esc="row_index + 1"/></td>
```

- [ ] **Step 3: SCSS — refreshed styling**

Replace the full content of `spe_dashboard.scss` with:

```scss
.spe-dashboard {
    height: 100%;
    overflow-y: auto;
    padding: 20px;
    background: #f2f5f6;
    font-variant-numeric: tabular-nums;

    .spe-loading {
        padding: 48px;
        text-align: center;
        color: #6c757d;
        font-size: 18px;
    }

    .spe-filter-bar {
        background: #fff;
        border-radius: 12px;
        padding: 14px 18px;
        margin-bottom: 18px;
        box-shadow: 0 1px 4px rgba(16, 40, 44, 0.08);
        .spe-filters {
            display: flex;
            flex-wrap: wrap;
            gap: 14px;
            align-items: flex-end;
        }
        .spe-field {
            display: flex;
            flex-direction: column;
            label { font-size: 11px; color: #8a959c; margin-bottom: 3px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; }
            input, select {
                padding: 6px 10px; border: 1px solid #dde3e6; border-radius: 8px;
                min-width: 130px; background: #fbfcfc; transition: border-color .15s;
                &:focus { border-color: #017e84; outline: none; }
            }
            &.spe-apply { margin-left: auto; }
        }
        .spe-chips {
            display: inline-flex;
            background: #eef2f3;
            border-radius: 999px;
            padding: 3px;
            gap: 2px;
            .spe-chip {
                border: none; background: transparent; color: #5b6970;
                border-radius: 999px; padding: 5px 16px; font-size: 13px;
                font-weight: 600; cursor: pointer; transition: all .15s;
                &:hover { color: #017e84; }
                &.active { background: #017e84; color: #fff; box-shadow: 0 1px 3px rgba(1,126,132,.35); }
            }
        }
        .btn-primary {
            background: #017e84; border-color: #017e84; border-radius: 8px;
            &:hover { background: #026a6f; border-color: #026a6f; }
        }
    }

    .spe-kpi-row {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
        gap: 14px;
        margin-bottom: 18px;
        .spe-kpi-card {
            display: flex;
            align-items: center;
            gap: 12px;
            background: #fff;
            border-radius: 12px;
            padding: 16px;
            box-shadow: 0 1px 4px rgba(16, 40, 44, 0.08);
            border: 1px solid transparent;
            &.spe-clickable { cursor: pointer; transition: transform .12s, box-shadow .12s; }
            &.spe-clickable:hover { transform: translateY(-2px); box-shadow: 0 6px 16px rgba(16,40,44,.12); }

            .spe-kpi-icon {
                width: 42px; height: 42px; flex: 0 0 42px;
                display: flex; align-items: center; justify-content: center;
                border-radius: 10px; font-size: 17px;
            }
            .spe-kpi-body { min-width: 0; }
            .spe-kpi-label { font-size: 11px; color: #8a959c; font-weight: 700; letter-spacing: .05em; text-transform: uppercase; }
            .spe-kpi-value { font-size: 21px; font-weight: 700; color: #22333a; margin-top: 2px; white-space: nowrap; }
            .spe-delta { font-size: 11px; font-weight: 700; margin-top: 2px; }
            .spe-up { color: #2e7d32; }
            .spe-down { color: #c62828; }

            .spe-kpi-ring {
                --pct: 0;
                width: 56px; height: 56px; flex: 0 0 56px;
                border-radius: 50%;
                background:
                    radial-gradient(closest-side, #fff 74%, transparent 75% 100%),
                    conic-gradient(#017e84 calc(var(--pct) * 1%), #e4ebec 0);
                display: flex; align-items: center; justify-content: center;
                span { font-size: 11px; font-weight: 700; color: #017e84; }
            }

            &.spe-accent-teal   .spe-kpi-icon { background: rgba(1,126,132,.12);   color: #017e84; }
            &.spe-accent-green  .spe-kpi-icon { background: rgba(46,125,50,.12);   color: #2e7d32; }
            &.spe-accent-red    .spe-kpi-icon { background: rgba(198,40,40,.10);   color: #c62828; }
            &.spe-accent-amber  .spe-kpi-icon { background: rgba(242,165,65,.15);  color: #b26a00; }
            &.spe-accent-indigo .spe-kpi-icon { background: rgba(121,134,203,.15); color: #4a5bb5; }
            &.spe-accent-slate  .spe-kpi-icon { background: rgba(84,110,122,.12);  color: #546e7a; }
        }
    }

    .spe-grid-2 {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 18px;
        margin-bottom: 18px;
        @media (max-width: 992px) { grid-template-columns: 1fr; }
    }

    .spe-chart-block, .spe-leaderboard {
        background: #fff;
        border-radius: 12px;
        padding: 14px 18px;
        box-shadow: 0 1px 4px rgba(16, 40, 44, 0.08);
        margin-bottom: 18px;
        .spe-chart-title {
            font-size: 13px;
            font-weight: 700;
            letter-spacing: .03em;
            text-transform: uppercase;
            color: #37474f;
            margin-bottom: 10px;
            padding-bottom: 8px;
            border-bottom: 2px solid #eef2f3;
        }
    }

    .spe-chart-block .spe-chart-box {
        position: relative;
        height: 280px;
        canvas { max-height: 280px; }
    }

    .spe-leaderboard {
        .spe-table {
            width: 100%;
            th, td { padding: 8px 10px; text-align: left; border-bottom: 1px solid #f0f4f5; }
            th { font-size: 11px; text-transform: uppercase; letter-spacing: .04em; color: #8a959c; }
            td.spe-num, th.spe-num { text-align: right; }
            tbody tr:nth-child(even) { background: #fafcfc; }
            tbody tr:hover { background: #eef7f7; }
        }
        .spe-rank {
            display: inline-flex; align-items: center; justify-content: center;
            width: 24px; height: 24px; border-radius: 50%;
            font-size: 12px; font-weight: 700;
            background: #eef2f3; color: #5b6970;
            &.spe-rank-1 { background: #ffe9b3; color: #9a6a00; }
            &.spe-rank-2 { background: #e7ebee; color: #5f6b74; }
            &.spe-rank-3 { background: #f6dcc8; color: #8d4f18; }
        }
    }
}
```

- [ ] **Step 4: XML well-formedness check**

Run: `python3 -c "import lxml.etree as e; e.parse('buz_sales_performance_engine/static/src/xml/spe_dashboard.xml')"`
Expected: no output.

- [ ] **Step 5: Stage**

```bash
git add buz_sales_performance_engine/static/
```

---

### Task 7: Version bump, lint, deploy DEV, verify

**Files:**
- Modify: `buz_sales_performance_engine/__manifest__.py`

- [ ] **Step 1: Version bump (needs user confirm per CLAUDE.md)**

Ask user, then set `"version": "17.0.2.0.0"` and extend the summary/description to mention POS Lite.

- [ ] **Step 2: Lint**

Run: `pylint --load-plugins=pylint_odoo buz_sales_performance_engine/ 2>&1 | tail -20`
Expected: no new errors (allow_failure in CI, but fix anything obvious).

- [ ] **Step 3: Deploy to DEV**

Run: `bash scripts/deploy.sh dev buz_sales_performance_engine`
Then restart (controller + asset changes): `ssh dev "docker restart odoo"`
Then upgrade module: `ssh dev "docker exec odoo odoo -d MOG_DEV -u buz_sales_performance_engine --stop-after-init --no-http"` (or via UI).

- [ ] **Step 4: Run tests on DEV** (same command as Task 3 Step 3)

Expected: 0 failures.

- [ ] **Step 5: Manual smoke check**

Open dashboard on DEV: source chips All/Sales/POS switch data; process one POS order to done; confirm it appears in Actual with source=pos; verify drill-downs.

- [ ] **Step 6: Ask user to confirm commit**

Proposed commit:

```bash
git add buz_sales_performance_engine/ docs/superpowers/
git commit -m "feat(spe): recognize pos_lite sales + modernize dashboard

- buz.sales.performance.result: source dimension, POS order/line links
- _recompute_for_pos_lines: SQL aggregation for done POS orders,
  returns counted as refunds; write-hook on pos.lite.order state
- cron rebuild + recompute wizard cover POS lines
- dashboard: source filter chips, KPI icons + trend deltas,
  achievement progress ring, refreshed palette and tables

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

PROD deploy only after user tests DEV.

---

## Self-Review Notes

- Spec §1–§7 all mapped: model (T1), recognition+plumbing (T2), tests (T3), controller (T4), backend views (T5, incl. `action_open_pos_order` from spec drill-downs), UI polish (T6), security unchanged (no new model → no ACL change needed; verified result model ACLs already exist).
- Type consistency: `_recompute_for_pos_lines(pos_line_ids)` name used consistently in hook, cron, wizard, tests.
- No placeholders remain.
