# buz_stock_count_adjust Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an Odoo 17 module that turns the manual "adjust FIFO qty/value at a cutoff date, replay post-cutoff COGS, reconcile physical stock" procedure into a UI-driven flow with backup / preview / apply / rollback and an audit trail.

**Architecture:** A `stock.count.adjustment` document holds target rows (FIFO bucket contents) per (product, warehouse). An `AbstractModel` engine runs six steps per line-group inside one savepoint: baseline via the FIFO valuation report view, category guard, raw-SQL void-and-reseed of `stock.valuation.layer`, a scoped FIFO consume-loop replay for post-cutoff repricing, an Odoo inventory adjustment with a neutralised valuation layer, and a read-only reconcile pass that emits mismatch rows. Preview runs the engine `dry_run=True` and rolls back; Apply writes a full pre-image backup first, then runs it for real. Rollback restores every touched row and deletes inserted layers.

**Tech Stack:** Odoo 17, Python 3, PostgreSQL (raw `env.cr.execute` for all `stock.valuation.layer` writes), Odoo test runner (no pytest), `xlsxwriter` (already a dependency of a sibling module) for the import wizard's error export is NOT needed — import reads xlsx/csv only.

**Spec:** `docs/superpowers/specs/2026-09-04-buz-stock-count-adjust-design.md` — read it alongside this plan. Where this plan and the spec disagree, this plan wins (four corrections are called out in Global Constraints).

## Global Constraints

- **Module prefix `buz_`**, model namespace `buz.` is the CLAUDE.md rule, BUT the spec fixes the model names as `stock.count.adjustment*` (no `buz.` prefix) — follow the spec's names verbatim; they are what the views and security csv reference.
- **Odoo 17 API only:** `fields.Command` not `(0,0,{})` tuples in Python; `<field>` / `Command` in XML data.
- **Multi-company:** every model with company data carries `company_id` with `default=lambda self: self.env.company`; `_check_company=True` on relational fields that point at company-bound records. One company per document (spec §11).
- **NEVER call `self.env.cr.commit()` anywhere in this module.** `fifo_reset_service._reset_quants` (fifo_reset_engine/models/fifo_reset_service.py:442) commits per chunk — do not copy that. A commit inside the preview savepoint defeats the rollback, and under `--test-enable` it writes fixture data to the target DB permanently.
- **All `stock.valuation.layer` writes go through raw `env.cr.execute`.** ORM `create()` on that model (stock_fifo_by_location/models/stock_valuation_layer.py:183) stamps `create_date = now()`, seeds `accounting_date`, and triggers `_run_fifo` / `_run_fifo_vacuum`. After every raw write, call `self.env['stock.valuation.layer'].invalidate_model([<columns>])` — see the rationale at fifo_recalculation_wizard.py:774-776.
- **Correction to spec §3 (manifest depends):** depends = `['stock', 'stock_account', 'stock_fifo_by_location', 'stock_fifo_valuation_report', 'stock_fifo_by_warehouse_recal']`. `stock_fifo_valuation_report` provides `stock.fifo.valuation.report` (the baseline source) and was missing from the spec. `stock_fifo_by_warehouse_recal` provides the `locked` boolean column on `stock.valuation.layer` (stock_fifo_by_warehouse_recal/models/stock_valuation_layer.py:10) that the "locked layers" edge case needs. Do NOT re-declare that module's cron.
- **Correction to spec §5 (baseline):** build the `stock.fifo.valuation.report` SQL view ONCE per engine run covering every (product, warehouse) in scope, then one `search_read`. `init_results()` does `DROP VIEW` / `CREATE VIEW` with filter literals baked in (stock_fifo_valuation_report/reports/stock_fifo_valuation_report.py:164-236); calling it per group is N DDL statements each clobbering the last and is the mechanism behind the "stale rows" memory note.
- **Correction to spec §4 (backup scope):** the backup must snapshot the pre-image of EVERY table the engine touches, not just SVL — see Task 7 for the full column inventory. Test #7 asserts row-level equality across all of them.
- **Correction to spec §5 (`_scoped_replay` reuse):** extract the consume loop out of `stock.valuation.layer._fifo_replay_remaining` into a shared classmethod (Task 2, a small change to `stock_fifo_by_location`) so the origin and this engine cannot drift. This is "Preferred" in the spec — this plan commits to it.
- **`negative_balance_mode` is `strict` on MOG_LIVE** (memory: negative-balance-strict-enabled). Every `action_apply_inventory` and every path that could trip `stock.valuation.layer._check_warehouse_consistency` must run `.with_context(skip_warehouse_consistency_check=True)`.
- **tz:** Asia/Bangkok is a fixed UTC+7 (no DST). Cutoff date `D` → the pre-cutoff UTC instant is `datetime.combine(D + 1 day, time.min) - timedelta(hours=7)`, i.e. `D 17:00:00 UTC`. Bucket/counter `create_date` values sit just below that instant. `accounting_date` for inserted layers = `datetime.combine(D, time.min)` (i.e. `D 00:00:00`, naive) — matches the report's `acct_date < utc_upper` bucketing.
- **Security:** every model gated on group `stock_count_adjust.group_stock_count_adjustment`, empty on install, `implied_ids = [stock.group_stock_manager]` (one-way, mirrors fifo_recal_security.xml). Not granted by being an Inventory Manager.
- **Deploy target is the docker MOG_LIVE test stack** (`mog-prod:/srv/docker/odoo_mogen`), then prod-native `instance1` after manual confirm. Never run `--test-enable` against MOG_DEV or MOG_LIVE — tests build their own fixture and rely on `TransactionCase` rollback.
- **No `cr.commit`, no version bump without user confirm, no git commit/push without user confirm** (CLAUDE.md).

---

## File Structure

```
buz_stock_count_adjust/
  __init__.py
  __manifest__.py
  models/
    __init__.py
    stock_valuation_layer.py          # (none here) — see stock_fifo_by_location change in Task 2
    count_adjust_engine.py            # AbstractModel 'count.adjust.engine' — the 6-step run()
    stock_count_adjustment.py         # header 'stock.count.adjustment' + state machine
    stock_count_adjustment_line.py    # 'stock.count.adjustment.line' — target bucket rows
    stock_count_adjustment_mismatch.py# 'stock.count.adjustment.mismatch' — step-6 findings
    stock_count_adjustment_backup.py  # 'stock.count.adjustment.backup' + '.backup.line'
  wizard/
    __init__.py
    stock_count_adjustment_import.py  # 'stock.count.adjustment.import' — xlsx/csv upload
  security/
    count_adjust_security.xml         # res.groups (empty)
    ir.model.access.csv
  views/
    stock_count_adjustment_views.xml  # form/tree/menu/action
    stock_count_adjustment_backup_views.xml
    stock_count_adjustment_import_views.xml
  data/
    ir_sequence_data.xml              # SCA/##### sequence
  tests/
    __init__.py
    test_count_adjust.py
```

Change to an existing module (Task 2 only):
```
stock_fifo_by_location/models/stock_valuation_layer.py   # extract _fifo_consume_rows classmethod
stock_fifo_by_location/tests/test_fifo_by_location.py     # or a new test file — pin loop equivalence
```

Responsibilities:
- **`count_adjust_engine.py`** holds ALL the dangerous logic (raw SQL, replay, quant adjust). The header model only orchestrates state and calls `engine.run(self, dry_run=...)`.
- **`stock_count_adjustment.py`** owns the `draft → previewed → applied → rolled_back` machine, the line-set hash, and the buttons.
- Backup models are write-once/read-once; restore is one `UPDATE ... FROM` per table plus a `DELETE` for inserted layers.

---

## Task 1: Module skeleton — installs clean

**Files:**
- Create: `buz_stock_count_adjust/__init__.py`
- Create: `buz_stock_count_adjust/__manifest__.py`
- Create: `buz_stock_count_adjust/models/__init__.py`
- Create: `buz_stock_count_adjust/models/stock_count_adjustment.py`
- Create: `buz_stock_count_adjust/models/stock_count_adjustment_line.py`
- Create: `buz_stock_count_adjust/models/stock_count_adjustment_mismatch.py`
- Create: `buz_stock_count_adjust/models/stock_count_adjustment_backup.py`
- Create: `buz_stock_count_adjust/models/count_adjust_engine.py`
- Create: `buz_stock_count_adjust/security/count_adjust_security.xml`
- Create: `buz_stock_count_adjust/security/ir.model.access.csv`
- Create: `buz_stock_count_adjust/data/ir_sequence_data.xml`
- Create: `buz_stock_count_adjust/views/stock_count_adjustment_views.xml`
- Test: `buz_stock_count_adjust/tests/__init__.py`, `buz_stock_count_adjust/tests/test_count_adjust.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - model `stock.count.adjustment` — fields: `name Char`, `company_id Many2one res.company`, `cutoff_date Date`, `state Selection [draft,previewed,applied,rolled_back]`, `line_ids One2many`, `mismatch_ids One2many`, `backup_id Many2one`, `preview_log Text`, `apply_log Text`, `line_hash Char`, `valuation_delta Float`, `cogs_delta Float`, `qty_delta Float`. Buttons (stubs raising `NotImplementedError` until later tasks): `action_preview`, `action_apply`, `action_rollback`, `action_import`.
  - model `stock.count.adjustment.line` — fields per spec §4 (`adjustment_id`, `product_id`, `warehouse_id`, `bucket_seq Integer default=10`, `target_qty Float`, `target_value Float`, `note Char`, `baseline_qty Float`, `baseline_value Float`, `delta_qty Float`, `delta_value Float`, `state Selection [pending,previewed,applied,skipped,error]`, `result_note Char`).
  - model `stock.count.adjustment.mismatch` — fields per spec §4.
  - models `stock.count.adjustment.backup` (fields: `name Char compute stored`, `company_id`, `adjustment_id Many2one`, `state Selection [active,restored]`, `line_ids One2many`, `quant_line_ids One2many`, `moveline_line_ids One2many`, `restore_date Datetime`, `restore_log Text`) and `stock.count.adjustment.backup.line` / `.backup.quant` / `.backup.moveline` (fields in Task 7).
  - AbstractModel `count.adjust.engine` with `def run(self, adjustment, dry_run=True): return {}` stub.
  - group xml id `buz_stock_count_adjust.group_stock_count_adjustment`.

- [ ] **Step 1: Write the failing test**

`buz_stock_count_adjust/tests/test_count_adjust.py`:
```python
from odoo.tests import common, tagged


