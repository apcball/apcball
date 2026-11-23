from collections import defaultdict, namedtuple
from datetime import datetime, time, timedelta

import pytz

from odoo import fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_is_zero

QTY_DIGITS = 4
CHUNK = 5000

# Lightweight valuation-layer row (plain tuple, no ORM): everything the engine needs,
# fetched in one SQL query instead of lazy per-record ORM reads.
Layer = namedtuple('Layer', 'id product_id wh_id quantity value doc move_id is_tr src_wh dst_wh')


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

    def _model_code(self, code):
        code = code or ''
        n = self.model_strip or 0
        return code[:-n] if n and len(code) > n else code

    def _is_transfer(self, svl):
        """Internal/inter-warehouse transfer: not a real stock in/out.

        With a warehouse filter, a leg whose counterpart is outside the
        selected warehouses is a real in/out and is kept."""
        if not svl.is_tr:
            return False
        if self.warehouse_ids:
            whs = set(self.warehouse_ids.ids)
            return bool(svl.src_wh and svl.dst_wh and svl.src_wh in whs and svl.dst_wh in whs)
        return True

    def _cutoff_utc(self):
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
            SELECT l.id, l.product_id, l.warehouse_id, l.quantity, l.value,
                   COALESCE(l.accounting_date, l.create_date) AS d,
                   COALESCE(NULLIF(p.name, ''), NULLIF(m.reference, ''),
                            NULLIF(m.name, ''), NULLIF(l.description, ''), '') AS doc,
                   m.id,
                   (m.id IS NOT NULL AND ls.usage IN ('internal', 'transit')
                        AND ld.usage IN ('internal', 'transit')) AS is_tr,
                   ls.warehouse_id, ld.warehouse_id
              FROM stock_valuation_layer l
              LEFT JOIN stock_move m ON m.id = l.stock_move_id
              LEFT JOIN stock_picking p ON p.id = m.picking_id
              LEFT JOIN stock_location ls ON ls.id = m.location_id
              LEFT JOIN stock_location ld ON ld.id = m.location_dest_id
             WHERE l.company_id = %s
               AND l.product_id = ANY(%s)
               AND l.warehouse_id IS NOT NULL
               AND (m.id IS NULL OR m.state != 'cancel')
               AND COALESCE(l.description, '') NOT LIKE 'Reverse cancelled%%'
               AND COALESCE(l.accounting_date, l.create_date) >= %s
               AND COALESCE(l.accounting_date, l.create_date) < %s
             ORDER BY COALESCE(l.accounting_date, l.create_date), l.id
        """, (self.company_id.id, list(product_ids), cutoff_utc, end_utc))
        by_prod = defaultdict(list)
        for (lid, pid, wh, q, v, d, doc, mid, tr, swh, dwh) in cr.fetchall():
            by_prod[pid].append((d, lid, Layer(lid, pid, wh, q or 0.0, v or 0.0, doc,
                                               mid, bool(tr), swh, dwh)))
        return by_prod

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
        if self.warehouse_ids:
            dom.append(('warehouse_id', 'in', self.warehouse_ids.ids))
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

    def _origin_labels(self, items, seq, end_utc):
        """{svl_id: (label, date)} for transfer-in layers: trace the FIFO lots the
        transfer consumed in the source warehouse back to the real receipt
        document (PO receipt, opening balance, ...). Label keeps the transfer
        reference in brackets. `items` = this report's layers, `seq` = all
        warehouses' layers of the product ([(date, id, Layer)] sorted)."""
        if not any(t[2].quantity > 0 and t[2].is_tr for t in items) or end_utc is None:
            return {}
        outs_by_move = defaultdict(list)
        for d, _i, sv in seq:
            if sv.quantity < 0 and sv.is_tr:
                outs_by_move[sv.move_id].append((d, sv))
        queues = defaultdict(list)    # warehouse id -> [[doc, date, remaining]]
        pieces = defaultdict(list)    # move id -> [[doc, date, qty]] consumed at source
        done = set()

        def consume(d, sv):
            done.add(sv.id)
            rem = -sv.quantity
            got = []
            for lot in queues[sv.wh_id]:
                if rem <= 1e-9:
                    break
                if lot[2] <= 1e-9:
                    continue
                take = min(lot[2], rem)
                lot[2] -= take
                rem -= take
                got.append([lot[0], lot[1], take])
            if rem > 1e-9:
                got.append([sv.doc, d, rem])
            return got

        labels = {}
        for d, _i, sv in seq:
            q = sv.quantity
            own = sv.doc
            wh = sv.wh_id
            if q < 0:
                if sv.id in done:
                    continue
                got = consume(d, sv)
                if sv.is_tr:
                    pieces[sv.move_id] += got
            elif q > 0 and sv.is_tr:
                mid = sv.move_id
                for od, osv in outs_by_move.get(mid, []):
                    if osv.id not in done:
                        pieces[mid] += consume(od, osv)
                need, mine = q, []
                while need > 1e-9 and pieces[mid]:
                    pc = pieces[mid][0]
                    take = min(pc[2], need)
                    mine.append([pc[0], pc[1], take])
                    pc[2] -= take
                    need -= take
                    if pc[2] <= 1e-9:
                        pieces[mid].pop(0)
                if need > 1e-9:
                    mine.append([own, d, need])
                queues[wh] += [list(m) for m in mine]
                docs = []
                for m in mine:
                    if m[0] not in docs:
                        docs.append(m[0])
                label = ', '.join(docs)
                if own not in docs:
                    label += ' (โอน %s)' % own
                labels[sv.id] = (label, mine[0][1])
            elif q > 0:
                queues[wh].append([own, d, q])
        return labels

    # ------------------------------------------------------------- engine
    def _compute_rows(self):
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
        whs = set(self.warehouse_ids.ids)
        by_prod = {pid: ([t for t in lst if t[2].wh_id in whs] if whs else lst)
                   for pid, lst in all_layers.items()}
        rows = []
        for prod in products.sorted(lambda p: (self._model_code(p.default_code), p.default_code or '')):
            items = by_prod.get(prod.id, [])  # already sorted (date, id) by SQL
            rows += self._product_rows(prod, items, start_utc, cutoff_utc, end_utc,
                                       all_layers.get(prod.id, []))
        return rows

    def _product_rows(self, prod, items, start_utc, cutoff_utc=None, end_utc=None, seq_all=None):
        tz = pytz.timezone(self.env.user.tz or 'Asia/Bangkok')

        def loc_date(d):
            return pytz.UTC.localize(d).astimezone(tz).date()

        origins = self._origin_labels(items, items if seq_all is None else seq_all, end_utc)
        base = {'wizard_id': self.id, 'product_id': prod.id,
                'model_code': self._model_code(prod.default_code)}
        seq = 0
        out = []
        o_qty = sum(s.quantity for d, _i, s in items if d < start_utc)
        o_val = sum(s.value for d, _i, s in items if d < start_utc)
        window = [t for t in items if t[0] >= start_utc]
        if not window and float_is_zero(o_qty, precision_digits=QTY_DIGITS) \
                and float_is_zero(o_val, precision_digits=2) and self.hide_zero:
            return []

        def row(**kw):
            nonlocal seq
            seq += 1
            r = dict(base, seq=seq)
            r.update(kw)
            out.append(r)

        bq, bv = o_qty, o_val
        row(line_type='opening', doc_ref='ยกมา', date=self.date_from,
            bal_qty=bq, bal_value=bv, bal_cost=(bv / bq) if bq else 0.0)
        tin_q = tin_v = tout_q = tout_v = 0.0
        net_q = net_v = 0.0
        for d, _i, s in window:
            q, v = s.quantity, s.value
            if self._is_transfer(s):
                net_q += q
                net_v += v
                continue
            bq += q
            bv += v
            vals = {'line_type': 'move', 'date': loc_date(d),
                    'warehouse_id': s.wh_id or False,
                    'bal_qty': bq, 'bal_value': bv,
                    'bal_cost': (bv / bq) if bq else 0.0}
            vals['doc_ref'] = s.doc
            if q > 0 and s.id in origins:
                vals['doc_ref'] = origins[s.id][0]
            if q > 0 or (q == 0 and v >= 0):
                vals.update(in_qty=q, in_value=v, in_cost=(v / q) if q else 0.0)
                tin_q += q
                tin_v += v
            else:
                vals.update(out_qty=-q, out_value=-v, out_cost=(v / q) if q else 0.0)
                tout_q += -q
                tout_v += -v
            row(**vals)
        if not float_is_zero(net_q, precision_digits=QTY_DIGITS) or abs(net_v) >= 0.01:
            # transfers net to ~0; show only a residual so the ledger still ties
            bq += net_q
            bv += net_v
            vals = {'line_type': 'move', 'date': self.date_to,
                    'doc_ref': 'โอนระหว่างคลัง (สุทธิ)',
                    'bal_qty': bq, 'bal_value': bv,
                    'bal_cost': (bv / bq) if bq else 0.0}
            if net_q > 0 or (net_q == 0 and net_v >= 0):
                vals.update(in_qty=net_q, in_value=net_v,
                            in_cost=(net_v / net_q) if net_q else 0.0)
                tin_q += net_q
                tin_v += net_v
            else:
                vals.update(out_qty=-net_q, out_value=-net_v,
                            out_cost=(net_v / net_q) if net_q else 0.0)
                tout_q += -net_q
                tout_v += -net_v
            row(**vals)
        row(line_type='total', doc_ref='รวม', in_qty=tin_q, in_value=tin_v,
            out_qty=tout_q, out_value=tout_v, bal_qty=bq, bal_value=bv,
            bal_cost=(bv / bq) if bq else 0.0)
        # ---- ending lots: FIFO queue is per warehouse (stock_fifo_by_location),
        # so replay each warehouse separately, transfer legs included.
        by_wh = defaultdict(list)
        for t in items:
            by_wh[t[2].wh_id].append(t)
        if self.hide_zero and all(
                float_is_zero(sum(t[2].quantity for t in w), precision_digits=QTY_DIGITS)
                for w in by_wh.values()):
            return []  # nothing in stock at date_to in any warehouse
        lot_val = 0.0
        wh_names = {w.id: w.name for w in self.env['stock.warehouse'].with_context(
            active_test=False).browse([w for w in by_wh if w])}
        for wh, wh_items in sorted(by_wh.items(), key=lambda kv: kv[0] or 0):
            wh_q = sum(t[2].quantity for t in wh_items)
            lots = []
            for d, _i, sv in wh_items:
                q = sv.quantity
                if q > 0:
                    lots.append([d, sv, sv.value / q, q, q])  # [date, svl, unit, remaining, received]
                elif q < 0:
                    rem = -q
                    for lot in lots:
                        if rem <= 0:
                            break
                        take = min(lot[3], rem)
                        lot[3] -= take
                        rem -= take
            alloc = sum(l[3] for l in lots)
            if float_compare(alloc, wh_q, precision_digits=QTY_DIGITS) > 0:
                excess = alloc - wh_q
                for lot in lots:
                    if excess <= 0:
                        break
                    take = min(lot[3], excess)
                    lot[3] -= take
                    excess -= take
            alloc = sum(l[3] for l in lots)  # after trimming
            merged = {}
            for d, sv, unit, remq, recq in lots:
                if float_is_zero(remq, precision_digits=QTY_DIGITS):
                    continue
                doc = sv.doc
                ldate = loc_date(d)
                if sv.id in origins:
                    doc, od = origins[sv.id]
                    ldate = loc_date(od)
                key = (ldate, doc, round(unit, 4))
                if key in merged:
                    merged[key][0] += remq
                    merged[key][2] += recq
                else:
                    merged[key] = [remq, unit, recq]
            wh_tag = ' · %s' % wh_names[wh] if wh else ''
            for (ldate, doc, _u), (remq, unit, recq) in sorted(merged.items(), key=lambda kv: kv[0][0]):
                val = remq * unit
                lot_val += val
                row(line_type='lot', date=ldate, doc_ref=doc + wh_tag,
                    warehouse_id=wh or False,
                    in_qty=recq, in_cost=unit, in_value=recq * unit,
                    bal_qty=remq, bal_cost=unit, bal_value=val)
            if not float_is_zero(wh_q - alloc, precision_digits=QTY_DIGITS):
                row(line_type='lot', doc_ref='ไม่สามารถอ้างอิงล็อตได้' + wh_tag,
                    warehouse_id=wh or False,
                    bal_qty=wh_q - alloc, bal_cost=0.0, bal_value=0.0)
        diff = bv - lot_val
        if abs(diff) >= 0.01:
            row(line_type='adjust', doc_ref='ปรับมูลค่า (ต่างจากล็อต)', bal_value=diff)
        return out

    # ----------------------------------------------------------- actions
    def _refresh(self):
        Line = self.env['buz.po.lot.line']
        self.env.cr.execute('DELETE FROM buz_po_lot_line WHERE wizard_id = %s', (self.id,))
        Line.invalidate_model()
        self.invalidate_recordset(['line_ids'])
        rows = self._compute_rows()
        if not rows:
            raise UserError('No data for the selected filters.')
        self._insert_lines(rows)

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
