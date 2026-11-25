from collections import defaultdict, namedtuple
from datetime import datetime, time, timedelta

import pytz

from odoo import fields, models
from odoo.exceptions import UserError
from odoo.tools import float_is_zero

QTY_DIGITS = 4
CHUNK = 5000
MAX_LOT_ROWS = 1500000  # guard: 'lotbal' rows ~ movements x open lots

# Lightweight valuation-layer row (plain tuple, no ORM): everything the engine needs,
# fetched in one SQL query instead of lazy per-record ORM reads.
Layer = namedtuple('Layer', 'id product_id wh_id quantity value doc move_id is_tr src_wh dst_wh parent_id')


class BuzPoLotWizard(models.TransientModel):
    _name = 'buz.po.lot.wizard'
    _description = 'Tax stock report wizard'

    date_from = fields.Date(required=True, default=lambda s: fields.Date.context_today(s).replace(month=1, day=1))
    date_to = fields.Date(required=True, default=fields.Date.context_today)
    company_id = fields.Many2one('res.company', required=True, default=lambda s: s.env.company)
    warehouse_ids = fields.Many2many('stock.warehouse', string='Warehouses',
                                     help='Empty = all warehouses.')
    product_ids = fields.Many2many('product.product', string='Products')
    code_prefix = fields.Char(string='Model starts with',
                              help='Product code prefix. Leave empty with no products chosen to '
                                   'list every product that has a balance in the period.')
    model_strip = fields.Integer(string='Strip trailing chars', default=3,
                                 help='Model = code minus last N chars (0 = full code).')
    cutoff_date = fields.Date(
        string='Layers from (override cutoff)',
        help='Empty = use the FIFO valuation cutoff (stock_fifo_valuation_report.cutoff_date). '
             'Set an earlier date to read older layers too, e.g. opening-balance (OB) '
             'documents, so lots trace back to their original receipt.')
    include_transit = fields.Boolean(
        string='Include transit warehouses', default=False,
        help='Off (default): warehouses whose stock location is a transit location '
             '(goods in transit) are left out, so balances match on-hand stock. '
             'Ignored when specific warehouses are chosen.')
    show_lots_each_row = fields.Boolean(string='Show FIFO lots under every movement', default=True,
                                        help='Off = lots only at period end (smaller file).')
    hide_zero = fields.Boolean(string='Hide products with zero stock at end date', default=True)
    line_ids = fields.One2many('buz.po.lot.line', 'wizard_id')

    # ------------------------------------------------------------ helpers
    def _utc_bounds(self):
        tz = pytz.timezone(self.env.user.tz or 'Asia/Bangkok')

        def to_utc(d):
            return tz.localize(datetime.combine(d, time.min)).astimezone(pytz.UTC).replace(tzinfo=None)

        return to_utc(self.date_from), to_utc(self.date_to + timedelta(days=1))

    @staticmethod
    def _bangkok_start_utc(day):
        return datetime.combine(day, time.min) - timedelta(hours=7)

    def _report_wh_ids(self):
        """Warehouse ids the report covers; empty set = every warehouse."""
        if self.warehouse_ids:
            return set(self.warehouse_ids.ids)
        if self.include_transit:
            return set()
        Wh = self.env['stock.warehouse'].with_context(active_test=False)
        whs = Wh.search([('company_id', '=', self.company_id.id)])
        keep = whs.filtered(lambda w: w.lot_stock_id.usage != 'transit')
        return set(keep.ids) if len(keep) < len(whs) else set()

    def _model_code(self, code):
        code = code or ''
        n = self.model_strip or 0
        return code[:-n] if n and len(code) > n else code

    def _cutoff_utc(self):
        if self.cutoff_date:
            return self._bangkok_start_utc(self.cutoff_date)
        cutoff = self.env['ir.config_parameter'].sudo().get_param(
            'stock_fifo_valuation_report.cutoff_date')
        return self._bangkok_start_utc(fields.Date.to_date(cutoff)) if cutoff else datetime.min

    def _fetch_layers(self, product_ids, cutoff_utc, end_utc):
        """{product_id: [(date, id, Layer)]} sorted by (date, id); one SQL query.

        Same scope as stock_fifo_valuation_report: no layers before its cutoff,
        none without a warehouse, none of cancelled moves or their
        'Reverse cancelled' neutralising layers. All warehouses (the origin
        tracing needs the source warehouse legs)."""
        if not product_ids:
            return {}
        cr = self.env.cr
        cr.execute("""
            SELECT l.id, l.product_id, COALESCE(l.warehouse_id, pl.warehouse_id), l.quantity, l.value,
                   COALESCE(l.accounting_date, l.create_date) AS d,
                   CASE WHEN l.quantity = 0 AND l.value <> 0
                             AND l.stock_valuation_layer_id IS NOT NULL
                             AND NULLIF(l.description, '') IS NOT NULL
                        -- landed cost / revaluation: show its own bill, not the parent receipt
                        THEN l.description || COALESCE(' (ลงล็อต ' || COALESCE(
                                 NULLIF(p.name, ''), NULLIF(m.reference, ''), NULLIF(m.name, '')) || ')', '')
                        ELSE COALESCE(NULLIF(p.name, ''), NULLIF(m.reference, ''),
                                      NULLIF(m.name, ''), NULLIF(l.description, ''), '')
                   END AS doc,
                   CASE WHEN l.quantity = 0 AND l.value <> 0
                             AND l.stock_valuation_layer_id IS NOT NULL
                             AND NULLIF(l.description, '') IS NOT NULL
                        THEN COALESCE(NULLIF(p.name, ''), NULLIF(m.reference, ''), NULLIF(m.name, ''))
                   END AS lcdoc,
                   m.id,
                   (m.id IS NOT NULL AND ls.usage IN ('internal', 'transit')
                        AND ld.usage IN ('internal', 'transit')) AS is_tr,
                   ls.warehouse_id, ld.warehouse_id, l.stock_valuation_layer_id
              FROM stock_valuation_layer l
              LEFT JOIN stock_valuation_layer pl ON pl.id = l.stock_valuation_layer_id
              LEFT JOIN stock_move m ON m.id = l.stock_move_id
              LEFT JOIN stock_picking p ON p.id = m.picking_id
              LEFT JOIN stock_location ls ON ls.id = m.location_id
              LEFT JOIN stock_location ld ON ld.id = m.location_dest_id
             WHERE l.company_id = %s
               AND l.product_id = ANY(%s)
               AND COALESCE(l.warehouse_id, pl.warehouse_id) IS NOT NULL
               -- warehouse-less value-only layers (landed cost / revaluation) belong
               -- to the warehouse of the layer they hang off
               AND (l.warehouse_id IS NOT NULL OR l.quantity = 0)
               AND (m.id IS NULL OR m.state != 'cancel')
               AND COALESCE(l.description, '') NOT LIKE 'Reverse cancelled%%'
               AND COALESCE(l.accounting_date, l.create_date) >= %s
               AND COALESCE(l.accounting_date, l.create_date) < %s
             ORDER BY COALESCE(l.accounting_date, l.create_date), l.id
        """, (self.company_id.id, list(product_ids), cutoff_utc, end_utc))
        by_prod = defaultdict(list)
        lcdoc = {}
        for (lid, pid, wh, q, v, d, doc, lcd, mid, tr, swh, dwh, par) in cr.fetchall():
            by_prod[pid].append((d, lid, Layer(lid, pid, wh, q or 0.0, v or 0.0, doc,
                                               mid, bool(tr), swh, dwh, par)))
            if lcd:
                lcdoc[lid] = lcd
        tz = pytz.timezone(self.env.user.tz or 'Asia/Bangkok')
        return {pid: self._group_landed(self._landed_after_parent(lst), lcdoc, tz)
                for pid, lst in by_prod.items()}

    @staticmethod
    def _group_landed(items, lcdoc, tz):
        """Merge value-only layers (landed cost / revaluation) that hang off the
        same layer, in the same warehouse, on the same local accounting date into
        one row (value summed, kept at the position of the first one). {layer id:
        receipt name} in `lcdoc` marks which layers are value-only."""
        out, first = [], {}
        for d, lid, sv in items:
            if lid not in lcdoc:
                out.append((d, lid, sv))
                continue
            day = pytz.UTC.localize(d).astimezone(tz).date()
            key = (sv.parent_id, sv.wh_id, day)
            if key in first:
                grp = first[key]
                grp['n'] += 1
                grp['value'] += sv.value
            else:
                grp = first[key] = {'n': 1, 'value': sv.value, 'idx': len(out)}
                out.append((d, lid, sv))
        for key, grp in first.items():
            if grp['n'] > 1:
                d, lid, sv = out[grp['idx']]
                out[grp['idx']] = (d, lid, sv._replace(
                    value=round(grp['value'], 2),
                    doc='ค่าใช้จ่ายนำเข้า %d รายการ (ลงล็อต %s)' % (grp['n'], lcdoc[lid])))
        return out

    @staticmethod
    def _landed_after_parent(items):
        """Re-sequence [(date, id, Layer)]: a value-only layer (landed cost /
        revaluation, qty 0) whose accounting date is earlier than the layer it
        hangs off is moved to sit right after that parent. Its own date is kept.
        Otherwise the cost shows up (qty 0) before the stock it belongs to
        arrives and the running balance reads "0 qty, value > 0"."""
        dates = {t[1]: t[0] for t in items}
        keyed = []
        for d, lid, sv in items:
            pd = dates.get(sv.parent_id)
            if sv.quantity == 0 and sv.value and pd is not None and pd > d:
                keyed.append(((pd, sv.parent_id, 1, lid), (d, lid, sv)))
            else:
                keyed.append(((d, lid, 0, lid), (d, lid, sv)))
        keyed.sort(key=lambda k: k[0])
        return [t for _k, t in keyed]

    def _balance_product_ids(self, end_utc):
        """Products with non-zero qty (in any warehouse) at date_to (same layer scope as the
        engine); with hide_zero off also products with any layer in the window."""
        cutoff_utc = self._cutoff_utc()
        dom = [('company_id', '=', self.company_id.id),
               ('warehouse_id', '!=', False),
               ('stock_move_id.state', '!=', 'cancel'),
               ('description', 'not like', 'Reverse cancelled%'),
               '|', '&', ('accounting_date', '!=', False),
                    '&', ('accounting_date', '>=', cutoff_utc), ('accounting_date', '<', end_utc),
               '&', ('accounting_date', '=', False),
                    '&', ('create_date', '>=', cutoff_utc), ('create_date', '<', end_utc)]
        wh_ids = self._report_wh_ids()
        if wh_ids:
            dom.append(('warehouse_id', 'in', list(wh_ids)))
        groups = self.env['stock.valuation.layer'].sudo().read_group(
            dom, ['quantity:sum'], ['product_id', 'warehouse_id'], lazy=False)
        ids = set()
        for g in groups:
            if not g['product_id']:
                continue
            if not self.hide_zero or \
                    not float_is_zero(g['quantity'], precision_digits=QTY_DIGITS):
                ids.add(g['product_id'][0])
        return list(ids)

    # ------------------------------------------------------------- engine
    def _compute_rows(self):
        return [r for rows in self._iter_rows() for r in rows]

    def _iter_rows(self):
        """Yield the row list of one product at a time (keeps memory flat)."""
        self.ensure_one()
        start_utc, end_utc = self._utc_bounds()
        Product = self.env['product.product']
        pdom = [('default_code', '!=', False)]
        if self.product_ids:
            pdom = [('id', 'in', self.product_ids.ids)]
        elif self.code_prefix:
            pdom = [('default_code', '=like', self.code_prefix + '%')]
        else:
            # No product filter: only products with a balance (or, when
            # "hide" is off, any movement) in the selected period.
            pdom = [('id', 'in', self._balance_product_ids(end_utc))]
        products = Product.with_context(active_test=False).search(pdom)
        cutoff_utc = self._cutoff_utc()
        all_layers = self._fetch_layers(products.ids, cutoff_utc, end_utc)
        whs = self._report_wh_ids()
        by_prod = {pid: ([t for t in lst if t[2].wh_id in whs] if whs else lst)
                   for pid, lst in all_layers.items()}
        for prod in products.sorted(lambda p: (self._model_code(p.default_code), p.default_code or '')):
            items = by_prod.pop(prod.id, [])  # already sorted (date, id) by SQL
            seq_all = all_layers.pop(prod.id, [])
            rows = self._product_rows(prod, items, start_utc, cutoff_utc, end_utc, seq_all)
            if rows:
                yield rows

    def _product_rows(self, prod, items, start_utc, cutoff_utc=None, end_utc=None, seq_all=None,
                      trace=None):
        """Ledger rows for one product: FIFO audit.

        FIFO is per warehouse (stock_fifo_by_location), so every warehouse has its
        own queue of lots. A lot is identified by its ORIGIN document (PO receipt,
        MO production, opening ...): a transfer out eats the source warehouse's
        oldest lots, and the transfer in opens lots in the destination warehouse
        that keep those origin documents. `seq_all` = all warehouses' layers of the
        product (needed to trace origins when a warehouse filter is set); `items`
        = the layers that belong in the report (selected warehouses).
        After every movement the remaining lots of the selected warehouses are
        emitted as 'lotbal' rows (when show_lots_each_row)."""
        tz = pytz.timezone(self.env.user.tz or 'Asia/Bangkok')

        def loc_date(d):
            return pytz.UTC.localize(d).astimezone(tz).date()

        seq_all = items if seq_all is None else seq_all
        in_report = {t[1] for t in items}
        sel = self._report_wh_ids()
        wh_names = {w.id: w.name for w in self.env['stock.warehouse'].with_context(
            active_test=False).search([])}
        base = {'wizard_id': self.id, 'product_id': prod.id,
                'model_code': self._model_code(prod.default_code)}
        seq = 0
        out = []

        queues = defaultdict(list)    # wh id -> [[doc, date, unit, remaining, received, layer id]]
        pieces = defaultdict(list)    # move id -> [[doc, date, qty]] eaten at the source
        done = set()
        outs_by_move = defaultdict(list)
        for d, _i, sv in seq_all:
            if sv.quantity < 0 and sv.is_tr:
                outs_by_move[sv.move_id].append((d, sv))

        # transfer: show the out leg before its in leg (same day), so the lot
        # rows under the in leg match the balance printed on it
        emitted, ordered = set(), []
        for d, i, sv in seq_all:
            if i in emitted:
                continue
            if sv.is_tr and sv.quantity > 0 and sv.move_id:
                for od, osv in outs_by_move.get(sv.move_id, []):
                    if osv.id not in emitted and loc_date(od) == loc_date(d):
                        ordered.append((od, osv.id, osv))
                        emitted.add(osv.id)
            ordered.append((d, i, sv))
            emitted.add(i)
        seq_all = ordered

        def consume(d, sv):
            done.add(sv.id)
            q = queues[sv.wh_id]
            rem = -sv.quantity
            got = []
            for lot in q:
                if rem <= 1e-9:
                    break
                take = min(lot[3], rem)
                if take <= 1e-9:
                    continue
                lot[3] -= take
                rem -= take
                got.append([lot[0], lot[1], take, lot[5], lot[2]])
            while q and q[0][3] <= 1e-9:
                q.pop(0)  # exhausted lots are always a prefix
            if rem > 1e-9:
                # shortfall (negative stock)
                got.append([sv.doc, loc_date(d), rem, {sv.id}, abs(sv.value / sv.quantity)])
            if trace is not None:
                trace['out'][sv.id] = [(g[0], g[1], g[4], g[2]) for g in got]
            return got

        seen = set()      # layer ids already applied
        pending = defaultdict(float)  # parent layer id -> value booked before the lot exists

        def flush_pending(sv):
            """Back-dated landed cost whose parent lot arrived later: add it now."""
            val = pending.pop(sv.id, 0.0)
            if val:
                hit = [lot for lot in queues[sv.wh_id] if sv.id in lot[5]]
                rec = sum(lot[4] for lot in hit)
                for lot in hit:
                    if rec:
                        lot[2] += val / rec

        def apply(d, sv):
            seen.add(sv.id)
            q = sv.quantity
            if q < 0:
                if sv.id in done:
                    return
                got = consume(d, sv)
                if sv.is_tr:
                    pieces[sv.move_id] += got
            elif q == 0 and sv.parent_id and sv.value:
                # landed cost / revaluation: spread over the lot it hangs off
                # (lot[5] = ids of every layer the lot passed through, so the
                # parent is still found after the lot moved between warehouses)
                hit = [lot for lot in queues[sv.wh_id] if sv.parent_id in lot[5]]
                rec = sum(lot[4] for lot in hit)
                if rec:
                    for lot in hit:
                        lot[2] += sv.value / rec
                elif sv.parent_id not in seen:
                    # booked (back-dated) before its parent lot exists: wait for it
                    pending[sv.parent_id] += sv.value
                else:
                    # parent lot already used up: spread over what is left in
                    # the warehouse so lots keep adding up to the ledger balance
                    left = [lot for lot in queues[sv.wh_id] if lot[3] > 1e-9]
                    rem_q = sum(lot[3] for lot in left)
                    for lot in left:
                        lot[2] += sv.value / rem_q
            elif q > 0:
                unit = sv.value / q
                if not sv.is_tr:
                    queues[sv.wh_id].append([sv.doc, loc_date(d), unit, q, q, {sv.id}])
                    if trace is not None:
                        trace['in'][sv.id] = [(sv.doc, loc_date(d), unit, q)]
                    flush_pending(sv)
                    return
                mid = sv.move_id
                for od, osv in outs_by_move.get(mid, []):
                    if osv.id not in done:
                        pieces[mid] += consume(od, osv)
                need = q
                tin = []
                while need > 1e-9 and pieces[mid]:
                    pc = pieces[mid][0]
                    take = min(pc[2], need)
                    queues[sv.wh_id].append([pc[0], pc[1], unit, take, take, pc[3] | {sv.id}])
                    tin.append((pc[0], pc[1], unit, take))
                    pc[2] -= take
                    need -= take
                    if pc[2] <= 1e-9:
                        pieces[mid].pop(0)
                if need > 1e-9:
                    queues[sv.wh_id].append([sv.doc, loc_date(d), unit, need, need, {sv.id}])
                    tin.append((sv.doc, loc_date(d), unit, need))
                if trace is not None:
                    trace['in'][sv.id] = tin
                flush_pending(sv)

        def live_lots():
            """Remaining lots of the selected warehouses, one row per
            (origin doc, warehouse, date, unit cost); [(date, wh, [doc, date, unit, rem, rec])]."""
            merged = {}
            for wh, q in queues.items():
                if sel and wh not in sel:
                    continue
                for lot in q:
                    if float_is_zero(lot[3], precision_digits=QTY_DIGITS):
                        continue
                    key = (lot[1], wh or 0, lot[0], round(lot[2], 4))
                    m = merged.get(key)
                    if m:
                        m[3] += lot[3]
                        m[4] += lot[4]
                    else:
                        merged[key] = [lot[0], lot[1], lot[2], lot[3], lot[4]]
            return [(k[0], k[1], v) for k, v in sorted(merged.items(), key=lambda kv: kv[0][:2] + (kv[0][2],))]

        def wtag(wh):
            return ' · %s' % wh_names[wh] if wh in wh_names else ''

        def row(**kw):
            nonlocal seq
            seq += 1
            r = dict(base, seq=seq)
            r.update(kw)
            out.append(r)

        def snapshot():
            for ldate, wh, lot in live_lots():
                row(line_type='lotbal', date=ldate, doc_ref=lot[0] + wtag(wh),
                    warehouse_id=wh or False, bal_qty=lot[3], bal_cost=lot[2],
                    bal_value=lot[3] * lot[2])

        bq = bv = 0.0
        opened = False
        tin_q = tin_v = tout_q = tout_v = 0.0
        window_any = any(t[0] >= start_utc for t in items)
        for d, _i, s in seq_all:
            if d >= start_utc and not opened:
                opened = True
                if not window_any and float_is_zero(bq, precision_digits=QTY_DIGITS) \
                        and float_is_zero(bv, precision_digits=2) and self.hide_zero:
                    return []
                row(line_type='opening', doc_ref='ยกมา', date=self.date_from,
                    bal_qty=bq, bal_value=bv, bal_cost=(bv / bq) if bq else 0.0)
                if trace is not None:
                    trace['opening'] = live_lots()
                    trace['open_bal'] = {k: list(v) for k, v in trace['bal'].items()}
                if self.show_lots_each_row:
                    snapshot()
            apply(d, s)
            if s.id not in in_report:
                continue
            q, v = s.quantity, s.value
            bq += q
            bv += v
            if trace is not None:
                wb = trace['bal'].setdefault(s.wh_id, [0.0, 0.0])
                wb[0] += q
                wb[1] += v
            if d < start_utc:
                continue
            vals = {'line_type': 'move', 'date': loc_date(d),
                    'warehouse_id': s.wh_id or False, 'doc_ref': s.doc + wtag(s.wh_id),
                    'bal_qty': bq, 'bal_value': bv,
                    'bal_cost': (bv / bq) if bq else 0.0}
            if q > 0 or (q == 0 and v >= 0):
                vals.update(in_qty=q, in_value=v, in_cost=(v / q) if q else 0.0)
                tin_q += q
                tin_v += v
            else:
                vals.update(out_qty=(-q) or 0.0, out_value=(-v) or 0.0, out_cost=(v / q) if q else 0.0)
                tout_q += -q
                tout_v += -v
            row(**vals)
            if trace is not None:
                trace['layers'].append((s.id, s.move_id, s.wh_id, q, v))
            if self.show_lots_each_row:
                snapshot()
        if not opened:
            if self.hide_zero and float_is_zero(bq, precision_digits=QTY_DIGITS):
                return []
            row(line_type='opening', doc_ref='ยกมา', date=self.date_from,
                bal_qty=bq, bal_value=bv, bal_cost=(bv / bq) if bq else 0.0)
            if trace is not None:
                trace['opening'] = live_lots()
                trace['open_bal'] = {k: list(v) for k, v in trace['bal'].items()}
        if self.hide_zero and float_is_zero(bq, precision_digits=QTY_DIGITS):
            return []  # nothing in stock at date_to
        if trace is not None:
            trace['ending'] = live_lots()
        lot_val = lot_q = 0.0
        for ldate, wh, lot in live_lots():
            lot_q += lot[3]
            lot_val += lot[3] * lot[2]
            row(line_type='lot', date=ldate, doc_ref=lot[0] + wtag(wh),
                warehouse_id=wh or False, in_qty=lot[4], in_cost=lot[2],
                in_value=lot[4] * lot[2], bal_qty=lot[3], bal_cost=lot[2],
                bal_value=lot[3] * lot[2])
        if not float_is_zero(bq - lot_q, precision_digits=QTY_DIGITS):
            row(line_type='lot', doc_ref='ไม่สามารถอ้างอิงล็อตได้',
                bal_qty=bq - lot_q, bal_cost=0.0, bal_value=0.0)
        diff = bv - lot_val
        if abs(diff) >= 0.01:
            row(line_type='adjust', doc_ref='ปรับมูลค่า (ต่างจากล็อต)', bal_value=diff)
        row(line_type='total', doc_ref='รวม', in_qty=tin_q, in_value=tin_v,
            out_qty=tout_q, out_value=tout_v, bal_qty=bq, bal_value=bv,
            bal_cost=(bv / bq) if bq else 0.0)
        return out

    # ----------------------------------------------------------- actions
    def _refresh(self):
        Line = self.env['buz.po.lot.line']
        self.env.cr.execute('DELETE FROM buz_po_lot_line WHERE wizard_id = %s', (self.id,))
        Line.invalidate_model()
        self.invalidate_recordset(['line_ids'])
        buf, total, lotbal = [], 0, 0
        for rows in self._iter_rows():
            buf += rows
            total += len(rows)
            lotbal += sum(1 for r in rows if r['line_type'] == 'lotbal')
            if lotbal > MAX_LOT_ROWS:
                raise UserError(
                    'Too many lot rows (> %d). Narrow the products/warehouses/dates or '
                    'untick "Show FIFO lots under every movement".' % MAX_LOT_ROWS)
            if len(buf) >= CHUNK:
                self._insert_lines(buf)
                buf = []
        if buf:
            self._insert_lines(buf)
        if not total:
            raise UserError('No data for the selected filters.')

    LINE_COLS = ('product_id', 'model_code', 'seq', 'line_type', 'date', 'doc_ref',
                 'warehouse_id', 'in_qty', 'in_cost', 'in_value', 'out_qty', 'out_cost',
                 'out_value', 'bal_qty', 'bal_cost', 'bal_value')

    def _insert_lines(self, rows):
        """Bulk insert report lines with plain SQL (transient data, no ORM
        create overhead: no computes, no access checks, no cache)."""
        from psycopg2.extras import execute_values
        cols = self.LINE_COLS
        uid = self.env.uid
        sql = ('INSERT INTO buz_po_lot_line (wizard_id, create_uid, write_uid, '
               'create_date, write_date, %s) VALUES %%s' % ', '.join(cols))
        tmpl = '(%s, %s, %s, now() at time zone \'UTC\', now() at time zone \'UTC\', ' % (
            '%s', '%s', '%s') + ', '.join(['%s'] * len(cols)) + ')'
        cr = self.env.cr
        for i in range(0, len(rows), CHUNK):
            execute_values(cr._obj, sql, [
                (self.id, uid, uid) + tuple(r.get(c) for c in cols)
                for r in rows[i:i + CHUNK]], template=tmpl, page_size=CHUNK)
        self.env['buz.po.lot.line'].invalidate_model()
        self.invalidate_recordset(['line_ids'])

    def action_compute(self):
        self.ensure_one()
        self._refresh()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Tax Stock Report',
            'res_model': 'buz.po.lot.line',
            'view_mode': 'tree',
            'domain': [('wizard_id', '=', self.id)],
        }

    def action_export_xlsx(self):
        self.ensure_one()
        self._refresh()
        return self.env.ref('buz_stock_po_lot_report.action_po_lot_xlsx').report_action(self)
