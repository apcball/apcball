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
# lcs = ((landed-cost bill, value), ...) for value-only layers, () otherwise;
# is_lc = layer was booked by a landed-cost document
# created = when the layer was really recorded (differs from its document date when back-dated)
Layer = namedtuple('Layer', 'id product_id wh_id quantity value doc move_id is_tr src_wh dst_wh parent_id lcs is_lc '
                   'created', defaults=((), False, None))

# one layer of the FIFO queue the system holds right now (remaining_qty / remaining_value)
SysLayer = namedtuple('SysLayer', 'id wh_id doc date qty value')

# document number of a layer (the landed-cost rows override it)
DOC_SQL = ("COALESCE(NULLIF(p.name, ''), NULLIF(m.reference, ''), NULLIF(m.name, ''), "
           "NULLIF(l.description, ''), '')")


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
                        ELSE """ + DOC_SQL + """
                   END AS doc,
                   CASE WHEN l.quantity = 0 AND l.value <> 0
                             AND l.stock_valuation_layer_id IS NOT NULL
                             AND NULLIF(l.description, '') IS NOT NULL
                        THEN COALESCE(NULLIF(p.name, ''), NULLIF(m.reference, ''), NULLIF(m.name, ''))
                   END AS lcdoc,
                   m.id,
                   (m.id IS NOT NULL AND ls.usage IN ('internal', 'transit')
                        AND ld.usage IN ('internal', 'transit')) AS is_tr,
                   ls.warehouse_id, ld.warehouse_id, l.stock_valuation_layer_id,
                   COALESCE(am.name, NULLIF(slc.name, ''), NULLIF(l.description, '')) AS lcref,
                   l.stock_landed_cost_id IS NOT NULL AS is_lc,
                   l.create_date
              FROM stock_valuation_layer l
              LEFT JOIN stock_valuation_layer pl ON pl.id = l.stock_valuation_layer_id
              LEFT JOIN stock_move m ON m.id = l.stock_move_id
              LEFT JOIN stock_picking p ON p.id = m.picking_id
              LEFT JOIN stock_location ls ON ls.id = m.location_id
              LEFT JOIN stock_location ld ON ld.id = m.location_dest_id
              LEFT JOIN stock_landed_cost slc ON slc.id = l.stock_landed_cost_id
              LEFT JOIN account_move am ON am.id = slc.vendor_bill_id
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
        for (lid, pid, wh, q, v, d, doc, lcd, mid, tr, swh, dwh, par, lcref, is_lc, created) in cr.fetchall():
            lcs = ((lcref, v or 0.0),) if lcd and lcref else ()
            by_prod[pid].append((d, lid, Layer(lid, pid, wh, q or 0.0, v or 0.0, doc,
                                               mid, bool(tr), swh, dwh, par, lcs, bool(is_lc), created)))
            if lcd:
                lcdoc[lid] = lcd
        tz = pytz.timezone(self.env.user.tz or 'Asia/Bangkok')
        return {pid: self._group_landed(self._landed_after_parent(lst), lcdoc, tz)
                for pid, lst in by_prod.items()}

    @staticmethod
    def _group_landed(items, lcdoc, tz):
        """Merge value-only layers (landed cost / revaluation) that hang off the
        same layer and warehouse into one row (value summed, kept at the position
        of the first one): per landed-cost document like the FIFO valuation
        report ("... (xN)" when several lines), per local day for layers with no
        document. {layer id: receipt name} in `lcdoc` marks which layers are
        value-only."""
        out, first = [], {}
        for d, lid, sv in items:
            if lid not in lcdoc:
                out.append((d, lid, sv))
                continue
            ref = sv.lcs[0][0] if sv.lcs else None
            day = pytz.UTC.localize(d).astimezone(tz).date()
            key = (sv.parent_id, sv.wh_id, ref or day)
            if key in first:
                grp = first[key]
                grp['n'] += 1
                grp['value'] += sv.value
                for ref, val in sv.lcs:
                    grp['lcs'][ref] = grp['lcs'].get(ref, 0.0) + val
            else:
                grp = first[key] = {'n': 1, 'value': sv.value, 'idx': len(out),
                                    'lcs': dict(sv.lcs), 'byref': bool(ref)}
                out.append((d, lid, sv))
        for key, grp in first.items():
            if grp['n'] > 1:
                d, lid, sv = out[grp['idx']]
                if grp['byref']:
                    head, sep, tail = sv.doc.rpartition(' (ลงล็อต ')
                    doc = ('%s (x%d)%s%s' % (head, grp['n'], sep, tail)) if sep else \
                        '%s (x%d)' % (sv.doc, grp['n'])
                else:
                    doc = 'ค่าใช้จ่ายนำเข้า %d รายการ (ลงล็อต %s)' % (grp['n'], lcdoc[lid])
                out[grp['idx']] = (d, lid, sv._replace(
                    value=round(grp['value'], 2), lcs=tuple(grp['lcs'].items()), doc=doc))
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

    def _show_system(self):
        """The system only stores today's FIFO queue, so it can be compared
        only with a report that runs up to today."""
        return self.date_to >= fields.Date.context_today(self)

    def _system_queue_wh_clause(self):
        """(sql, params) limiting system-queue layers to the report warehouses."""
        wh_ids = self._report_wh_ids()
        if not wh_ids:
            return '', []
        # layers with no warehouse are shown unless the user picked warehouses
        no_wh = '' if self.warehouse_ids else ' OR l.warehouse_id IS NULL'
        return ' AND (l.warehouse_id = ANY(%%s)%s)' % no_wh, [list(wh_ids)]

    def _fetch_system_queue(self, product_ids):
        """{product_id: [SysLayer]}: every layer the system still holds stock or
        value on, whatever its date (this is the data as it is, errors included)."""
        if not product_ids:
            return {}
        self.env['stock.valuation.layer'].flush_model()
        wh_sql, wh_params = self._system_queue_wh_clause()
        self.env.cr.execute("""
            SELECT l.product_id, l.id, l.warehouse_id, """ + DOC_SQL + """,
                   COALESCE(l.accounting_date, l.create_date),
                   COALESCE(l.remaining_qty, 0), COALESCE(l.remaining_value, 0)
              FROM stock_valuation_layer l
              LEFT JOIN stock_move m ON m.id = l.stock_move_id
              LEFT JOIN stock_picking p ON p.id = m.picking_id
             WHERE l.company_id = %s AND l.product_id = ANY(%s)
               AND (COALESCE(l.remaining_qty, 0) <> 0 OR COALESCE(l.remaining_value, 0) <> 0)
        """ + wh_sql + """
             ORDER BY COALESCE(l.accounting_date, l.create_date), l.id
        """, [self.company_id.id, list(product_ids)] + wh_params)
        by_prod = defaultdict(list)
        for pid, lid, wh, doc, d, q, v in self.env.cr.fetchall():
            by_prod[pid].append(SysLayer(lid, wh or 0, doc, d, float(q), float(v)))
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
        if self._show_system():
            # also products the system queue still holds, so a zero-balance
            # ledger with leftover queue reaches the check list
            self.env['stock.valuation.layer'].flush_model()
            wh_sql, wh_params = self._system_queue_wh_clause()
            self.env.cr.execute(
                'SELECT DISTINCT l.product_id FROM stock_valuation_layer l '
                'WHERE l.company_id = %s AND l.remaining_qty <> 0' + wh_sql,
                [self.company_id.id] + wh_params)
            ids.update(r[0] for r in self.env.cr.fetchall())
        return list(ids)

    # ------------------------------------------------------------- engine
    def _compute_rows(self):
        return [r for rows in self._iter_rows() for r in rows]

    def _iter_rows(self, checks=None):
        """Yield the row list of one product at a time (keeps memory flat).
        `checks` (list) collects the product x warehouse rows that differ."""
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
        system = self._fetch_system_queue(products.ids) if self._show_system() else None
        for prod in products.sorted(lambda p: (self._model_code(p.default_code), p.default_code or '')):
            items = by_prod.pop(prod.id, [])  # already sorted (date, id) by SQL
            seq_all = all_layers.pop(prod.id, [])
            rows = self._product_rows(
                prod, items, start_utc, cutoff_utc, end_utc, seq_all, checks=checks,
                system=None if system is None else system.get(prod.id, []))
            if rows:
                yield rows

    def _product_rows(self, prod, items, start_utc, cutoff_utc=None, end_utc=None, seq_all=None,
                      trace=None, system=None, checks=None):
        """Ledger rows for one product: FIFO audit.

        FIFO is per warehouse (stock_fifo_by_location), so every warehouse has its
        own queue of lots. A lot is identified by its ORIGIN document (PO receipt,
        MO production, opening ...): a transfer out eats the source warehouse's
        oldest lots, and the transfer in opens lots in the destination warehouse
        that keep those origin documents. The report's lot rows show the document
        that put the stock in that warehouse's queue (e.g. the transfer), with the
        origin document(s) as a ' (ล็อต ...)' suffix; `trace` stays keyed by origin.
        Queues are consumed in document (accounting) date order.
        `seq_all` = all warehouses' layers of the
        product (needed to trace origins when a warehouse filter is set); `items`
        = the layers that belong in the report (selected warehouses).
        After every movement the remaining lots of the selected warehouses are
        emitted as 'lotbal' rows (when show_lots_each_row).

        `system` = [SysLayer] queue the system holds today (None = no
        comparison): ending lots then show it next to the replay. `checks`
        (list) gets one dict per warehouse where ledger, system queue and
        replay disagree."""
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

        # wh id -> [[origin doc, date, unit, remaining, received, layer ids,
        #            date it entered this wh, document that put it in this wh]]
        queues = defaultdict(list)
        pieces = defaultdict(list)    # move id -> [[doc, date, qty, ids, unit]] eaten at the source
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

        short = defaultdict(float)     # wh id -> qty ever issued before it was received
        lc_moved = defaultdict(float)  # wh id -> landed cost whose own lot was already used up

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
                debts[sv.wh_id] += rem
                short[sv.wh_id] += rem
                got.append([sv.doc, loc_date(d), rem, {sv.id}, abs(sv.value / sv.quantity)])
            origins[sv.id] = [(g[0], g[2]) for g in got]
            if trace is not None:
                trace['out'][sv.id] = [(g[0], g[1], g[4], g[2]) for g in got]
            return got

        seen = set()      # layer ids already applied
        pending = defaultdict(list)   # parent layer id -> [(bill, value)] booked before the lot exists
        origins = {}                  # layer id -> [(origin doc, qty)] lots a transfer moved
        debts = defaultdict(float)    # wh id -> qty issued with no lot (stock went negative)

        def settle(wh, lot):
            """Stock that arrives (back-dated receipt, transfer in) in a warehouse that
            already issued it without a lot pays the shortfall back first, so the
            lot is not shown as stock the warehouse no longer has."""
            debt = debts[wh]
            if debt > 1e-9:
                take = min(debt, lot[3])
                lot[3] -= take
                debts[wh] = debt - take
            return lot

        def add_lc(lots, parts, weight):
            """Spread landed-cost `parts` [(bill, value)] over `lots` (unit cost up)."""
            for _ref, val in parts:
                for lot in lots:
                    lot[2] += val / weight

        def flush_pending(sv):
            """Back-dated landed cost whose parent lot arrived later: add it now."""
            parts = pending.pop(sv.id, [])
            if parts:
                hit = [lot for lot in queues[sv.wh_id] if sv.id in lot[5]]
                rec = sum(lot[4] for lot in hit)
                if rec:
                    add_lc(hit, parts, rec)

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
                parts = sv.lcs or ((None, sv.value),)
                hit = [lot for lot in queues[sv.wh_id] if sv.parent_id in lot[5]]
                rec = sum(lot[4] for lot in hit)
                if rec:
                    add_lc(hit, parts, rec)
                elif sv.parent_id not in seen:
                    # booked (back-dated) before its parent lot exists: wait for it
                    pending[sv.parent_id] += parts
                else:
                    # parent lot already used up: spread over what is left in
                    # the warehouse so lots keep adding up to the ledger balance
                    lc_moved[sv.wh_id] += sv.value
                    left = [lot for lot in queues[sv.wh_id] if lot[3] > 1e-9]
                    rem_q = sum(lot[3] for lot in left)
                    if rem_q:
                        add_lc(left, parts, rem_q)
            elif q > 0:
                unit = sv.value / q
                if not sv.is_tr:
                    queues[sv.wh_id].append(settle(sv.wh_id, [sv.doc, loc_date(d), unit, q, q, {sv.id}, loc_date(d), sv.doc]))
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
                    queues[sv.wh_id].append(settle(sv.wh_id, [pc[0], pc[1], unit, take, take, pc[3] | {sv.id}, loc_date(d), sv.doc]))
                    tin.append((pc[0], pc[1], unit, take))
                    pc[2] -= take
                    need -= take
                    if pc[2] <= 1e-9:
                        pieces[mid].pop(0)
                if need > 1e-9:
                    queues[sv.wh_id].append(settle(sv.wh_id, [sv.doc, loc_date(d), unit, need, need, {sv.id}, loc_date(d), sv.doc]))
                    tin.append((sv.doc, loc_date(d), unit, need))
                origins[sv.id] = [(t[0], t[3]) for t in tin]
                if trace is not None:
                    trace['in'][sv.id] = tin
                flush_pending(sv)

        def open_lots():
            """(wh id, lot) of every lot with stock left in the selected warehouses."""
            for wh, q in queues.items():
                if sel and wh not in sel:
                    continue
                for lot in q:
                    if not float_is_zero(lot[3], precision_digits=QTY_DIGITS):
                        yield wh or 0, lot

        def live_lots():
            """For `trace`: remaining lots, ONE per (origin doc, warehouse); unit
            cost = weighted average of its pieces.
            [(date, wh, [doc, date, unit, rem, rec])]"""
            merged = {}
            for wh, lot in open_lots():
                key = (wh, lot[0])
                m = merged.get(key)
                if not m:
                    m = merged[key] = [lot[0], lot[1], lot[2], 0.0, 0.0, 0.0]
                m[5] += lot[3] * lot[2]
                m[3] += lot[3]
                m[4] += lot[4]
                m[1] = min(m[1], lot[1])
            res = []
            for (wh, _doc), m in merged.items():
                m[2] = m[5] / m[3]
                res.append((m[1], wh, m[:5]))
            return sorted(res, key=lambda t: (t[0], t[1], t[2][0]))

        def queue_lots():
            """For the report: remaining stock, ONE entry per (warehouse, document
            that put it in that warehouse's queue), oldest entry first."""
            merged = {}
            for wh, lot in open_lots():
                origin, _odate, unit, rem, rec, _ids, entered, qdoc = lot
                m = merged.get((wh, qdoc))
                if not m:
                    m = merged[(wh, qdoc)] = {'wh': wh, 'doc': qdoc, 'date': entered,
                                              'qty': 0.0, 'value': 0.0, 'received': 0.0,
                                              'origins': []}
                m['qty'] += rem
                m['value'] += rem * unit
                m['received'] += rec
                m['date'] = min(m['date'], entered)
                if origin and origin not in m['origins']:
                    m['origins'].append(origin)
            return sorted(merged.values(), key=lambda m: (m['date'], m['wh'], m['doc']))

        def wtag(wh):
            return ' · %s' % wh_names[wh] if wh in wh_names else ''

        def lot_tag(sv):
            """' (ล็อต A, B +N)': origin lot(s) a transfer leg carries, so the
            transfer document is tied to the lot it moves; an outgoing layer (sale,
            consumption, transfer out) shows the lot(s) it was cut from."""
            docs = []
            for doc, _q in origins.get(sv.id, ()):
                if doc and doc != sv.doc and doc not in docs:
                    docs.append(doc)
            if not docs:
                return ''
            more = ' +%d' % (len(docs) - 2) if len(docs) > 2 else ''
            return ' (ล็อต %s%s)' % (', '.join(docs[:2]), more)

        def queue_ref(m):
            """'DOC (ล็อต origin, ...) · warehouse'; no suffix for a direct receipt."""
            tag = ''
            if m['origins'] and m['origins'] != [m['doc']]:
                tag = ' (ล็อต %s)' % ', '.join(m['origins'])
            return m['doc'] + tag + wtag(m['wh'])

        def row(**kw):
            nonlocal seq
            seq += 1
            r = dict(base, seq=seq)
            r.update(kw)
            out.append(r)

        def snapshot():
            for m in queue_lots():
                row(line_type='lotbal', date=m['date'], wh_date=m['date'], doc_ref=queue_ref(m),
                    warehouse_id=m['wh'] or False, bal_qty=m['qty'],
                    bal_cost=m['value'] / m['qty'], bal_value=m['value'])

        # landed cost ever booked on each layer: receipt rows show the all-in unit cost
        lc_on = defaultdict(float)
        for _d, _i, s in seq_all:
            if s.is_lc and s.parent_id:
                lc_on[s.parent_id] += s.value

        bq = bv = 0.0
        opened = False
        tin_q = tin_v = tout_q = tout_v = 0.0
        window_any = any(t[0] >= start_utc for t in items)
        hidden = False  # nothing to list; the replay still runs for the check list
        for d, _i, s in seq_all:
            if d >= start_utc and not opened:
                opened = True
                if not window_any and float_is_zero(bq, precision_digits=QTY_DIGITS) \
                        and float_is_zero(bv, precision_digits=2) and self.hide_zero:
                    hidden = True
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
                    'warehouse_id': s.wh_id or False, 'doc_ref': s.doc + lot_tag(s) + wtag(s.wh_id),
                    'bal_qty': bq, 'bal_value': bv,
                    'bal_cost': (bv / bq) if bq else 0.0}
            if s.created:
                recorded = loc_date(s.created)
                vals.update(rec_date=recorded, backdated=recorded > vals['date'])
            if q > 0 or (q == 0 and v >= 0):
                vals.update(in_qty=q, in_value=v, in_cost=(v / q) if q else 0.0)
                if q > 0:
                    vals['in_allin'] = (v + lc_on.get(s.id, 0.0)) / q
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
                hidden = True
            row(line_type='opening', doc_ref='ยกมา', date=self.date_from,
                bal_qty=bq, bal_value=bv, bal_cost=(bv / bq) if bq else 0.0)
            if trace is not None:
                trace['opening'] = live_lots()
                trace['open_bal'] = {k: list(v) for k, v in trace['bal'].items()}
        if self.hide_zero and float_is_zero(bq, precision_digits=QTY_DIGITS):
            hidden = True  # nothing in stock at date_to
        if trace is not None:
            trace['ending'] = live_lots()
        ending = {(m['wh'], m['doc']): m for m in queue_lots()}
        held = {}  # (wh, doc) -> the same entry as the system holds it today
        for sl in system or ():
            key = (sl.wh_id, sl.doc)
            h = held.setdefault(key, {'qty': 0.0, 'value': 0.0})
            h['qty'] += sl.qty
            h['value'] += sl.value
            if key not in ending:
                # the replay used it up (or never had it) but the system still does
                ending[key] = {'wh': sl.wh_id, 'doc': sl.doc, 'date': loc_date(sl.date),
                               'qty': 0.0, 'value': 0.0, 'received': 0.0, 'origins': []}
            if not ending[key]['qty']:
                for origin, _q in origins.get(sl.id, ()):
                    if origin and origin not in ending[key]['origins']:
                        ending[key]['origins'].append(origin)

        def compare(qty, value, h):
            if system is None:
                return {}
            return {'has_sys': True, 'sys_qty': h['qty'], 'sys_value': h['value'],
                    'diff_qty': h['qty'] - qty, 'diff_value': h['value'] - value}

        nothing = {'qty': 0.0, 'value': 0.0}
        lot_val = lot_q = 0.0
        for key, m in sorted(ending.items(), key=lambda kv: (kv[1]['date'], kv[0])):
            lot_q += m['qty']
            lot_val += m['value']
            if m['qty']:
                unit = m['value'] / m['qty']
            else:
                h = held[key]
                unit = h['value'] / h['qty'] if h['qty'] else 0.0
            row(line_type='lot', date=m['date'], wh_date=m['date'], doc_ref=queue_ref(m),
                warehouse_id=m['wh'] or False, in_qty=m['received'], in_cost=unit,
                in_value=m['received'] * unit, bal_qty=m['qty'], bal_cost=unit,
                bal_value=m['value'], **compare(m['qty'], m['value'], held.get(key, nothing)))
        if not float_is_zero(bq - lot_q, precision_digits=QTY_DIGITS):
            row(line_type='lot', doc_ref='ไม่สามารถอ้างอิงล็อตได้',
                bal_qty=bq - lot_q, bal_cost=0.0, bal_value=0.0)
        diff = bv - lot_val
        if abs(diff) >= 0.01:
            row(line_type='adjust', doc_ref='ปรับมูลค่า (ต่างจากล็อต)', bal_value=diff)
        total_held = {'qty': sum(h['qty'] for h in held.values()),
                      'value': sum(h['value'] for h in held.values())}
        total_cmp = compare(bq, bv, total_held)  # system queue against the ledger
        row(line_type='total', doc_ref='รวม', in_qty=tin_q, in_value=tin_v,
            out_qty=tout_q, out_value=tout_v, bal_qty=bq, bal_value=bv,
            bal_cost=(bv / bq) if bq else 0.0, **total_cmp)

        if checks is not None:
            # landed cost still waiting for a lot that never showed up
            lc_left = defaultdict(float)
            for _d, _i, s in seq_all:
                if s.parent_id in pending and not s.quantity:
                    lc_left[s.wh_id] += s.value
            for wh, value in lc_left.items():
                lc_moved[wh] += value
            checks.extend(self._check_rows(
                prod, items, system, queue_lots(), short, lc_moved,
                loc_date, start_bound=cutoff_utc, end_bound=end_utc))
        return [] if hidden else out

    def _check_rows(self, prod, items, system, lots, short, lc_moved, loc_date,
                    start_bound=None, end_bound=None):
        """One dict per warehouse of `prod` where the ledger, the system queue and
        the document-date replay disagree (quantity, or value by 1 THB or more)."""
        sel = self._report_wh_ids()
        tot = defaultdict(lambda: defaultdict(float))
        in_scope = set()
        for d, lid, s in items:
            t = tot[s.wh_id or 0]
            in_scope.add(lid)
            t['ledger_qty'] += s.quantity
            t['ledger_value'] += s.value
            if s.quantity and s.created and loc_date(s.created) > loc_date(d):
                t['backdated_count'] += 1
        for m in lots:
            tot[m['wh']]['lot_qty'] += m['qty']
            tot[m['wh']]['lot_value'] += m['value']
        outside = set()
        for sl in system or ():
            t = tot[sl.wh_id]
            t['sys_qty'] += sl.qty
            t['sys_value'] += sl.value
            if sl.id not in in_scope and (
                    (start_bound and sl.date < start_bound) or (end_bound and sl.date >= end_bound)):
                outside.add(sl.wh_id)
        res = []
        for wh, t in sorted(tot.items()):
            if sel and wh and wh not in sel:
                continue
            has_sys = system is not None
            diff_sys_qty = t['sys_qty'] - t['ledger_qty'] if has_sys else 0.0
            diff_sys_value = t['sys_value'] - t['ledger_value'] if has_sys else 0.0
            diff_lot_qty = t['lot_qty'] - t['ledger_qty']
            diff_lot_value = t['lot_value'] - t['ledger_value']
            bad_sys_qty = not float_is_zero(diff_sys_qty, precision_digits=QTY_DIGITS)
            bad_lot_qty = not float_is_zero(diff_lot_qty, precision_digits=QTY_DIGITS)
            if not (bad_sys_qty or bad_lot_qty or abs(diff_sys_value) >= 1
                    or abs(diff_lot_value) >= 1):
                continue
            no_qty = float_is_zero(t['ledger_qty'], precision_digits=QTY_DIGITS)
            causes = [text for flag, text in (
                (no_qty and abs(t['ledger_value']) >= 1, 'ยอดบัญชีจำนวน 0 แต่มีมูลค่า'),
                (not no_qty and t['ledger_qty'] < 0, 'ยอดบัญชีติดลบ'),
                (bad_sys_qty, 'คิวระบบไม่ตรงบัญชี (จำนวน)'),
                (abs(diff_sys_value) >= 1, 'คิวระบบไม่ตรงบัญชี (มูลค่า)'),
                (bad_lot_qty, 'ล็อตรายงานไม่ตรงบัญชี (จำนวน)'),
                (abs(diff_lot_value) >= 1, 'ล็อตรายงานไม่ตรงบัญชี (มูลค่า)'),
                (short.get(wh, 0.0) > 1e-9, 'จ่ายก่อนรับ'),
                (abs(lc_moved.get(wh, 0.0)) >= 0.01, 'landed cost ของล็อตที่หมดแล้ว'),
                (wh in outside, 'คิวระบบมีรายการนอกช่วงรายงาน'),
                (t['backdated_count'], 'มีรายการย้อนหลัง'),
            ) if flag]
            res.append({
                'wizard_id': self.id, 'product_id': prod.id, 'warehouse_id': wh or False,
                'ledger_qty': t['ledger_qty'], 'ledger_value': t['ledger_value'],
                'has_sys': has_sys, 'sys_qty': t['sys_qty'], 'sys_value': t['sys_value'],
                'lot_qty': t['lot_qty'], 'lot_value': t['lot_value'],
                'diff_sys_qty': diff_sys_qty, 'diff_sys_value': diff_sys_value,
                'diff_lot_value': diff_lot_value,
                'backdated_count': int(t['backdated_count']),
                'short_qty': short.get(wh, 0.0), 'lc_moved_value': lc_moved.get(wh, 0.0),
                'note': ', '.join(causes),
            })
        return res

    # ----------------------------------------------------------- actions
    def _refresh(self):
        Line = self.env['buz.po.lot.line']
        self.env.cr.execute('DELETE FROM buz_po_lot_line WHERE wizard_id = %s', (self.id,))
        self.env['buz.po.lot.check'].search([('wizard_id', '=', self.id)]).unlink()
        Line.invalidate_model()
        self.invalidate_recordset(['line_ids'])
        buf, total, lotbal = [], 0, 0
        checks = []
        for rows in self._iter_rows(checks=checks):
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
        self.env['buz.po.lot.check'].create(checks)
        if not total and not checks:
            raise UserError('No data for the selected filters.')

    LINE_COLS = ('product_id', 'model_code', 'seq', 'line_type', 'date', 'doc_ref',
                 'warehouse_id', 'in_qty', 'in_cost', 'in_value', 'out_qty', 'out_cost',
                 'out_value', 'bal_qty', 'bal_cost', 'bal_value', 'wh_date', 'in_allin',
                 'rec_date', 'backdated', 'has_sys', 'sys_qty', 'sys_value', 'diff_qty', 'diff_value')

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