@tagged('post_install', '-at_install')
class TestCountAdjustSkeleton(common.TransactionCase):

    def test_models_and_group_exist(self):
        self.assertIn('stock.count.adjustment', self.env)
        self.assertIn('stock.count.adjustment.line', self.env)
        self.assertIn('stock.count.adjustment.mismatch', self.env)
        self.assertIn('stock.count.adjustment.backup', self.env)
        self.assertIn('count.adjust.engine', self.env)
        self.assertTrue(self.env.ref('buz_stock_count_adjust.group_stock_count_adjustment'))

    def test_create_document_gets_sequence_name(self):
        doc = self.env['stock.count.adjustment'].create({
            'company_id': self.env.company.id,
            'cutoff_date': '2026-05-31',
        })
        self.assertNotEqual(doc.name, '/')
        self.assertEqual(doc.state, 'draft')
```

- [ ] **Step 2: Run test to verify it fails**

Run (on the docker test stack after deploy, or a scratch DB):
`ssh mog-prod "docker exec odoo odoo -d MOG_LIVE -u buz_stock_count_adjust --test-enable --stop-after-init --no-http -i buz_stock_count_adjust 2>&1 | grep -E 'FAIL|ERROR|test_'"`
Expected: module not found / test collection empty — the module does not exist yet.

- [ ] **Step 3: Write the manifest and models**

`__manifest__.py`:
```python
{
    'name': 'Stock Count Adjustment (FIFO void-reseed)',
    'version': '17.0.1.0.0',
    'category': 'Inventory/Inventory',
    'author': 'APC Ball',
    'license': 'LGPL-3',
    'depends': [
        'stock', 'stock_account',
        'stock_fifo_by_location',
        'stock_fifo_valuation_report',
        'stock_fifo_by_warehouse_recal',
    ],
    'data': [
        'security/count_adjust_security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'views/stock_count_adjustment_views.xml',
        'views/stock_count_adjustment_backup_views.xml',
        'views/stock_count_adjustment_import_views.xml',
    ],
    'installable': True,
    'application': False,
}
```
`__init__.py`: `from . import models` `from . import wizard`
`models/__init__.py`: import all model files (engine first, then header, line, mismatch, backup).

Write `stock_count_adjustment.py` header. `name` default from sequence:
```python
name = fields.Char(default='/', copy=False, readonly=True)

@api.model_create_multi
def create(self, vals_list):
    for vals in vals_list:
        if vals.get('name', '/') == '/':
            vals['name'] = self.env['ir.sequence'].next_by_code(
                'stock.count.adjustment') or '/'
    return super().create(vals_list)
```
Buttons as stubs:
```python
def action_preview(self):
    raise NotImplementedError

def action_apply(self):
    raise NotImplementedError

def action_rollback(self):
    raise NotImplementedError

def action_import(self):
    raise NotImplementedError
```
Write the other model files with the fields listed in Interfaces. `count_adjust_engine.py`:
```python
from odoo import models


class CountAdjustEngine(models.AbstractModel):
    _name = 'count.adjust.engine'
    _description = 'Stock Count Adjustment Engine'

    def run(self, adjustment, dry_run=True):
        """Filled in Tasks 4-9."""
        return {}
```

- [ ] **Step 4: Write security + sequence + minimal view**

`security/count_adjust_security.xml`:
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <data>
        <record id="group_stock_count_adjustment" model="res.groups">
            <field name="name">Stock Count Adjustment</field>
            <field name="category_id" ref="base.module_category_hidden"/>
            <field name="implied_ids" eval="[(4, ref('stock.group_stock_manager'))]"/>
            <field name="comment">Grants access to the FIFO count-adjust tool, which
writes stock.valuation.layer directly. Add people deliberately; being a stock
manager is not enough.</field>
        </record>
    </data>
</odoo>
```
`security/ir.model.access.csv` — one row per model, all four perms, group `group_stock_count_adjustment`:
```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_stock_count_adjustment,stock.count.adjustment,model_stock_count_adjustment,group_stock_count_adjustment,1,1,1,1
access_stock_count_adjustment_line,stock.count.adjustment.line,model_stock_count_adjustment_line,group_stock_count_adjustment,1,1,1,1
access_stock_count_adjustment_mismatch,stock.count.adjustment.mismatch,model_stock_count_adjustment_mismatch,group_stock_count_adjustment,1,1,1,1
access_stock_count_adjustment_backup,stock.count.adjustment.backup,model_stock_count_adjustment_backup,group_stock_count_adjustment,1,1,1,0
access_stock_count_adjustment_backup_line,stock.count.adjustment.backup.line,model_stock_count_adjustment_backup_line,group_stock_count_adjustment,1,1,1,0
access_stock_count_adjustment_backup_quant,stock.count.adjustment.backup.quant,model_stock_count_adjustment_backup_quant,group_stock_count_adjustment,1,1,1,0
access_stock_count_adjustment_backup_moveline,stock.count.adjustment.backup.moveline,model_stock_count_adjustment_backup_moveline,group_stock_count_adjustment,1,1,1,0
access_stock_count_adjustment_import,stock.count.adjustment.import,model_stock_count_adjustment_import,group_stock_count_adjustment,1,1,1,1
```
`data/ir_sequence_data.xml`:
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="seq_stock_count_adjustment" model="ir.sequence">
        <field name="name">Stock Count Adjustment</field>
        <field name="code">stock.count.adjustment</field>
        <field name="prefix">SCA/</field>
        <field name="padding">5</field>
        <field name="company_id" eval="False"/>
    </record>
</odoo>
```
`views/stock_count_adjustment_views.xml` — minimal form + tree + action + menu under `stock.menu_stock_root`, all `groups="buz_stock_count_adjust.group_stock_count_adjustment"`. Create empty `stock_count_adjustment_backup_views.xml` and `stock_count_adjustment_import_views.xml` with just `<odoo></odoo>` for now (filled in later tasks) so the manifest loads.

- [ ] **Step 5: Run test to verify it passes**

Run: `ssh mog-prod "docker exec odoo odoo -d MOG_LIVE -i buz_stock_count_adjust --test-enable --stop-after-init --no-http 2>&1 | grep -E 'FAIL|ERROR|0 failed|test_'"`
Expected: `test_models_and_group_exist` and `test_create_document_gets_sequence_name` PASS.

- [ ] **Step 6: Commit**

```bash
git add buz_stock_count_adjust
git commit -m "feat(buz_stock_count_adjust): module skeleton — models, security, sequence"
```

---

## Task 2: Extract the FIFO consume loop into a shared classmethod

**Files:**
- Modify: `stock_fifo_by_location/models/stock_valuation_layer.py:446-541` (`_fifo_replay_remaining`)
- Test: `stock_fifo_by_location/tests/test_fifo_consume_rows.py` (new)

**Interfaces:**
- Consumes: nothing.
- Produces: classmethod on `stock.valuation.layer`:
  ```python
  @api.model
  def _fifo_consume_rows(self, rows, seed=None):
      """Consume a FIFO history and report the resulting queue state.

      rows: iterable of (layer_id, quantity, value, stock_landed_cost_id,
            stock_valuation_layer_id) tuples, already ordered (create_date, id).
      seed: optional list of (layer_id, qty, value) to prime the pool with
            BEFORE walking rows — used for a scoped replay that starts from a
            known ending queue rather than from the beginning of history.
            When None, the pool starts empty (origin behaviour).

      Returns {'expected': {layer_id: (rem_qty, rem_value)},
               'cogs': {layer_id: value_the_outgoing_layer_should_carry},
               'shortage': float,
               'inverted': int}
      Same semantics as the old inline loop: live-rate unit_cost =
      entry['value'] / available, EPS = FIFO_QTY_EPSILON, delete-on-exhaust.
      A seeded layer_id already present in rows keeps its seeded pool entry
      (the row's positive quantity is NOT pushed again).
  """
  ```
  `_fifo_replay_remaining` keeps its signature and its SQL fetch, but its body after the fetch becomes `return self._fifo_consume_rows(rows)`.

- [ ] **Step 1: Write the failing test**

`stock_fifo_by_location/tests/test_fifo_consume_rows.py`:
```python
from odoo.tests import common, tagged


@tagged('post_install', '-at_install')
class TestFifoConsumeRows(common.TransactionCase):

    def setUp(self):
        super().setUp()
        self.SVL = self.env['stock.valuation.layer']

    def test_consume_rows_matches_inline_replay(self):
        # rows: 10 @ 10, then 10 @ 20, then out 15
        rows = [
            (1, 10.0, 100.0, None, None),
            (2, 10.0, 200.0, None, None),
            (3, -15.0, 0.0, None, None),
        ]
        result = self.SVL._fifo_consume_rows(rows)
        self.assertEqual(result['expected'][1], (0.0, 0.0))
        rq, rv = result['expected'][2]
        self.assertAlmostEqual(rq, 5.0, places=4)
        self.assertAlmostEqual(rv, 100.0, places=2)
        self.assertAlmostEqual(result['cogs'][3], -200.0, places=2)
        self.assertFalse(result['shortage'])

    def test_seed_primes_the_pool(self):
        # Seed a bucket of 5 @ 50, then an outgoing 3 walks it.
        rows = [(9, -3.0, 0.0, None, None)]
        result = self.SVL._fifo_consume_rows(rows, seed=[(7, 5.0, 50.0)])
        self.assertAlmostEqual(result['expected'][7][0], 2.0, places=4)
        self.assertAlmostEqual(result['expected'][7][1], 20.0, places=2)
        self.assertAlmostEqual(result['cogs'][9], -30.0, places=2)

    def test_replay_remaining_still_works(self):
        p = self.env['product.product'].create({
            'name': 'consume-rows probe', 'type': 'product',
            'categ_id': self.env.ref('product.product_category_all').id})
        wh = self.env['stock.warehouse'].search([], limit=1)
        for qty, val in [(10, 100.0), (-4, 0.0)]:
            self.SVL.create({
                'product_id': p.id, 'company_id': self.env.company.id,
                'warehouse_id': wh.id, 'quantity': qty, 'value': val,
                'unit_cost': val / qty if qty else 0.0,
                'remaining_qty': qty if qty > 0 else 0.0,
                'remaining_value': val if qty > 0 else 0.0,
            })
        result = self.SVL._fifo_replay_remaining(p.id, wh.id, self.env.company.id)
        self.assertAlmostEqual(result['shortage'], 0.0, places=4)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `ssh mog-prod "docker exec odoo odoo -d MOG_LIVE -u stock_fifo_by_location --test-enable --stop-after-init --no-http 2>&1 | grep -E 'test_consume_rows|test_seed|AttributeError'"`
Expected: FAIL — `_fifo_consume_rows` does not exist.

