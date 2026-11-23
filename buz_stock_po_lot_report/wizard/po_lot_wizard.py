from collections import defaultdict
from datetime import datetime, time, timedelta

import pytz

from odoo import fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_is_zero

QTY_DIGITS = 4


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
        mv = svl.stock_move_id
        if not mv:
            return False
        src, dst = mv.location_id, mv.location_dest_id
        ok = ('internal', 'transit')
        if src.usage not in ok or dst.usage not in ok:
            return False
        if self.warehouse_ids:
            whs = self.warehouse_ids
            return bool(src.warehouse_id and dst.warehouse_id
                        and src.warehouse_id in whs and dst.warehouse_id in whs)
        return True

    def _doc_ref(self, move, desc):
        if move:
            return move.picking_id.name or move.reference or move.name or desc or ''
        return desc or ''

    def _balance_product_ids(self, end_utc):
        """Products with non-zero qty (in any warehouse) at date_to (same layer scope as the
        engine); with hide_zero off also products with any layer in the window."""
        cutoff = self.env['ir.config_parameter'].sudo().get_param(
            'stock_fifo_valuation_report.cutoff_date')
        cutoff_utc = self._bangkok_start_utc(fields.Date.to_date(cutoff)) if cutoff else datetime.min
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

    def _origin_labels(self, prod, items, cutoff_utc, end_utc):
        """{svl_id: (label, date)} for transfer-in layers: trace the FIFO lots the
        transfer consumed in the source warehouse back to the real receipt
        document (PO receipt, opening balance, ...). Label keeps the transfer
        reference in brackets. Same layer scope as the main report."""
        ok = ('internal', 'transit')

        def is_tr(sv):
            mv = sv.stock_move_id
            return bool(mv) and mv.location_id.usage in ok and mv.location_dest_id.usage in ok

        if not any(t[2].quantity > 0 and is_tr(t[2]) for t in items) or end_utc is None:
            return {}
        svls = self.env['stock.valuation.layer'].sudo().search([
            ('company_id', '=', self.company_id.id), ('product_id', '=', prod.id),
            ('warehouse_id', '!=', False)])
        seq = []
        for sv in svls:
            if sv.stock_move_id.state == 'cancel' or \
                    (sv.description or '').startswith('Reverse cancelled'):
                continue
            d = sv.accounting_date or sv.create_date
            if cutoff_utc <= d < end_utc:
                seq.append((d, sv.id, sv))
        seq.sort(key=lambda t: (t[0], t[1]))
        outs_by_move = defaultdict(list)
        for d, _i, sv in seq:
            if sv.quantity < 0 and is_tr(sv):
                outs_by_move[sv.stock_move_id.id].append((d, sv))
        queues = defaultdict(list)    # warehouse id -> [[doc, date, remaining]]
        pieces = defaultdict(list)    # move id -> [[doc, date, qty]] consumed at source
        done = set()

        def consume(d, sv):
            done.add(sv.id)
            rem = -sv.quantity
            got = []
            for lot in queues[sv.warehouse_id.id]:
                if rem <= 1e-9:
                    break
                if lot[2] <= 1e-9:
                    continue
                take = min(lot[2], rem)
                lot[2] -= take
                rem -= take
                got.append([lot[0], lot[1], take])
            if rem > 1e-9:
                got.append([self._doc_ref(sv.stock_move_id, sv.description), d, rem])
            return got

        labels = {}
        for d, _i, sv in seq:
            q = sv.quantity
            mv = sv.stock_move_id
            own = self._doc_ref(mv, sv.description)
            wh = sv.warehouse_id.id
            if q < 0:
                if sv.id in done:
                    continue
                got = consume(d, sv)
                if is_tr(sv):
                    pieces[mv.id] += got
            elif q > 0 and is_tr(sv):
                for od, osv in outs_by_move.get(mv.id, []):
                    if osv.id not in done:
                        pieces[mv.id] += consume(od, osv)
                need, mine = q, []
                while need > 1e-9 and pieces[mv.id]:
                    pc = pieces[mv.id][0]
                    take = min(pc[2], need)
                    mine.append([pc[0], pc[1], take])
                    pc[2] -= take
                    need -= take
                    if pc[2] <= 1e-9:
                        pieces[mv.id].pop(0)
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
        svl_dom = [('company_id', '=', self.company_id.id),
                   ('product_id', 'in', products.ids)]
        if self.warehouse_ids:
            svl_dom.append(('warehouse_id', 'in', self.warehouse_ids.ids))
        # Same layer scope as stock_fifo_valuation_report so both reports tie:
        # no layers before its cutoff, none without a warehouse, none of
        # cancelled moves or their 'Reverse cancelled' neutralising layers.
        svl_dom += [('warehouse_id', '!=', False)]
        cutoff = self.env['ir.config_parameter'].sudo().get_param(
            'stock_fifo_valuation_report.cutoff_date')
        if cutoff:
            cutoff_utc = self._bangkok_start_utc(fields.Date.to_date(cutoff))
        else:
            cutoff_utc = datetime.min
        svls = self.env['stock.valuation.layer'].sudo().search(svl_dom)
        by_prod = defaultdict(list)
        for s in svls:
            if s.stock_move_id.state == 'cancel' or \
                    (s.description or '').startswith('Reverse cancelled'):
                continue
            d = s.accounting_date or s.create_date
            if cutoff_utc <= d < end_utc:
                by_prod[s.product_id.id].append((d, s.id, s))
        rows = []
        for prod in products.sorted(lambda p: (self._model_code(p.default_code), p.default_code or '')):
            items = sorted(by_prod.get(prod.id, []), key=lambda t: (t[0], t[1]))
            rows += self._product_rows(prod, items, start_utc, cutoff_utc, end_utc)
        return rows

    def _product_rows(self, prod, items, start_utc, cutoff_utc=None, end_utc=None):
        tz = pytz.timezone(self.env.user.tz or 'Asia/Bangkok')

        def loc_date(d):
            return pytz.UTC.localize(d).astimezone(tz).date()

        origins = self._origin_labels(prod, items, cutoff_utc, end_utc)
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
                    'warehouse_id': s.warehouse_id.id or False,
                    'bal_qty': bq, 'bal_value': bv,
                    'bal_cost': (bv / bq) if bq else 0.0}
            mv = s.stock_move_id
            vals['doc_ref'] = self._doc_ref(mv, s.description)
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
            by_wh[t[2].warehouse_id].append(t)
        if self.hide_zero and all(
                float_is_zero(sum(t[2].quantity for t in w), precision_digits=QTY_DIGITS)
                for w in by_wh.values()):
            return []  # nothing in stock at date_to in any warehouse
        lot_val = 0.0
        for wh, wh_items in sorted(by_wh.items(), key=lambda kv: kv[0].id or 0):
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
                doc = self._doc_ref(sv.stock_move_id, sv.description)
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
            wh_tag = ' · %s' % wh.name if wh else ''
            for (ldate, doc, _u), (remq, unit, recq) in sorted(merged.items(), key=lambda kv: kv[0][0]):
                val = remq * unit
                lot_val += val
                row(line_type='lot', date=ldate, doc_ref=doc + wh_tag,
                    warehouse_id=wh.id or False,
                    in_qty=recq, in_cost=unit, in_value=recq * unit,
                    bal_qty=remq, bal_cost=unit, bal_value=val)
            if not float_is_zero(wh_q - alloc, precision_digits=QTY_DIGITS):
                row(line_type='lot', doc_ref='ไม่สามารถอ้างอิงล็อตได้' + wh_tag,
                    warehouse_id=wh.id or False,
                    bal_qty=wh_q - alloc, bal_cost=0.0, bal_value=0.0)
        diff = bv - lot_val
        if abs(diff) >= 0.01:
            row(line_type='adjust', doc_ref='ปรับมูลค่า (ต่างจากล็อต)', bal_value=diff)
        return out

    # ----------------------------------------------------------- actions
    def _refresh(self):
        self.line_ids.unlink()
        rows = self._compute_rows()
        if not rows:
            raise UserError('No data for the selected filters.')
        self.env['buz.po.lot.line'].create(rows)

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