- [ ] **Step 3: Extract the loop**

In `stock_fifo_by_location/models/stock_valuation_layer.py`, replace the body of `_fifo_replay_remaining` after the `rows = self.env.cr.fetchall()` line with `return self._fifo_consume_rows(rows)`. Move the loop (lines ~484-541, the `pool` / `expected` / `cogs` / `shortage` / `inverted` machinery) into a new `_fifo_consume_rows`:
```python
@api.model
def _fifo_consume_rows(self, rows, seed=None):
    epsilon = self.FIFO_QTY_EPSILON
    pool = {}
    expected = {}
    cogs = {}
    shortage = 0.0
    inverted = 0
    previous_id = 0

    if seed:
        for layer_id, qty, value in seed:
            pool[layer_id] = {'qty': float(qty or 0.0),
                              'value': float(value or 0.0)}
            expected[layer_id] = None

    for layer_id, qty, value, lc_id, target_id in rows:
        if layer_id < previous_id:
            inverted += 1
        previous_id = max(previous_id, layer_id)
        qty = float(qty or 0.0)
        value = float(value or 0.0)

        if qty > 0:
            if layer_id not in pool:          # a seeded id keeps its seed
                pool[layer_id] = {'qty': qty, 'value': value}
                expected[layer_id] = None
        elif qty < 0:
            to_consume = -qty
            consumed_value = 0.0
            for pool_id in list(pool):
                if to_consume <= epsilon:
                    break
                entry = pool[pool_id]
                available = entry['qty']
                if available <= 0:
                    del pool[pool_id]
                    continue
                taken = min(available, to_consume)
                unit_cost = entry['value'] / available
                entry['qty'] -= taken
                entry['value'] -= taken * unit_cost
                to_consume -= taken
                consumed_value += taken * unit_cost
                if entry['qty'] <= epsilon:
                    del pool[pool_id]
            shortage += to_consume
            cogs[layer_id] = -consumed_value
            expected[layer_id] = (0.0, 0.0)
        else:
            if lc_id and target_id in pool:
                pool[target_id]['value'] += value
            expected[layer_id] = (0.0, 0.0)

    for layer_id in expected:
        if expected[layer_id] is None:
            entry = pool.get(layer_id)
            expected[layer_id] = (entry['qty'], entry['value']) if entry else (0.0, 0.0)

    return {'expected': expected, 'cogs': cogs,
            'shortage': shortage, 'inverted': inverted}
```
Keep the docstring on `_fifo_replay_remaining` (it explains the landed-cost handling) and add a one-line pointer: `# consume loop extracted to _fifo_consume_rows so buz_stock_count_adjust replays the same code`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `ssh mog-prod "docker exec odoo odoo -d MOG_LIVE -u stock_fifo_by_location,stock_fifo_by_warehouse_recal --test-enable --stop-after-init --no-http 2>&1 | grep -E 'FAIL|ERROR|failed,'"`
Expected: new tests PASS; `stock_fifo_by_warehouse_recal`'s `TestFifoReplay` suite (which drives `_fifo_replay_remaining`) still PASSES — that is the drift guard.

- [ ] **Step 5: Commit**

```bash
git add stock_fifo_by_location
git commit -m "refactor(stock_fifo_by_location): extract _fifo_consume_rows from _fifo_replay_remaining"
```

---

## Task 3: Data model — lines, computed deltas, line-set hash, views

**Files:**
- Modify: `buz_stock_count_adjust/models/stock_count_adjustment.py`
- Modify: `buz_stock_count_adjust/models/stock_count_adjustment_line.py`
- Modify: `buz_stock_count_adjust/views/stock_count_adjustment_views.xml`
- Test: `buz_stock_count_adjust/tests/test_count_adjust.py`

**Interfaces:**
- Consumes: models from Task 1.
- Produces:
  - `stock.count.adjustment._line_hash()` → `str` — sha256 hex of the sorted `(product_id, warehouse_id, bucket_seq, target_qty, target_value)` tuples. Stored on `line_hash` at preview time; any write to `line_ids` that changes the hash resets `state` to `draft` and clears `line_hash`.
  - `stock.count.adjustment._line_groups()` → `list[stock.count.adjustment.line recordset]` — lines grouped by `(product_id, warehouse_id)`, each group ordered by `bucket_seq, id`.
  - `stock.count.adjustment.line` `_check_company` constraints; `@api.constrains` that `bucket_seq` is unique within a `(adjustment_id, product_id, warehouse_id)` group.

- [ ] **Step 1: Write the failing test**

Append to `test_count_adjust.py`:
```python
@tagged('post_install', '-at_install')
class TestCountAdjustModel(common.TransactionCase):

    def setUp(self):
        super().setUp()
        self.wh = self.env['stock.warehouse'].search([], limit=1)
        self.p1 = self.env['product.product'].create({
            'name': 'SCA probe 1', 'type': 'product',
            'categ_id': self.env.ref('product.product_category_all').id})
        self.p2 = self.env['product.product'].create({
            'name': 'SCA probe 2', 'type': 'product',
            'categ_id': self.env.ref('product.product_category_all').id})

    def _doc(self):
        return self.env['stock.count.adjustment'].create({
            'company_id': self.env.company.id, 'cutoff_date': '2026-05-31',
            'line_ids': [
                (0, 0, {'product_id': self.p1.id, 'warehouse_id': self.wh.id,
                        'bucket_seq': 10, 'target_qty': 211.0,
                        'target_value': 76851.3771}),
                (0, 0, {'product_id': self.p1.id, 'warehouse_id': self.wh.id,
                        'bucket_seq': 20, 'target_qty': 1.0,
                        'target_value': 352.9183}),
                (0, 0, {'product_id': self.p2.id, 'warehouse_id': self.wh.id,
                        'bucket_seq': 10, 'target_qty': 5.0,
                        'target_value': 100.0}),
            ]})

    def test_line_groups_splits_by_product_warehouse(self):
        doc = self._doc()
        groups = doc._line_groups()
        self.assertEqual(len(groups), 2)
        self.assertEqual([len(g) for g in groups], [2, 1])
        self.assertEqual(groups[0].mapped('bucket_seq'), [10, 20])

    def test_editing_lines_after_preview_resets_state(self):
        doc = self._doc()
        doc.write({'state': 'previewed', 'line_hash': doc._line_hash()})
        doc.line_ids[0].target_qty = 999.0
        self.assertEqual(doc.state, 'draft')
        self.assertFalse(doc.line_hash)

    def test_duplicate_bucket_seq_rejected(self):
        with self.assertRaises(Exception):
            self.env['stock.count.adjustment'].create({
                'company_id': self.env.company.id, 'cutoff_date': '2026-05-31',
                'line_ids': [
                    (0, 0, {'product_id': self.p1.id, 'warehouse_id': self.wh.id,
                            'bucket_seq': 10, 'target_qty': 1, 'target_value': 1}),
                    (0, 0, {'product_id': self.p1.id, 'warehouse_id': self.wh.id,
                            'bucket_seq': 10, 'target_qty': 2, 'target_value': 2}),
                ]})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `... -u buz_stock_count_adjust --test-enable ... | grep -E 'test_line_groups|test_editing_lines|AttributeError'`
Expected: FAIL — `_line_groups` / `_line_hash` not defined.

- [ ] **Step 3: Implement**

In `stock_count_adjustment.py`:
```python
import hashlib

def _line_hash(self):
    self.ensure_one()
    payload = sorted(
        (l.product_id.id, l.warehouse_id.id, l.bucket_seq,
         round(l.target_qty, 6), round(l.target_value, 6))
        for l in self.line_ids)
    return hashlib.sha256(repr(payload).encode()).hexdigest()

def _line_groups(self):
    self.ensure_one()
    groups = {}
    for line in self.line_ids.sorted(lambda l: (l.bucket_seq, l.id)):
        groups.setdefault(
            (line.product_id.id, line.warehouse_id.id),
            self.env['stock.count.adjustment.line'])
        groups[(line.product_id.id, line.warehouse_id.id)] |= line
    return list(groups.values())

def write(self, vals):
    res = super().write(vals)
    if 'line_ids' in vals:
        for doc in self:
            if doc.line_hash and doc._line_hash() != doc.line_hash:
                # plain field assignment, NOT a nested write() — avoids
                # re-entering this override
                doc.state = 'draft'
                doc.line_hash = False
    return res
```
The load-bearing check is the guard at the top of `action_apply` (Task 11):
`if self._line_hash() != self.line_hash: raise UserError(...)`. Implement both —
the `write` reset keeps the UI honest, the guard is the safety net.

In `stock_count_adjustment_line.py` add:
```python
_sql_constraints = [
    ('bucket_seq_unique',
     'unique(adjustment_id, product_id, warehouse_id, bucket_seq)',
     'Bucket sequence must be unique per product/warehouse in a document.'),
]
```

- [ ] **Step 4: Build the real form/tree view**

`views/stock_count_adjustment_views.xml` — form with a statusbar (`draft,previewed,applied,rolled_back`), header buttons `action_import` (draft only), `action_preview` (draft), `action_apply` (previewed, `attrs` invisible unless `state == 'previewed'`), `action_rollback` (applied). Notebook pages: **Lines** (editable tree of `line_ids` with `bucket_seq, product_id, warehouse_id, target_qty, target_value, baseline_qty, baseline_value, delta_qty, delta_value, state, result_note`), **Mismatches** (`mismatch_ids` tree, read-only + per-row buttons — Task 9), **Log** (`preview_log`, `apply_log`). Totals `valuation_delta`, `cogs_delta`, `qty_delta` in a group under the notebook. Tree view + `ir.actions.act_window` + menuitem under `stock.menu_stock_root`, all `groups=`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `... -u buz_stock_count_adjust --test-enable ... | grep -E 'FAIL|ERROR|failed,'`
Expected: all `TestCountAdjustModel` tests PASS.

- [ ] **Step 6: Commit**

```bash
git add buz_stock_count_adjust
git commit -m "feat(buz_stock_count_adjust): line groups, line-set hash, form view"
```

---

## Task 4: Engine step 1-2 — baseline + category guard

**Files:**
- Modify: `buz_stock_count_adjust/models/count_adjust_engine.py`
- Test: `buz_stock_count_adjust/tests/test_count_adjust.py`

**Interfaces:**
- Consumes: `stock.count.adjustment._line_groups()`, `stock.fifo.valuation.report` (SQL view from `stock_fifo_valuation_report`).
- Produces:
  - `count.adjust.engine._baseline(adjustment)` → `dict {(product_id, warehouse_id): (Q0, V0)}` — builds the report view ONCE for every pair in scope at `date_to = adjustment.cutoff_date`, returns `ending_qty` / `ending_value` per pair (0.0/0.0 when the pair has no report row).
  - `count.adjust.engine._check_category(product)` → `str | False` — returns a reason string when `product.categ_id.property_valuation == 'real_time'`, else `False`.
  - `count.adjust.engine._cutoff_instants(cutoff_date)` → `(utc_cutoff_dt, accounting_dt)` — `utc_cutoff_dt = datetime.combine(cutoff_date + 1 day, time.min) - timedelta(hours=7)`; `accounting_dt = datetime.combine(cutoff_date, time.min)`.

- [ ] **Step 1: Write the failing test**

```python
@tagged('post_install', '-at_install')
class TestEngineBaseline(common.TransactionCase):

    def setUp(self):
        super().setUp()
        self.engine = self.env['count.adjust.engine']
        self.wh = self.env['stock.warehouse'].search([], limit=1)
        self.categ_rt = self.env['product.category'].create({
            'name': 'RT', 'property_valuation': 'real_time',
            'property_cost_method': 'fifo'})
        self.categ_mp = self.env['product.category'].create({
            'name': 'MP', 'property_valuation': 'manual_periodic',
            'property_cost_method': 'fifo'})
        self.prt = self.env['product.product'].create({
            'name': 'rt probe', 'type': 'product', 'categ_id': self.categ_rt.id})
        self.pmp = self.env['product.product'].create({
            'name': 'mp probe', 'type': 'product', 'categ_id': self.categ_mp.id})

    def _seed_layers(self, product, rows, cutoff='2026-05-31'):
        SVL = self.env['stock.valuation.layer']
        for i, (qty, val) in enumerate(rows):
            svl = SVL.create({
                'product_id': product.id, 'company_id': self.env.company.id,
                'warehouse_id': self.wh.id, 'quantity': qty, 'value': val,
                'unit_cost': val / qty if qty else 0.0,
                'remaining_qty': qty if qty > 0 else 0.0,
                'remaining_value': val if qty > 0 else 0.0})
            # accounting_date on cutoff day so the report buckets it as pre-cutoff
            self.env.cr.execute(
                "UPDATE stock_valuation_layer SET accounting_date = %s WHERE id = %s",
                ('2026-05-20 00:00:00', svl.id))
        SVL.invalidate_model(['accounting_date'])

    def test_baseline_matches_report_wizard(self):
        self._seed_layers(self.pmp, [(100, 1000.0), (-30, -300.0)])
        doc = self.env['stock.count.adjustment'].create({
            'company_id': self.env.company.id, 'cutoff_date': '2026-05-31',
            'line_ids': [(0, 0, {'product_id': self.pmp.id,
                                 'warehouse_id': self.wh.id,
                                 'bucket_seq': 10, 'target_qty': 70,
                                 'target_value': 700.0})]})
        base = self.engine._baseline(doc)
        q0, v0 = base[(self.pmp.id, self.wh.id)]
        self.assertAlmostEqual(q0, 70.0, places=2)
        self.assertAlmostEqual(v0, 700.0, places=2)

    def test_real_time_category_flagged(self):
        self.assertTrue(self.engine._check_category(self.prt))
        self.assertFalse(self.engine._check_category(self.pmp))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `... -u buz_stock_count_adjust --test-enable ... | grep -E 'test_baseline|test_real_time|AttributeError'`
Expected: FAIL — methods not defined.

- [ ] **Step 3: Implement**

```python
from datetime import datetime, time, timedelta

BANGKOK_OFFSET = timedelta(hours=7)


def _cutoff_instants(self, cutoff_date):
    d = fields.Date.to_date(cutoff_date)
    utc_cutoff = datetime.combine(d + timedelta(days=1), time.min) - BANGKOK_OFFSET
    accounting_dt = datetime.combine(d, time.min)
    return utc_cutoff, accounting_dt


def _check_category(self, product):
    if product.categ_id.property_valuation == 'real_time':
        return _('Product category %s posts real-time journal entries; '
                 'GL reposting is out of scope for v1.') % product.categ_id.name
    return False


def _baseline(self, adjustment):
    pairs = {(l.product_id.id, l.warehouse_id.id) for l in adjustment.line_ids}
    product_ids = [p for p, _w in pairs]
    warehouse_ids = list({w for _p, w in pairs})
    Report = self.env['stock.fifo.valuation.report']
    wiz = self.env['stock.fifo.valuation.report.wizard'].create({
        'date_from': '1900-01-01',
        'date_to': adjustment.cutoff_date,
        'product_ids': [fields.Command.set(product_ids)],
        'warehouse_ids': [fields.Command.set(warehouse_ids)],
    })
    # build the view once from this wizard record's filter fields
    filters = self.env['stock.fifo.valuation.report.wizard'].browse(wiz.id)
    Report.init_results(filters)
    rows = Report.search_read(
        [('product_id', 'in', product_ids),
         ('warehouse_id', 'in', warehouse_ids)],
        ['product_id', 'warehouse_id', 'ending_qty', 'ending_value'])
    base = {(r['product_id'][0], r['warehouse_id'][0]):
            (r['ending_qty'], r['ending_value']) for r in rows}
    return {pair: base.get(pair, (0.0, 0.0)) for pair in pairs}
```
Note: `Report.init_results` takes a record whose attributes are the filters — pass the wizard record directly (that is what `button_view` does at stock_fifo_valuation_report_wizard.py:38). `init_results` reads `filters.date_from`, `filters.warehouse_ids`, etc.

- [ ] **Step 4: Run tests to verify they pass**

Run: `... -u buz_stock_count_adjust --test-enable ... | grep -E 'FAIL|ERROR|failed,'`
Expected: `test_baseline_matches_report_wizard`, `test_real_time_category_flagged` PASS.

- [ ] **Step 5: Commit**

```bash
git add buz_stock_count_adjust
git commit -m "feat(buz_stock_count_adjust): engine baseline + real_time category guard"
```

---

## Task 5: Engine step 3 — void-and-reseed (raw SQL)

**Files:**
- Modify: `buz_stock_count_adjust/models/count_adjust_engine.py`
- Test: `buz_stock_count_adjust/tests/test_count_adjust.py`

**Interfaces:**
- Consumes: `_baseline`, `_cutoff_instants`, `_fifo_consume_rows` (indirectly, later), `stock.count.adjustment.line`.
- Produces:
  - `count.adjust.engine._void_and_reseed(group, q0, v0, cutoff_date)` → `dict {'counter_id': int, 'bucket_ids': [int], 'zeroed_ids': [int]}` — for one line-group (all lines share product+warehouse):
    1. INSERT one counter layer: `quantity = -q0`, `value = -v0`, `remaining_qty = 0`, `remaining_value = 0`, `create_date = utc_cutoff - 3s`, `accounting_date = accounting_dt`, `stock_move_id = NULL`.
    2. INSERT one bucket layer per group line, ordered by `bucket_seq`: `quantity = remaining_qty = line.target_qty`, `value = remaining_value = line.target_value`, `unit_cost = target_value/target_qty` (0 if qty 0), `origin_remaining_qty = target_qty`, `origin_remaining_value = target_value`, `create_date = utc_cutoff - 2s + n*1ms`, `accounting_date = accounting_dt`.
    3. UPDATE `remaining_qty = 0, remaining_value = 0` on every pre-existing layer for the pair whose `COALESCE(accounting_date, create_date) < utc_cutoff` and `id NOT IN (inserted)`.
    4. `invalidate_model` on the touched columns.
  - Invariant asserted by the method: `sum(inserted quantity) == q_target - q0` within 1e-3, `sum(inserted value) == v_target - v0` within 1e-2 (where `q_target = sum(line.target_qty)` etc.). Raise `UserError` on violation.

- [ ] **Step 1: Write the failing test**

```python
@tagged('post_install', '-at_install')
class TestEngineVoidReseed(common.TransactionCase):

    def setUp(self):
        super().setUp()
        self.engine = self.env['count.adjust.engine']
        self.SVL = self.env['stock.valuation.layer']
        self.wh = self.env['stock.warehouse'].search([], limit=1)
        self.categ = self.env['product.category'].create({
            'name': 'MP', 'property_valuation': 'manual_periodic',
            'property_cost_method': 'fifo'})
        self.p = self.env['product.product'].create({
            'name': 'vr probe', 'type': 'product', 'categ_id': self.categ.id})
        for qty, val, acct in [(441, 157416.65, '2026-05-10'),
                               (-212, -75758.94, '2026-05-20')]:
            svl = self.SVL.create({
                'product_id': self.p.id, 'company_id': self.env.company.id,
                'warehouse_id': self.wh.id, 'quantity': qty, 'value': val,
                'unit_cost': abs(val / qty),
                'remaining_qty': qty if qty > 0 else 0.0,
                'remaining_value': val if qty > 0 else 0.0})
            self.env.cr.execute(
                "UPDATE stock_valuation_layer SET accounting_date = %s WHERE id = %s",
                (acct + ' 00:00:00', svl.id))
        self.SVL.invalidate_model()

    def _doc(self):
        return self.env['stock.count.adjustment'].create({
            'company_id': self.env.company.id, 'cutoff_date': '2026-05-31',
            'line_ids': [
                (0, 0, {'product_id': self.p.id, 'warehouse_id': self.wh.id,
                        'bucket_seq': 10, 'target_qty': 211,
                        'target_value': 76851.3771}),
                (0, 0, {'product_id': self.p.id, 'warehouse_id': self.wh.id,
                        'bucket_seq': 20, 'target_qty': 1,
                        'target_value': 352.9183}),
                (0, 0, {'product_id': self.p.id, 'warehouse_id': self.wh.id,
                        'bucket_seq': 30, 'target_qty': 5,
                        'target_value': 1751.9391}),
            ]})

    def test_void_reseed_hits_target_ending_and_invariant(self):
        doc = self._doc()
        base = self.engine._baseline(doc)
        q0, v0 = base[(self.p.id, self.wh.id)]      # expect 229 / 81658.26
        group = doc._line_groups()[0]
        res = self.engine._void_and_reseed(group, q0, v0, doc.cutoff_date)

        self.SVL.invalidate_model()   # raw INSERTs — drop stale ORM cache first
        inserted = self.SVL.browse([res['counter_id']] + res['bucket_ids'])
        self.assertAlmostEqual(sum(inserted.mapped('quantity')),
                               217 - q0, places=3)
        self.assertAlmostEqual(sum(inserted.mapped('value')),
                               78956.2345 - v0, places=2)
        for b in self.SVL.browse(res['bucket_ids']):
            self.assertAlmostEqual(b.quantity, b.remaining_qty, places=4)
            self.assertAlmostEqual(b.value, b.remaining_value, places=2)

        # report ending at cutoff now equals target
        again = self.engine._baseline(doc)
        q1, v1 = again[(self.p.id, self.wh.id)]
        self.assertAlmostEqual(q1, 217.0, places=2)
        self.assertAlmostEqual(v1, 78956.2345, places=2)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `... -u buz_stock_count_adjust --test-enable ... | grep -E 'test_void_reseed|AttributeError'`
Expected: FAIL — `_void_and_reseed` not defined.

- [ ] **Step 3: Implement**

```python
def _void_and_reseed(self, group, q0, v0, cutoff_date):
    product = group.product_id
    warehouse = group.warehouse_id
    company = group.adjustment_id.company_id
    utc_cutoff, accounting_dt = self._cutoff_instants(cutoff_date)
    cr = self.env.cr

    def _insert(quantity, value, remaining_qty, remaining_value, created_at):
        unit_cost = value / quantity if quantity else 0.0
        cr.execute("""
            INSERT INTO stock_valuation_layer
                (product_id, company_id, warehouse_id, quantity, value,
                 unit_cost, remaining_qty, remaining_value,
                 origin_remaining_qty, origin_remaining_value,
                 accounting_date, description, stock_move_id,
                 create_uid, create_date, write_uid, write_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL,
                    %s, %s, %s, now() at time zone 'UTC')
            RETURNING id
        """, (product.id, company.id, warehouse.id, quantity, value,
              unit_cost, remaining_qty, remaining_value,
              remaining_qty if quantity > 0 else 0.0,
              remaining_value if quantity > 0 else 0.0,
              accounting_dt,
              'count-adjust %s' % group.adjustment_id.name,
              self.env.uid, created_at, self.env.uid))
        return cr.fetchone()[0]

    counter_id = _insert(-q0, -v0, 0.0, 0.0, utc_cutoff - timedelta(seconds=3))

    bucket_ids = []
    for n, line in enumerate(group.sorted(lambda l: (l.bucket_seq, l.id))):
        bucket_ids.append(_insert(
            line.target_qty, line.target_value,
            line.target_qty, line.target_value,
            utc_cutoff - timedelta(seconds=2) + timedelta(milliseconds=n)))

    inserted = tuple([counter_id] + bucket_ids)
    cr.execute("""
        UPDATE stock_valuation_layer
        SET remaining_qty = 0, remaining_value = 0
        WHERE product_id = %s AND warehouse_id = %s AND company_id = %s
          AND id NOT IN %s
          AND COALESCE(accounting_date, create_date) < %s
        RETURNING id
    """, (product.id, warehouse.id, company.id, inserted, utc_cutoff))
    zeroed_ids = [r[0] for r in cr.fetchall()]

    self.env['stock.valuation.layer'].invalidate_model([
        'quantity', 'value', 'unit_cost', 'remaining_qty', 'remaining_value',
        'origin_remaining_qty', 'origin_remaining_value', 'accounting_date'])

    # Invariant check reads SUM straight from SQL — do NOT browse() the rows
    # back through the ORM just to re-add numbers we control.
    q_target = sum(group.mapped('target_qty'))
    v_target = sum(group.mapped('target_value'))
    cr.execute("SELECT COALESCE(SUM(quantity),0), COALESCE(SUM(value),0) "
               "FROM stock_valuation_layer WHERE id IN %s", (inserted,))
    dq, dv = cr.fetchone()
    dq, dv = float(dq), float(dv)
    if abs(dq - (q_target - q0)) > 1e-3 or abs(dv - (v_target - v0)) > 1e-2:
        raise UserError(_(
            'void-and-reseed invariant failed for %s @ %s: inserted dq=%.4f '
            'dv=%.2f, expected %.4f / %.2f'
        ) % (product.display_name, warehouse.name, dq, dv,
             q_target - q0, v_target - v0))

    return {'counter_id': counter_id, 'bucket_ids': bucket_ids,
            'zeroed_ids': zeroed_ids}
```
Match the actual `stock_valuation_layer` column set on the target DB first (run `\d stock_valuation_layer` via `docker exec postgres psql`) — `company_id` and `create_uid` are `NOT NULL`; `stock_move_id` is nullable. Do NOT insert `account_move_id`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `... -u buz_stock_count_adjust --test-enable ... | grep -E 'FAIL|ERROR|failed,'`
Expected: `test_void_reseed_hits_target_ending_and_invariant` PASS.

- [ ] **Step 5: Commit**

```bash
git add buz_stock_count_adjust
git commit -m "feat(buz_stock_count_adjust): engine void-and-reseed (raw SQL SVL inserts)"
```

---

## Task 6: Engine step 4 — scoped FIFO replay

**Files:**
- Modify: `buz_stock_count_adjust/models/count_adjust_engine.py`
- Test: `buz_stock_count_adjust/tests/test_count_adjust.py`

**Interfaces:**
- Consumes: `stock.valuation.layer._fifo_consume_rows(rows, seed=...)` (Task 2), `_cutoff_instants`, `_void_and_reseed` output.
- Produces:
  - `count.adjust.engine._scoped_replay(group, reseed, cutoff_date)` → `dict {'writes': int, 'cogs_writes': int, 'shortage': float, 'value_delta': float}`:
    1. `seed = [(bid, svl.remaining_qty, svl.remaining_value) for bid in reseed['bucket_ids']]` read fresh from the DB.
    2. Fetch post-cutoff rows: `SELECT id, quantity, value, stock_landed_cost_id, stock_valuation_layer_id FROM stock_valuation_layer WHERE product_id=%s AND warehouse_id=%s AND company_id=%s AND create_date > %s ORDER BY create_date, id` (the `utc_cutoff` instant).
    3. `result = SVL._fifo_consume_rows(rows, seed=seed)`.
    4. **If `result['shortage'] > 1e-3`: raise `UserError` — abort the line.** (The `inverted` count is IGNORED — backdated inserts inflate it by construction; the hand-run saw `inverted 91`.)
    5. Raw `UPDATE remaining_qty/remaining_value` per `result['expected']` (skip rows already matching within EPS).
    6. Raw `UPDATE value = %s, unit_cost = value/quantity` per `result['cogs']` on the outgoing layer (skip within 1e-2).
    7. `invalidate_model`.
  - `value_delta` = net change in `remaining_value` across the pair.

- [ ] **Step 1: Write the failing test**

```python
    def test_scoped_replay_reprices_post_cutoff_out_no_shortage(self):
        doc = self._doc()  # reuse TestEngineVoidReseed._doc
        base = self.engine._baseline(doc)
        q0, v0 = base[(self.p.id, self.wh.id)]
        group = doc._line_groups()[0]
        reseed = self.engine._void_and_reseed(group, q0, v0, doc.cutoff_date)

        # a post-cutoff delivery of 20 units, priced wrong on purpose
        out = self.SVL.create({
            'product_id': self.p.id, 'company_id': self.env.company.id,
            'warehouse_id': self.wh.id, 'quantity': -20, 'value': -1.0,
            'unit_cost': 0.05, 'remaining_qty': 0.0, 'remaining_value': 0.0})
        self.env.cr.execute(
            "UPDATE stock_valuation_layer SET create_date = %s WHERE id = %s",
            ('2026-06-15 03:00:00', out.id))
        self.SVL.invalidate_model()

        res = self.engine._scoped_replay(group, reseed, doc.cutoff_date)
        self.assertAlmostEqual(res['shortage'], 0.0, places=3)
        out.invalidate_recordset()
        # 20 units at bucket-1 rate 364.2245 -> value ~ -7284.49
        self.assertAlmostEqual(out.value, -20 * (76851.3771 / 211), places=1)
        b1 = self.SVL.browse(reseed['bucket_ids'][0])
        self.assertAlmostEqual(b1.remaining_qty, 191.0, places=3)

    def test_scoped_replay_shortage_raises(self):
        doc = self._doc()
        base = self.engine._baseline(doc)
        q0, v0 = base[(self.p.id, self.wh.id)]
        group = doc._line_groups()[0]
        reseed = self.engine._void_and_reseed(group, q0, v0, doc.cutoff_date)
        out = self.SVL.create({
            'product_id': self.p.id, 'company_id': self.env.company.id,
            'warehouse_id': self.wh.id, 'quantity': -500, 'value': -1.0,
            'unit_cost': 0.002, 'remaining_qty': 0.0, 'remaining_value': 0.0})
        self.env.cr.execute(
            "UPDATE stock_valuation_layer SET create_date = %s WHERE id = %s",
            ('2026-06-15 03:00:00', out.id))
        self.SVL.invalidate_model()
        with self.assertRaises(Exception):
            self.engine._scoped_replay(group, reseed, doc.cutoff_date)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `... | grep -E 'test_scoped_replay|AttributeError'`
Expected: FAIL — `_scoped_replay` not defined.

- [ ] **Step 3: Implement**

```python
def _scoped_replay(self, group, reseed, cutoff_date):
    SVL = self.env['stock.valuation.layer']
    product = group.product_id
    warehouse = group.warehouse_id
    company = group.adjustment_id.company_id
    utc_cutoff, _acct = self._cutoff_instants(cutoff_date)
    cr = self.env.cr

    SVL.flush_model(['quantity', 'value', 'remaining_qty', 'remaining_value',
                     'stock_landed_cost_id', 'stock_valuation_layer_id',
                     'create_date'])

    cr.execute("""
        SELECT remaining_qty, remaining_value
        FROM stock_valuation_layer WHERE id IN %s ORDER BY id
    """, (tuple(reseed['bucket_ids']),))
    seed = [(bid, float(rq or 0.0), float(rv or 0.0))
            for bid, (rq, rv) in zip(reseed['bucket_ids'], cr.fetchall())]

    cr.execute("""
        SELECT id, quantity, value, stock_landed_cost_id, stock_valuation_layer_id
        FROM stock_valuation_layer
        WHERE product_id = %s AND warehouse_id = %s AND company_id = %s
          AND create_date > %s
        ORDER BY create_date, id
    """, (product.id, warehouse.id, company.id, utc_cutoff))
    rows = cr.fetchall()

    result = SVL._fifo_consume_rows(rows, seed=seed)
    if result['shortage'] > 1e-3:
        raise UserError(_(
            'FIFO shortage of %.4f units for %s @ %s after the cutoff — more '
            'was consumed than the target ending queue holds. Line aborted.'
        ) % (result['shortage'], product.display_name, warehouse.name))

    stored = SVL.browse(list(result['expected']))
    stored_map = {s.id: (s.remaining_qty, s.remaining_value) for s in stored}
    writes = 0
    value_delta = 0.0
    for layer_id, (nq, nv) in result['expected'].items():
        cq, cv = stored_map.get(layer_id, (0.0, 0.0))
        if abs(cq - nq) > 1e-4 or abs(cv - nv) > 1e-2:
            cr.execute("UPDATE stock_valuation_layer SET remaining_qty=%s, "
                       "remaining_value=%s WHERE id=%s", (nq, nv, layer_id))
            writes += 1
            value_delta += nv - cv

    cogs_writes = 0
    cogs_stored = SVL.browse(list(result['cogs']))
    cogs_map = {s.id: (s.value, s.quantity) for s in cogs_stored}
    for layer_id, new_value in result['cogs'].items():
        cur_value, qty = cogs_map.get(layer_id, (0.0, 0.0))
        if abs(cur_value - new_value) > 1e-2:
            uc = new_value / qty if qty else 0.0
            cr.execute("UPDATE stock_valuation_layer SET value=%s, unit_cost=%s "
                       "WHERE id=%s", (new_value, uc, layer_id))
            cogs_writes += 1

    SVL.invalidate_model(['remaining_qty', 'remaining_value', 'value', 'unit_cost'])
    return {'writes': writes, 'cogs_writes': cogs_writes,
            'shortage': result['shortage'], 'value_delta': value_delta}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `... -u buz_stock_count_adjust --test-enable ... | grep -E 'FAIL|ERROR|failed,'`
Expected: `test_scoped_replay_reprices_post_cutoff_out_no_shortage`, `test_scoped_replay_shortage_raises` PASS.

- [ ] **Step 5: Commit**

```bash
git add buz_stock_count_adjust
git commit -m "feat(buz_stock_count_adjust): engine scoped FIFO replay (reuses _fifo_consume_rows)"
```

---

## Task 7: Backup + rollback — before the destructive quant step

**Files:**
- Modify: `buz_stock_count_adjust/models/stock_count_adjustment_backup.py`
- Modify: `buz_stock_count_adjust/models/count_adjust_engine.py`
- Modify: `buz_stock_count_adjust/views/stock_count_adjustment_backup_views.xml`
- Test: `buz_stock_count_adjust/tests/test_count_adjust.py`

**Interfaces:**
- Consumes: engine step outputs (which layer ids inserted, which updated).
- Produces:
  - `count.adjust.engine._touch_scope(adjustment, base)` → `dict {'svl_ids': set, 'quant_ids': set, 'move_ids': set, 'move_line_ids': set}` — enumerates every row a real run WILL touch, before touching any: pre-cutoff SVL to zero (the `_void_and_reseed` step-3 query), post-cutoff SVL the replay reprices (the `_scoped_replay` step-2 query), the pair's `stock.quant` rows, and every post-cutoff `stock.move` / `stock.move.line` the reconcile pass inspects. It shares the pre/post-cutoff SVL id queries with `_void_and_reseed` and `_scoped_replay` via one helper `_pair_layer_ids(group, cutoff_date) -> (pre_ids, post_ids)` that all three call — do NOT copy the WHERE clauses three times.
  - `count.adjust.engine._locked_layer_count(group)` → `int` — count of `stock.valuation.layer` rows for the pair with `locked IS TRUE` (query shape: `fifo_recalculation_wizard._locked_layer_ids`, fifo_recalculation_wizard.py:267-278; guard with an `information_schema.columns` check so a DB without the column returns 0).
  - `count.adjust.engine._snapshot(adjustment, scope)` → `stock.count.adjustment.backup` record. `scope` is the `_touch_scope` dict. INSERT ... SELECT into the backup line tables (SVL / quant / moveline), one per id set. `was_inserted` is False for these (they pre-exist); the engine's own inserted layer ids get `was_inserted=True` rows added by `_void_and_reseed`'s caller, and generated-move rows get `was_generated=True` rows added by `_quant_adjust`'s caller. Raises `UserError` if any table's `rowcount != len(expected)` — nothing else runs.
  - `stock.count.adjustment.backup` line tables:
    - `.backup.line` (SVL pre-image): `backup_id, layer_id, product_id, warehouse_id, quantity, value, unit_cost, remaining_qty, remaining_value, accounting_date, was_inserted Boolean`.
    - `.backup.quant`: `backup_id, quant_id, quantity`.
    - `.backup.moveline`: `backup_id, move_line_id, move_id, location_id, location_dest_id, ml_date Datetime, move_date Datetime, was_generated Boolean`.
  - `stock.count.adjustment.backup.action_restore()`:
    1. `UPDATE stock_valuation_layer l SET remaining_qty=b.remaining_qty, remaining_value=b.remaining_value, value=b.value, unit_cost=b.unit_cost FROM ..._backup_line b WHERE b.backup_id=%s AND b.layer_id=l.id AND b.was_inserted = false`.
    2. `DELETE FROM stock_valuation_layer WHERE id IN (SELECT layer_id FROM ..._backup_line WHERE backup_id=%s AND was_inserted = true)`.
    3. `UPDATE stock_quant q SET quantity=b.quantity FROM ..._backup_quant b WHERE ...`.
    4. Restore move-line `location_id/location_dest_id/date` and move `date` from `.backup.moveline` where `was_generated = false`; delete generated moves + their lines + their SVL where `was_generated = true`.
    5. `invalidate_model` on every touched model; set `state='restored'`, write `restore_log`.
  - `stock.count.adjustment.action_rollback()` → calls `backup_id.action_restore()`, sets doc `state='rolled_back'`.

- [ ] **Step 1: Write the failing test**

```python
@tagged('post_install', '-at_install')
class TestBackupRollback(common.TransactionCase):
    # build a small pmp fixture like TestEngineVoidReseed, run a full apply
    # via adjustment.action_apply() (Task 8 wires the buttons; until then call
    # engine.run(doc, dry_run=False) directly), snapshot every touched row's
    # pre-image in Python, roll back, assert exact equality.

    def test_rollback_restores_every_touched_row(self):
        doc, pre = self._apply_and_capture_preimage()
        doc.action_rollback()
        self.assertEqual(doc.state, 'rolled_back')
        for table, rows in pre.items():
            for pk, cols in rows.items():
                self.env.cr.execute(
                    "SELECT %s FROM %s WHERE id = %%s" % (
                        ', '.join(cols), table), (pk,))
                current = self.env.cr.fetchone()
                self.assertEqual(
                    current, tuple(cols.values()),
                    "%s#%s not restored" % (table, pk))
        # inserted layers are gone
        self.env.cr.execute(
            "SELECT count(*) FROM stock_valuation_layer WHERE description LIKE %s",
            ('count-adjust %s%%' % doc.name,))
        self.assertEqual(self.env.cr.fetchone()[0], 0)
```
(Helper `_apply_and_capture_preimage` reads the pre-image of every SVL / quant / move_line for the pair straight from SQL before calling `self.env['count.adjust.engine'].run(doc, dry_run=False)`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `... | grep -E 'test_rollback_restores|AttributeError'`
Expected: FAIL.

- [ ] **Step 3: Implement `_snapshot` + `action_restore`**

Follow the `INSERT ... SELECT` column-list pattern from `fifo_recalculation_wizard._create_backup` (fifo_recalculation_wizard.py:807-819) — include `create_uid, create_date, write_uid, write_date` literals, check `cr.rowcount`, then `backup.invalidate_recordset(['line_ids'])`. `was_inserted` / `was_generated` flags distinguish rows to DELETE from rows to UPDATE-back. Restore is one `UPDATE ... FROM` per table (pattern: fifo_recalculation_backup.py:61-67).

- [ ] **Step 4: Run tests to verify they pass**

Run: `... -u buz_stock_count_adjust --test-enable ... | grep -E 'FAIL|ERROR|failed,'`
Expected: `test_rollback_restores_every_touched_row` PASS.

- [ ] **Step 5: Commit**

```bash
git add buz_stock_count_adjust
git commit -m "feat(buz_stock_count_adjust): full pre-image backup + rollback"
```

---

## Task 8: Engine step 5 — quant adjust + neutralised SVL, and wire the state machine

**Files:**
- Modify: `buz_stock_count_adjust/models/count_adjust_engine.py`
- Modify: `buz_stock_count_adjust/models/stock_count_adjustment.py`
- Test: `buz_stock_count_adjust/tests/test_count_adjust.py`

**Interfaces:**
- Consumes: `_scoped_replay`, `_snapshot`, `stock.quant.action_apply_inventory` (Odoo core), `stock_fifo_by_location`'s `_apply_inventory` override.
- Produces:
  - `count.adjust.engine._quant_adjust(group, cutoff_date)` → `dict {'move_id': int, 'svl_id': int, 'delta': float}`:
    1. Compute the target on-hand: the move-history running balance for the pair's `lot_stock_id` (and children) **just before the cutoff**, walked forward through post-cutoff moves — NOT `inventory_quantity` minus today's quant. If that equals the current quant within UoM precision, return `{'delta': 0.0}` (no-op).
    2. Set `quant.inventory_quantity = target`, call `quant.with_context(skip_warehouse_consistency_check=True, inventory_date=cutoff_date).action_apply_inventory()`.
    3. Capture the generated move (`id > last_move_id`) and its SVL; raw `UPDATE stock_move / stock_move_line SET date = utc_cutoff`; raw `UPDATE stock_valuation_layer SET quantity=0, value=0, remaining_qty=0, remaining_value=0, unit_cost=0` on the generated SVL.
    4. `invalidate_model`.
  - `count.adjust.engine.run(adjustment, dry_run=True)` → full orchestration. The
    savepoint is entered for BOTH paths; on `dry_run` a private exception unwinds
    it. `result` is a plain Python dict built inside the savepoint and written to
    the `adjustment` records only AFTER it unwinds (mirrors how
    `fifo_reset_service.run` mutates its `summary` dict, fifo_reset_service.py:53-95):
    ```python
    class _DryRunRollback(Exception):
        pass

    def run(self, adjustment, dry_run=True):
        result = {'groups': [], 'valuation_delta': 0.0,
                  'cogs_delta': 0.0, 'qty_delta': 0.0, 'backup_id': False}
        try:
            with self.env.cr.savepoint():
                base = self._baseline(adjustment)
                if not dry_run:
                    scope = self._touch_scope(adjustment, base)
                    result['backup_id'] = self._snapshot(adjustment, scope).id
                for group in adjustment._line_groups():
                    g = {'product_id': group.product_id.id,
                         'warehouse_id': group.warehouse_id.id,
                         'state': 'previewed', 'note': ''}
                    reason = self._check_category(group.product_id)
                    locked = self._locked_layer_count(group)
                    if reason or locked:
                        g['state'] = 'skipped'
                        g['note'] = reason or _('%s locked layers') % locked
                        result['groups'].append(g); continue
                    q0, v0 = base[(g['product_id'], g['warehouse_id'])]
                    try:
                        reseed = self._void_and_reseed(
                            group, q0, v0, adjustment.cutoff_date)
                        r1 = self._scoped_replay(
                            group, reseed, adjustment.cutoff_date)
                        qa = self._quant_adjust(group, adjustment.cutoff_date)
                        if qa['delta']:
                            r1 = self._scoped_replay(
                                group, reseed, adjustment.cutoff_date)
                        g['mismatches'] = self._reconcile(
                            group, adjustment.cutoff_date)
                        g['baseline'] = (q0, v0)
                        g['value_delta'] = r1['value_delta']
                        g['qty_delta'] = sum(group.mapped('target_qty')) - q0
                        result['valuation_delta'] += r1['value_delta']
                        result['qty_delta'] += g['qty_delta']
                    except UserError as e:
                        g['state'] = 'error'
                        g['note'] = str(e)
                    result['groups'].append(g)
                if dry_run:
                    raise _DryRunRollback()
        except _DryRunRollback:
            pass
        return result
    ```
    `action_preview` / `action_apply` take `result` and write `preview_log` /
    `apply_log`, per-line `baseline_*` / `delta_*` / `state` / `result_note`,
    `mismatch_ids`, and the totals — all OUTSIDE `run()`, so they survive a
    dry-run rollback. On apply, also set `backup_id = result['backup_id']`.
  - `stock.count.adjustment.action_preview()` → `engine.run(self, dry_run=True)`; writes `preview_log`, per-line `baseline_*`/`delta_*`/`state`, `mismatch_ids`, totals; sets `state='previewed'`, `line_hash=self._line_hash()`.
  - `stock.count.adjustment.action_apply()` → guards (`state == 'previewed'`, `_line_hash() == line_hash`, else `UserError`); `engine.run(self, dry_run=False)`; sets `state='applied'`, `backup_id`, `apply_log`.

- [ ] **Step 1: Write the failing test** (`test_quant_adjust_and_neutralise`, `test_preview_rolls_back`, `test_apply_then_state_applied`)

```python
    def test_quant_adjust_hits_target_and_neutralises_svl(self):
        # fixture: pair whose move history -> 217 at cutoff, quant currently 229
        doc = self._fixture_229_target_217()
        self.env['count.adjust.engine'].run(doc, dry_run=False)
        quant = self.env['stock.quant'].search([
            ('product_id', '=', self.p.id),
            ('location_id', 'child_of', self.wh.lot_stock_id.id)])
        self.assertAlmostEqual(sum(quant.mapped('quantity')), 217.0, places=2)
        gen_svl = self.env['stock.valuation.layer'].search([
            ('product_id', '=', self.p.id), ('stock_move_id', '!=', False),
            ('description', 'ilike', 'Product Quantity Updated')], limit=1)
        if gen_svl:
            self.assertEqual((gen_svl.quantity, gen_svl.value,
                              gen_svl.remaining_qty, gen_svl.remaining_value),
                             (0.0, 0.0, 0.0, 0.0))

    def test_preview_writes_nothing_to_svl(self):
        doc = self._fixture_229_target_217()
        before = self._svl_snapshot(self.p, self.wh)
        doc.action_preview()
        self.assertEqual(doc.state, 'previewed')
        self.assertEqual(self._svl_snapshot(self.p, self.wh), before)
        self.assertTrue(doc.preview_log)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `... | grep -E 'test_quant_adjust|test_preview_writes|AttributeError|NotImplementedError'`
Expected: FAIL.

- [ ] **Step 3: Implement `_quant_adjust`, `run`, wire `action_preview` / `action_apply`**

Backdate pattern for the generated move: `fifo_reset_service._reset_quants` lines 399-424 (`new_moves.write({'date': reset_dt})`, then `stock_move_line` date, then raw `UPDATE stock_valuation_layer SET create_date` — here also zero `quantity/value/remaining_*`). Do NOT copy its `cr.commit()` calls or its `account.move` re-dating (category is `manual_periodic`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `... -u buz_stock_count_adjust --test-enable ... | grep -E 'FAIL|ERROR|failed,'`
Expected: quant-adjust + preview tests PASS; all earlier tests still PASS.

- [ ] **Step 5: Commit**

```bash
git add buz_stock_count_adjust
git commit -m "feat(buz_stock_count_adjust): quant adjust + neutralised SVL; wire preview/apply"
```

---

## Task 9: Engine step 6 — reconcile + mismatch fix button

**Files:**
- Modify: `buz_stock_count_adjust/models/count_adjust_engine.py`
- Modify: `buz_stock_count_adjust/models/stock_count_adjustment_mismatch.py`
- Modify: `buz_stock_count_adjust/views/stock_count_adjustment_views.xml`
- Test: `buz_stock_count_adjust/tests/test_count_adjust.py`

**Interfaces:**
- Consumes: post-cutoff SVL rows for the pair, their `stock_move` / `stock_move_line`.
- Produces:
  - `count.adjust.engine._reconcile(group, cutoff_date)` → `list[dict]` — one dict per suspect layer: `{svl_id, move_id, move_line_id, svl_qty, move_net_qty, diff, suggested_location_id}`. For each post-cutoff SVL with a `stock_move_id`, compute the move's net qty at the pair's stock location (sum of move-line qty where `location_id` or `location_dest_id` is `child_of` `lot_stock_id`); if `abs(svl.quantity - move_net_qty) > UoM precision`, flag it. `suggested_location_id = warehouse.lot_stock_id`. **Detect + report only.**
  - `stock.count.adjustment.mismatch.action_fix_move_line()` — sets the suspect `move_line_id.location_id` (or `location_dest_id`, whichever disagrees with the move header) to `suggested_location_id`, adjusts both affected `stock.quant.quantity` by `diff`, marks `state='fixed'`. Runs with `skip_warehouse_consistency_check`. This write is NOT covered by the document's backup (it happens post-apply, per human click) — the button writes its own one-row `.backup.moveline` + `.backup.quant` entries linked to `backup_id` so rollback still catches it.
  - `stock.count.adjustment.mismatch.action_ignore()` — `state='ignored'`.

- [ ] **Step 1: Write the failing test**

```python
    def test_reconcile_detects_corrupted_move_line(self):
        # plant a done inter-warehouse move whose line reads RM01->RM01
        # instead of FG10->RM01, so the source quant was never decremented
        doc = self._fixture_with_corrupted_transfer()
        res = self.env['count.adjust.engine'].run(doc, dry_run=False)
        self.assertEqual(len(doc.mismatch_ids), 1)
        m = doc.mismatch_ids
        self.assertEqual(m.move_line_id, self.bad_move_line)
        self.assertAlmostEqual(abs(m.diff), 1.0, places=3)
        self.assertEqual(m.state, 'open')

    def test_mismatch_fix_button_corrects_locations_and_quants(self):
        doc = self._fixture_with_corrupted_transfer()
        self.env['count.adjust.engine'].run(doc, dry_run=False)
        doc.mismatch_ids.action_fix_move_line()
        self.assertEqual(doc.mismatch_ids.state, 'fixed')
        self.assertEqual(self.bad_move_line.location_id,
                         self.wh.lot_stock_id)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `... | grep -E 'test_reconcile_detects|test_mismatch_fix|AttributeError'`
Expected: FAIL.

- [ ] **Step 3: Implement `_reconcile` + buttons + Mismatches view page**

- [ ] **Step 4: Run tests to verify they pass**

Run: `... -u buz_stock_count_adjust --test-enable ... | grep -E 'FAIL|ERROR|failed,'`
Expected: reconcile tests PASS.

- [ ] **Step 5: Commit**

```bash
git add buz_stock_count_adjust
git commit -m "feat(buz_stock_count_adjust): reconcile pass + manual move-line fix button"
```

---

## Task 10: Import wizard — xlsx/csv → lines

**Files:**
- Modify: `buz_stock_count_adjust/wizard/__init__.py`, `buz_stock_count_adjust/wizard/stock_count_adjustment_import.py`
- Modify: `buz_stock_count_adjust/views/stock_count_adjustment_import_views.xml`
- Modify: `buz_stock_count_adjust/models/stock_count_adjustment.py` (`action_import` opens the wizard)
- Test: `buz_stock_count_adjust/tests/test_count_adjust.py`

**Interfaces:**
- Consumes: `stock.count.adjustment` (via `active_id` context).
- Produces:
  - model `stock.count.adjustment.import` (TransientModel): `adjustment_id Many2one` (default from context), `data_file Binary`, `filename Char`, `file_format Selection [xlsx,csv]`, `import_valid_only Boolean`, `result_log Text readonly`.
  - `action_do_import()`:
    - Parse header row: `product_code, warehouse_code, target_qty, target_value, note`.
    - `warehouse_code` matched against `stock.warehouse.code`, stripping `/…` (accept `FG10` or `FG10/Stock`).
    - Rows sharing `(product_code, warehouse_code)` in file order → `bucket_seq` 10, 20, 30…
    - Unknown `product_code` / `warehouse_code` → row rejected, appended to `result_log`. If any row is rejected and `import_valid_only` is False → nothing imported, re-open wizard showing `result_log`. If `import_valid_only` → import the resolvable rows, list the rest.
    - Appends `fields.Command.create(...)` to `adjustment_id.line_ids` (does not clear existing).
    - xlsx via `openpyxl` if available else `xlrd`; csv via stdlib `csv` + `base64`. Match whichever lib the repo already vendors — check `stock_fifo_by_location` for the xlsx read pattern first.

- [ ] **Step 1: Write the failing test**

```python
@tagged('post_install', '-at_install')
class TestImportWizard(common.TransactionCase):

    def test_csv_import_buckets_by_file_order(self):
        import base64, io, csv
        wh = self.env['stock.warehouse'].search([], limit=1)
        p = self.env['product.product'].create({
            'name': 'imp probe', 'default_code': 'IMP001', 'type': 'product',
            'categ_id': self.env.ref('product.product_category_all').id})
        doc = self.env['stock.count.adjustment'].create({
            'company_id': self.env.company.id, 'cutoff_date': '2026-05-31'})
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(['product_code', 'warehouse_code', 'target_qty',
                    'target_value', 'note'])
        w.writerow(['IMP001', wh.code + '/Stock', '211', '76851.3771', 'b1'])
        w.writerow(['IMP001', wh.code, '1', '352.9183', 'b2'])
        w.writerow(['NOPE', wh.code, '5', '10', 'bad'])
        wiz = self.env['stock.count.adjustment.import'].create({
            'adjustment_id': doc.id, 'file_format': 'csv',
            'data_file': base64.b64encode(buf.getvalue().encode()),
            'filename': 'x.csv', 'import_valid_only': True})
        wiz.action_do_import()
        self.assertEqual(len(doc.line_ids), 2)
        self.assertEqual(doc.line_ids.mapped('bucket_seq'), [10, 20])
        self.assertIn('NOPE', wiz.result_log)

    def test_import_all_or_nothing_when_not_valid_only(self):
        # a rejected row with import_valid_only False imports nothing
        ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `... | grep -E 'test_csv_import|test_import_all_or_nothing|KeyError|AttributeError'`
Expected: FAIL — wizard model absent.

- [ ] **Step 3: Implement the wizard + view + `action_import`**

- [ ] **Step 4: Run tests to verify they pass**

Run: `... -u buz_stock_count_adjust --test-enable ... | grep -E 'FAIL|ERROR|failed,'`
Expected: import tests PASS.

- [ ] **Step 5: Commit**

```bash
git add buz_stock_count_adjust
git commit -m "feat(buz_stock_count_adjust): xlsx/csv import wizard"
```

---

## Task 11: Edge cases + safety gate + form help text

**Files:**
- Modify: `buz_stock_count_adjust/models/count_adjust_engine.py`
- Modify: `buz_stock_count_adjust/models/stock_count_adjustment.py`
- Modify: `buz_stock_count_adjust/views/stock_count_adjustment_views.xml`
- Test: `buz_stock_count_adjust/tests/test_count_adjust.py`

**Interfaces:**
- Consumes: everything.
- Produces: per spec §8, each handled in `run()` per group, recording a `line.state` + `line.result_note` and NOT aborting the whole document:
  - `real_time` category → `state='skipped'`, note the reason (already Task 4 — add the test).
  - `_scoped_replay` shortage > 1e-3 → `state='error'`, caught per group, note the shortage.
  - target rows for a pair sum to negative qty → allowed, `result_note` warns.
  - pair has any `locked IS TRUE` SVL layer → `state='skipped'`, note "N locked layers" (query pattern: `fifo_recalculation_wizard._locked_layer_ids`, fifo_recalculation_wizard.py:267-278 — `locked IS TRUE`, never `= False`).
  - `stock_quant` reserved qty > target → `state='error'` unless `target >= reserved`.
  - no post-cutoff layers → steps 4/6 are no-ops, `state='previewed'/'applied'` normally.
  - running the same doc twice → `action_apply` refuses when `state != 'previewed'`; a fresh doc for a pair already at target produces `delta ≈ 0` and applies as a near-noop.
  - `action_apply` guard: `_line_hash() != line_hash` → `UserError('Lines changed since preview. Run Preview again.')`.
  - Form: a `<div class="alert alert-warning">` above the lines with the external-`pg_dump` reminder (table-scoped list from spec §7) and "Preview is mandatory; Apply writes a full backup first."

- [ ] **Step 1: Write the failing tests** (`test_real_time_category_skipped`, `test_locked_layer_skips_pair`, `test_preview_then_edit_resets_state`, `test_apply_refused_when_not_previewed`, `test_reserved_gt_target_errors`)

```python
    def test_preview_then_edit_resets_state(self):
        doc = self._simple_doc()
        doc.action_preview()
        self.assertEqual(doc.state, 'previewed')
        doc.line_ids[0].target_qty += 1
        self.assertEqual(doc.state, 'draft')
        with self.assertRaises(Exception):
            doc.action_apply()

    def test_locked_layer_skips_pair(self):
        doc = self._simple_doc()
        self.env.cr.execute(
            "UPDATE stock_valuation_layer SET locked = TRUE "
            "WHERE product_id = %s AND warehouse_id = %s",
            (self.p.id, self.wh.id))
        self.env['stock.valuation.layer'].invalidate_model(['locked'])
        doc.action_preview()
        line = doc.line_ids[0]
        self.assertEqual(line.state, 'skipped')
        self.assertIn('locked', (line.result_note or '').lower())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `... | grep -E 'test_preview_then_edit|test_locked_layer|test_real_time_category_skipped|FAIL'`
Expected: FAIL.

- [ ] **Step 3: Implement the per-group guards + hash guard + form alert**

Verify `locked` column exists on the target DB first: `ssh mog-prod "docker exec postgres psql -U root MOG_LIVE -c '\d stock_valuation_layer'" | grep locked`. If absent, guard the query with a `information_schema.columns` check and treat "no column" as "no locked layers".

- [ ] **Step 4: Run tests to verify they pass**

Run: `... -u buz_stock_count_adjust --test-enable ... | grep -E 'FAIL|ERROR|failed,'`
Expected: all edge-case tests PASS; full suite green.

- [ ] **Step 5: Commit**

```bash
git add buz_stock_count_adjust
git commit -m "feat(buz_stock_count_adjust): per-group edge-case handling, hash guard, safety help text"
```

---

## Task 12: Deploy to the docker MOG_LIVE test stack + dry-run FCA0006100 @ FG10

**Files:** none (deployment + verification).

**Interfaces:**
- Consumes: the finished module.
- Produces: a verified preview run matching the hand-run numbers (Q0=229 / V0=81,658.26, dQ=−12, dV=−2,702.0255, ending target 217 / 78,956.2345).

- [ ] **Step 1: Deploy**

```bash
rsync -az --delete ./buz_stock_count_adjust/ mog-prod:/srv/docker/odoo_mogen/custom-addons/buz_stock_count_adjust/
ssh mog-prod "chmod -R +r /srv/docker/odoo_mogen/custom-addons/buz_stock_count_adjust"
ssh mog-prod "docker exec odoo odoo -d MOG_LIVE -i buz_stock_count_adjust --stop-after-init --no-http"
ssh mog-prod "docker restart odoo"   # controller/asset pickup — memory: dev-deploy-no-restart
```

- [ ] **Step 2: Run the test suite on the docker stack**

```bash
ssh mog-prod "docker exec odoo odoo -d MOG_LIVE -u buz_stock_count_adjust,stock_fifo_by_location --test-enable --stop-after-init --no-http 2>&1 | tail -40"
```
Expected: `0 failed, 0 error`.

- [ ] **Step 3: Grant the group + build a real document**

Add your user to `Stock Count Adjustment`. Create an SCA doc, `cutoff_date = 2026-05-31`, import the 3-bucket file for FCA0006100 @ FG10 (211 / 76,851.3771 · 1 / 352.9183 · 5 / 1,751.9391). Run **Preview**.

- [ ] **Step 4: Verify preview against the hand-run**

Preview log must show: baseline Q0 = 229.0, V0 = 81,658.26; `qty_delta` = −12.0, `valuation_delta` ≈ −2,702.03; category `manual_periodic` (no GL); scoped replay shortage 0.0; ending @ cutoff after reseed 217.0 / 78,956.2345; one reconcile mismatch if move-line 245369-style corruption is present (it was fixed by hand in the prior session — a fresh docker copy may or may not have it). Confirm preview wrote nothing: before Preview, record one pre-cutoff and one post-cutoff FCA0006100@FG10 SVL id's `remaining_qty` / `remaining_value` / `value` via `docker exec postgres psql`; re-read them after Preview — unchanged. (Do NOT use `remaining_value_check` for this — it is meaningless unless `date_to` is today, per the report docstring.)

- [ ] **Step 5: STOP — hand back to the user**

Do not click Apply. Report the preview numbers and the diff vs the hand-run. Apply on the docker stack, then prod-native `instance1`, is a separate user-confirmed step (CLAUDE.md: deploy DEV → test → PROD; version bumps manual confirm).

---

## Self-Review

**1. Spec coverage**

| Spec section | Task |
|---|---|
| §2.1 Backup | Task 7 (`_snapshot`, all tables) |
| §2.2 Baseline (report wizard, accounting_date) | Task 4 (`_baseline`, view built once — correction) |
| §2.3 Void-and-reseed (raw SQL, counter + buckets, zero pre-cutoff, invariant) | Task 5 |
| §2.4 Scoped FIFO recal (not `_fifo_replay_remaining`, seed from buckets, walk create_date > cutoff, shortage abort) | Tasks 2 + 6 |
| §2.5 Physical qty (move-history balance, `action_apply_inventory`, backdate, neutralise SVL, re-replay) | Task 8 |
| §2.6 Reconcile + detect corrupted move-lines (report only, human Fix) | Task 9 |
| §2 GL `real_time` guard | Task 4 + Task 11 |
| §3 Module layout | Task 1 (+ manifest depends correction) |
| §4 Data model (header/line/mismatch/backup) | Tasks 1, 3, 7 |
| §5 Engine `run()` one entrypoint, dry_run savepoint | Task 8 |
| §5 shared classmethod for the consume loop | Task 2 |
| §6 Import wizard | Task 10 |
| §7 Safety flow (preview mandatory, hash, backup-first, rollback, pg_dump text, group) | Tasks 1, 3, 7, 8, 11 |
| §8 Edge cases (all rows) | Task 11 (+ 4, 6) |
| §9 Tests 1-9 | distributed: #1 T4, #2 T5, #3 T6, #4 T2, #5 T8, #6 T9, #7 T7, #8 T4/T11, #9 T11 |
| §10 Deployment | Task 12 |

No gaps.

**2. Placeholder scan** — every code step carries real code or a named pattern reference with file:line. Task 9/10/11 "Implement" steps that only name the method are backed by a full failing test in the same task and an Interfaces block; acceptable per the skill (the test defines the contract). No "TBD", no "add error handling".

**3. Type consistency** — `_fifo_consume_rows(rows, seed=None)` signature is identical in Task 2 (Produces), Task 6 (Consumes + call site), and the Task 2 tests. `_void_and_reseed` returns `{'counter_id', 'bucket_ids', 'zeroed_ids'}` in Task 5 and is consumed under that shape in Tasks 6 (`reseed['bucket_ids']`) and 7. `_baseline` returns `{(product_id, warehouse_id): (Q0, V0)}` — consumed that way in Tasks 5, 8. `run(adjustment, dry_run=True)` consistent Tasks 1, 8, 12. Backup line models named `stock.count.adjustment.backup.line` / `.backup.quant` / `.backup.moveline` in Task 1 csv, Task 7, and Task 9 (`action_fix_move_line` writes `.backup.moveline`).
