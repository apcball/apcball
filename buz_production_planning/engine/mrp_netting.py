"""MRP netting engine for buz_production_planning.

Two stages, so the logic can be tested without any UI or stock data:

* ``PlanGatherer.gather()``  reads the database in batches and returns a
  ``PlanData`` object (plain dicts / lists).
* ``solve(data)``            nets level by level and returns a ``PlanResult``
  (suggestion and demand-line value dicts). It never writes to the database.
* ``persist(run, result)``   writes the result on a ``buz.plan.run``.
"""
# pylint: disable=prefer-env-translation  # Odoo 17 has no env._ (that is Odoo 18 API)
# pylint: disable=protected-access  # standard ORM helpers (_read_group, _bom_find, _for_xml_id, ...)
import math
from collections import defaultdict
from datetime import timedelta

from odoo import _, fields
from odoo.exceptions import UserError

MAX_DEPTH = 10
EPS = 1e-6
OPEN_DELIVERY_STATES = ('confirmed', 'waiting', 'partially_available', 'assigned')
OPEN_MOVE_STATES_EXCLUDED = ('done', 'cancel', 'draft')
# Vendor delays of 0 or 1 day are placeholder master data (prod 2026-11: 1,585 x 0, 780 x 1).
MAX_PLACEHOLDER_VENDOR_DELAY = 1
DEFAULT_PARAM = {
    'safety_stock': 0.0, 'min_batch_qty': 0.0, 'batch_multiple': 0.0,
    'lead_make_days': None, 'lead_buy_days': None, 'supply_method': 'auto',
    'picking_type_id': False, 'vendor_id': False, 'forecast_method': 'avg',
}


# ----------------------------------------------------------------------
# Pure helpers
# ----------------------------------------------------------------------
def week_start(day):
    return day - timedelta(days=day.weekday())


def bucket_index(day, start, n_buckets):
    """Weekly bucket of ``day``. Past dates land in bucket 0, dates after the
    horizon return None."""
    idx = max((day - start).days // 7, 0)
    return idx if idx < n_buckets else None


def round_up_qty(qty, min_batch=0.0, multiple=0.0, rounding=0.0):
    """Round a shortage up to the minimum batch, then up to the multiple, then
    up to the unit of measure rounding (0.083 units becomes 1 unit)."""
    if qty <= EPS:
        return 0.0
    qty = max(qty, min_batch or 0.0)
    if multiple and multiple > 0:
        qty = math.ceil(qty / multiple - 1e-9) * multiple
    if rounding and rounding > 0:
        qty = math.ceil(qty / rounding - 1e-9) * rounding
    return qty


def forecast_window(date_from, lookback_weeks, cutoff):
    """(start, end) of the history used for the average, never before cut-off."""
    start = max(date_from - timedelta(weeks=lookback_weeks), cutoff)
    return start, date_from


def net_product(onhand, receipts, demand, safety, min_batch, multiple, rounding=0.0):
    """Walk the buckets; return one entry per shortage (see PlanData docs)."""
    projected = onhand
    cum_in = cum_dem = 0.0
    out = []
    for b in range(len(demand)):
        projected += receipts[b] - demand[b]
        cum_in += receipts[b]
        cum_dem += demand[b]
        if projected < safety - EPS:
            shortage = safety - projected
            qty = round_up_qty(shortage, min_batch, multiple, rounding)
            out.append({
                'bucket': b, 'qty': qty, 'shortage': shortage, 'onhand': onhand,
                'incoming': cum_in, 'demand': cum_dem, 'projected': projected,
            })
            projected += qty
    return out


def resolve_method(param, bom):
    method = param['supply_method']
    if method == 'auto':
        return 'make' if bom else 'buy'
    return method


def blanket_order_supply(suggestions):
    """Quantity a plan's blanket orders still have to bring in, per suggestion.

    Returns ``{suggestion.id: qty in the product's stock unit}`` for suggestions
    linked to a blanket order line that is still open: the plan made the blanket
    order (``buz_plan_run_id``; a hand-made one is never counted, prod keeps 176
    old ones open), its state is not done / cancel and its deadline has not passed.

    A blanket order creates no stock move until a PO issued from it is confirmed,
    so without this the next Compute would propose the same purchase again.
    ``qty_ordered`` counts only confirmed POs (state purchase / done); their
    receipts are already netted through ``PlanGatherer._receipts``, and a draft PO
    stays inside the remaining quantity, so every unit is counted exactly once.
    Odoo books ``qty_ordered`` of a product on the FIRST line of that product in
    the blanket order (the other lines read 0), so the remaining quantity is
    worked out per (blanket order, product): the ordered quantity is consumed
    against the earliest lines first and what is left stays on the latest ones.
    """
    now = fields.Datetime.now()
    out = {}
    linked = suggestions.filtered(lambda s: s.requisition_line_id)
    requisitions = linked.requisition_id.filtered(
        lambda r: r.buz_plan_run_id and r.state not in ('done', 'cancel')
        and (not r.date_end or r.date_end >= now))
    for req in requisitions:
        by_product = defaultdict(list)
        for line in req.line_ids:
            by_product[line.product_id].append(line)
        for product, lines in by_product.items():
            ordered = sum(l.qty_ordered for l in lines)
            remaining = {}
            for line in sorted(lines, key=lambda l: (l.schedule_date or fields.Date.today(), l.id)):
                used = min(line.product_qty, ordered)
                ordered -= used
                remaining[line.id] = line.product_uom_id._compute_quantity(
                    max(line.product_qty - used, 0.0), product.uom_id, round=False)
            for s in linked.filtered(lambda s: s.requisition_id == req and s.product_id == product):
                out[s.id] = remaining.get(s.requisition_line_id.id, 0.0)
    return out


# ----------------------------------------------------------------------
# Data containers
# ----------------------------------------------------------------------
class PlanData:
    """Everything solve() needs. All per-product containers are keyed by
    product id and hold one float per bucket where noted."""

    def __init__(self, env, start, n_buckets, today, products, **kw):
        self.env = env
        self.start = start                    # Monday of the first bucket
        self.n = n_buckets
        self.today = today
        self.products = products              # product.product recordset (planable)
        self.params = kw.get('params', {})    # pid -> param dict (missing = default)
        self.boms = kw.get('boms', {})        # pid -> normal mrp.bom
        self.delivery = kw.get('delivery', {})            # pid -> [qty]*n
        self.delivery_refs = kw.get('delivery_refs', {})  # (pid, b) -> str
        self.forecast_avg = kw.get('forecast_avg', {})    # pid -> qty per week
        self.manual = kw.get('manual', {})    # (pid, b) -> manual forecast qty
        self.raw = kw.get('raw', {})          # pid -> [qty]*n  (open MO components)
        self.raw_refs = kw.get('raw_refs', {})
        self.receipts = kw.get('receipts', {})            # pid -> [qty]*n
        self.onhand = kw.get('onhand', {})    # pid -> qty
        self.kept = kw.get('kept', [])        # approved / done suggestions kept
        self.allowed_picking_type_ids = set(kw.get('allowed_picking_type_ids', ()))
        self.last_lines = kw.get('last_lines', {})  # pid -> picking type of latest MO
        self.cfg = kw.get('cfg', {'lead_make_days': 3.0, 'lead_buy_days': 7.0})

    def param(self, pid):
        return {**DEFAULT_PARAM, **self.params.get(pid, {})}

    def bucket_date(self, b):
        return self.start + timedelta(weeks=b)


class PlanResult:
    def __init__(self):
        self.suggestions = []   # value dicts, parents always before children
        self.demand = []        # value dicts for buz.plan.demand.line
        self.warnings = []


# ----------------------------------------------------------------------
# Solver
# ----------------------------------------------------------------------
def _decisions(data):
    decisions = {}
    for product in data.products:
        bom = data.boms.get(product.id)
        method = resolve_method(data.param(product.id), bom)
        decisions[product.id] = (method, bom if method == 'make' else None)
    return decisions


def _children(data, decisions):
    pmap = {p.id: p for p in data.products}
    children = {}
    for pid, (method, bom) in decisions.items():
        if method != 'make' or not bom:
            continue
        _boms, lines = bom.explode(pmap[pid], 1.0)
        children[pid] = {l.product_id.id for l, _d in lines if l.product_id.id in pmap}
    return children


def compute_levels(data, decisions):
    """Low-level code: longest BoM path from any end product. Raises UserError
    on a BoM loop or when the depth exceeds MAX_DEPTH."""
    children = _children(data, decisions)
    pmap = {p.id: p for p in data.products}
    indeg = {pid: 0 for pid in pmap}
    for kids in children.values():
        for kid in kids:
            indeg[kid] += 1
    level = {pid: 0 for pid in pmap}
    queue = [pid for pid, d in indeg.items() if d == 0]
    done = 0
    while queue:
        pid = queue.pop()
        done += 1
        for kid in children.get(pid, ()):
            level[kid] = max(level[kid], level[pid] + 1)
            if level[kid] > MAX_DEPTH:
                raise UserError(_(
                    "The bill of materials of %(product)s is nested more than %(depth)s levels deep. "
                    "Flatten the BoM structure or check it for a loop.",
                    product=pmap[kid].display_name, depth=MAX_DEPTH))
            indeg[kid] -= 1
            if indeg[kid] == 0:
                queue.append(kid)
    if done < len(pmap):
        stuck = {pid for pid, d in indeg.items() if d > 0}
        path = _find_cycle(stuck, children)
        raise UserError(_(
            "Bill of materials loop detected: %s. "
            "Remove the circular component from one of these BoMs and compute again.",
            " → ".join(pmap[pid].display_name for pid in path)))
    return level


def _find_cycle(nodes, children):
    """Return a closed path [a, b, ..., a] inside ``nodes`` (a cycle exists)."""
    color = {}

    def visit(pid, trail):
        color[pid] = 1
        trail.append(pid)
        for kid in sorted(children.get(pid, ())):
            if kid not in nodes:
                continue
            if color.get(kid) == 1:
                return trail[trail.index(kid):] + [kid]
            if kid not in color:
                found = visit(kid, trail)
                if found:
                    return found
        trail.pop()
        color[pid] = 2
        return None

    for pid in sorted(nodes):
        if pid not in color:
            found = visit(pid, [])
            if found:
                return found
    return []


def solve(data):
    n, start = data.n, data.start
    result = PlanResult()
    pmap = {p.id: p for p in data.products}
    decisions = _decisions(data)
    level = compute_levels(data, decisions)
    zeros = lambda: [0.0] * n  # noqa: E731

    dep = defaultdict(zeros)       # dependent demand coming from suggestions
    dep_lines = defaultdict(float)  # (pid, bucket, parent_key) -> qty
    contrib = defaultdict(lambda: defaultdict(float))  # (pid, b) -> {parent: qty}
    counter = [0]

    def explode(pid, bom, qty, release, parent_key):
        product = pmap[pid]
        bom_qty = product.uom_id._compute_quantity(qty, bom.product_uom_id, round=False)
        _boms, lines = bom.explode(product, bom_qty / (bom.product_qty or 1.0))
        b = bucket_index(release, start, n)
        if b is None:
            return
        for line, vals in lines:
            comp = line.product_id
            if comp.id not in pmap:
                continue
            cq = line.product_uom_id._compute_quantity(vals['qty'], comp.uom_id, round=False)
            dep[comp.id][b] += cq
            dep_lines[(comp.id, b, parent_key)] += cq
            contrib[(comp.id, b)][parent_key] += cq

    kept_by_product = defaultdict(list)
    for k in data.kept:
        kept_by_product[k['product_id']].append(k)

    by_level = defaultdict(list)
    for pid, lvl in level.items():
        by_level[lvl].append(pid)

    for lvl in sorted(by_level):
        for pid in sorted(by_level[lvl]):
            product = pmap[pid]
            prm = data.param(pid)
            method, bom = decisions[pid]
            if method == 'none':
                continue
            delivery = data.delivery.get(pid, zeros())
            raw = data.raw.get(pid, zeros())
            receipts = list(data.receipts.get(pid, zeros()))

            # ---- demand per bucket: delivery + (forecast excess or manual)
            demand = zeros()
            fmethod = prm['forecast_method']
            avg = data.forecast_avg.get(pid, 0.0) if fmethod == 'avg' else 0.0
            for b in range(n):
                manual = data.manual.get((pid, b), 0.0)
                excess = max(0.0, avg - delivery[b])
                # A manual forecast replaces the average, so it also absorbs open orders.
                eff = max(0.0, manual - delivery[b]) if manual > EPS else excess
                if delivery[b] > EPS:
                    result.demand.append({
                        'product_id': pid, 'bucket_start': data.bucket_date(b), 'source': 'delivery',
                        'qty': delivery[b], 'origin_ref': data.delivery_refs.get((pid, b), '')})
                if fmethod == 'manual' or avg > EPS or manual > EPS:
                    result.demand.append({
                        'product_id': pid, 'bucket_start': data.bucket_date(b), 'source': 'forecast',
                        'qty': excess, 'qty_manual': manual})
                if raw[b] > EPS:
                    result.demand.append({
                        'product_id': pid, 'bucket_start': data.bucket_date(b), 'source': 'dependent',
                        'qty': raw[b], 'origin_ref': data.raw_refs.get((pid, b), '')})
                demand[b] = delivery[b] + eff + raw[b] + dep[pid][b]

            # ---- approved / done suggestions count as scheduled receipts
            for k in kept_by_product.get(pid, ()):
                b = bucket_index(k['date_need'], start, n)
                if b is not None:
                    receipts[b] += k['qty']
                if k['action'] == 'make' and bom:
                    explode(pid, bom, k['qty'], k['date_release'], ('db', k['id']))

            # ---- net
            hits = net_product(
                data.onhand.get(pid, 0.0), receipts, demand,
                prm['safety_stock'], prm['min_batch_qty'], prm['batch_multiple'],
                product.uom_id.rounding)
            for hit in hits:
                sugg = _make_suggestion(data, product, prm, method, bom, hit, lvl, counter, result)
                if not sugg:
                    continue
                shares = defaultdict(float)
                for b in range(hit['bucket'] + 1):
                    for parent, q in contrib.get((pid, b), {}).items():
                        shares[parent] += q
                sugg['parent_key'] = max(shares, key=shares.get) if shares else False
                result.suggestions.append(sugg)
                if sugg['action'] == 'make':
                    explode(pid, bom, sugg['qty'], sugg['date_release'], sugg['key'])

    for (pid, b, parent), qty in dep_lines.items():
        result.demand.append({
            'product_id': pid, 'bucket_start': data.bucket_date(b), 'source': 'dependent',
            'qty': qty, 'parent_key': parent})
    return result


def _warn(result, message):
    if message not in result.warnings:
        result.warnings.append(message)


def _make_suggestion(data, product, prm, method, bom, hit, lvl, counter, result):
    cfg = data.cfg
    date_need = data.bucket_date(hit['bucket'])
    vendor_id = False
    picking_type_id = False
    if method == 'make':
        if not bom:
            _warn(result, _("%s: marked Make but has no BoM.", product.display_name))
            return None
        # Prod BoMs carry no line (1 of 2,526): fall back to the product's latest MO,
        # the same rule as "Compute Defaults from History".
        picking_type_id = (prm['picking_type_id'] or bom.picking_type_id.id
                           or data.last_lines.get(product.id) or False)
        allowed = data.allowed_picking_type_ids
        if allowed and picking_type_id not in allowed:
            line = data.env['stock.picking.type'].browse(picking_type_id) if picking_type_id else None
            _warn(result, _(
                "%(product)s: needs %(qty)s but its production line %(line)s is not selected in "
                "this plan, so nothing is suggested for it or its components.",
                product=product.display_name, qty=hit['qty'],
                line=line.display_name if line else _("(none)")))
            return None
        lead = prm['lead_make_days']
        if lead is None:
            lead = bom.produce_delay or cfg['lead_make_days']
    else:
        seller = product._select_seller(
            quantity=hit['qty'], date=date_need, uom_id=product.uom_id)
        if not seller:
            # Shortage below every vendor's minimum quantity: still name the usual vendor.
            seller = product._select_seller(quantity=None, date=date_need, uom_id=product.uom_id)
        vendor_id = prm['vendor_id'] or seller.partner_id.id or False
        lead = prm['lead_buy_days']
        if lead is None:
            lead = (seller.delay if seller.delay > MAX_PLACEHOLDER_VENDOR_DELAY
                    else cfg['lead_buy_days'])
        if not vendor_id:
            _warn(result, _("%s: no vendor configured.", product.display_name))
    release = date_need - timedelta(days=math.ceil(lead))
    is_late = release < data.today
    if is_late:
        release = data.today
    counter[0] += 1
    return {
        'key': ('tmp', counter[0]),
        'product_id': product.id, 'action': method, 'qty': hit['qty'], 'uom_id': product.uom_id.id,
        'date_need': date_need, 'date_release': release, 'is_late': is_late,
        'bom_id': bom.id if bom else False, 'picking_type_id': picking_type_id,
        'vendor_id': vendor_id, 'level': lvl,
        'onhand_qty': hit['onhand'], 'incoming_qty': hit['incoming'], 'demand_qty': hit['demand'],
        'projected_qty': hit['projected'], 'shortage_qty': hit['shortage'],
    }


# ----------------------------------------------------------------------
# Database access
# ----------------------------------------------------------------------
class PlanGatherer:
    def __init__(self, run):
        self.run = run
        self.env = run.env
        self.cr = run.env.cr

    # -- helpers ------------------------------------------------------
    def _tz(self):
        return self.env.user.tz or 'Asia/Bangkok'

    def _bucketize(self, rows, start, n):
        """rows: (pid, local_date, qty, refs) -> qty dict, refs dict."""
        qty, refs = defaultdict(lambda: [0.0] * n), {}
        for pid, day, q, names in rows:
            b = bucket_index(day, start, n)
            if b is None:
                continue
            qty[pid][b] += q or 0.0
            old = refs.get((pid, b), [])
            refs[(pid, b)] = old + [x for x in (names or []) if x and x not in old]
        return qty, {k: ", ".join(v[:5]) + (" …" if len(v) > 5 else "") for k, v in refs.items()}

    def _delivery(self, start, n):
        self.cr.execute("""
            SELECT m.product_id, (m.date AT TIME ZONE 'UTC' AT TIME ZONE %s)::date,
                   SUM(m.product_qty), ARRAY_AGG(DISTINCT p.name)
              FROM stock_move m
              JOIN stock_picking_type pt ON pt.id = m.picking_type_id
              JOIN stock_location ld ON ld.id = m.location_dest_id
              LEFT JOIN stock_picking p ON p.id = m.picking_id
             WHERE pt.code = 'outgoing' AND ld.usage = 'customer'
               AND m.state IN %s AND m.company_id = %s
               AND COALESCE(m.scrapped, FALSE) = FALSE
             GROUP BY 1, 2
        """, (self._tz(), OPEN_DELIVERY_STATES, self.run.company_id.id))
        return self._bucketize(self.cr.fetchall(), start, n)

    def _forecast(self, date_from, lookback_weeks, cutoff):
        w_start, w_end = forecast_window(date_from, lookback_weeks, cutoff)
        days = (w_end - w_start).days
        if days <= 0:
            return {}
        self.cr.execute("""
            SELECT m.product_id, SUM(m.product_qty)
              FROM stock_move m
              JOIN stock_picking_type pt ON pt.id = m.picking_type_id
              JOIN stock_location ld ON ld.id = m.location_dest_id
             WHERE pt.code = 'outgoing' AND ld.usage = 'customer'
               AND m.state = 'done' AND m.company_id = %s
               AND (m.date AT TIME ZONE 'UTC' AT TIME ZONE %s)::date >= %s
               AND (m.date AT TIME ZONE 'UTC' AT TIME ZONE %s)::date < %s
             GROUP BY 1
        """, (self.run.company_id.id, self._tz(), w_start, self._tz(), w_end))
        weeks = days / 7.0
        return {pid: (q or 0.0) / weeks for pid, q in self.cr.fetchall()}

    def _raw(self, start, n):
        self.cr.execute("""
            SELECT m.product_id, (m.date AT TIME ZONE 'UTC' AT TIME ZONE %s)::date,
                   SUM(m.product_qty), ARRAY_AGG(DISTINCT mo.name)
              FROM stock_move m
              JOIN mrp_production mo ON mo.id = m.raw_material_production_id
             WHERE mo.state IN ('confirmed', 'progress', 'to_close')
               AND m.state NOT IN %s AND m.company_id = %s
             GROUP BY 1, 2
        """, (self._tz(), OPEN_MOVE_STATES_EXCLUDED, self.run.company_id.id))
        return self._bucketize(self.cr.fetchall(), start, n)

    def _receipts(self, product_ids, start, n):
        wh_ids = tuple(self.run.warehouse_ids.ids) or (0,)
        self.cr.execute("""
            SELECT m.product_id, (m.date AT TIME ZONE 'UTC' AT TIME ZONE %s)::date,
                   SUM(m.product_qty), ARRAY[]::varchar[]
              FROM stock_move m
              JOIN stock_picking_type pt ON pt.id = m.picking_type_id
              LEFT JOIN mrp_production mo ON mo.id = m.production_id
             WHERE m.product_id IN %s AND pt.warehouse_id IN %s
               AND m.state NOT IN %s AND m.company_id = %s
               AND (m.purchase_line_id IS NOT NULL
                    OR (m.production_id IS NOT NULL
                        AND mo.state IN ('confirmed', 'progress', 'to_close')))
             GROUP BY 1, 2
        """, (self._tz(), tuple(product_ids) or (0,), wh_ids,
              OPEN_MOVE_STATES_EXCLUDED, self.run.company_id.id))
        qty, _refs = self._bucketize(self.cr.fetchall(), start, n)
        return qty

    def _other_plan_drafts(self):
        """Draft MOs / RFQs created by other plans: not in stock moves yet, but
        already on their way, so a second plan must not propose them again.
        Returned in the ``_kept`` format, so solve() counts each one as a
        receipt and explodes a draft MO into component demand (its draft raw
        moves are not in ``_raw``). Draft documents made by hand are not
        counted (many are abandoned RFQs)."""
        out = []
        others = self.env['buz.plan.suggestion'].search([
            ('run_id', '!=', self.run.id), ('run_id.state', '!=', 'cancel'),
            ('company_id', '=', self.run.company_id.id), ('state', '=', 'done')])
        blanket = blanket_order_supply(others)
        for s in others:
            product = s.product_id
            mo, pol = s.production_id, s.purchase_line_id
            if s.requisition_line_id:
                qty = blanket.get(s.id, 0.0)
                if qty <= EPS:
                    continue
            elif mo and mo.state == 'draft':
                qty = mo.product_uom_id._compute_quantity(mo.product_qty, product.uom_id, round=False)
            elif pol and pol.order_id.state in ('draft', 'sent'):
                qty = pol.product_uom._compute_quantity(pol.product_qty, product.uom_id, round=False)
            else:
                continue
            out.append({
                'id': s.id, 'product_id': product.id, 'action': s.action, 'qty': qty,
                'date_need': s.date_need, 'date_release': s.date_release})
        return out

    def _onhand(self, products):
        locations = self.run.warehouse_ids.lot_stock_id
        if not locations or not products:
            return {}
        groups = self.env['stock.quant']._read_group(
            [('location_id', 'child_of', locations.ids), ('product_id', 'in', products.ids),
             ('company_id', '=', self.run.company_id.id)],
            ['product_id'], ['quantity:sum'])
        return {product.id: qty for product, qty in groups}

    def _last_lines(self, product_ids):
        """Production line of each product's latest non-cancelled MO."""
        if not product_ids:
            return {}
        self.cr.execute("""
            SELECT DISTINCT ON (product_id) product_id, picking_type_id
              FROM mrp_production
             WHERE product_id IN %s AND company_id = %s AND state != 'cancel'
               AND picking_type_id IS NOT NULL
             ORDER BY product_id, date_start DESC NULLS LAST, id DESC
        """, (tuple(product_ids), self.run.company_id.id))
        return dict(self.cr.fetchall())

    def _params(self):
        out = {}
        for p in self.env['buz.plan.product.param'].search(
                [('company_id', '=', self.run.company_id.id)]):
            out[p.product_id.id] = {
                'safety_stock': p.safety_stock, 'min_batch_qty': p.min_batch_qty,
                'batch_multiple': p.batch_multiple, 'lead_make_days': p.lead_time_make_days,
                'lead_buy_days': p.lead_time_buy_days, 'supply_method': p.supply_method,
                'picking_type_id': p.picking_type_id.id, 'vendor_id': p.vendor_id.id,
                'forecast_method': p.forecast_method,
            }
        return out

    def _kept(self):
        kept = []
        suggestions = self.run.suggestion_ids.filtered(lambda s: s.state in ('approved', 'done'))
        blanket = blanket_order_supply(suggestions)
        for s in suggestions:
            qty = s.qty
            if s.state == 'done':
                if s.requisition_line_id:
                    # Counted for what the blanket order still has to bring in.
                    qty = blanket.get(s.id, 0.0)
                    doc_open = qty > EPS
                else:
                    doc_open = (s.production_id and s.production_id.state == 'draft') or (
                        s.purchase_line_id and s.purchase_line_id.order_id.state in ('draft', 'sent'))
                if not doc_open:
                    continue
            kept.append({
                'id': s.id, 'product_id': s.product_id.id, 'action': s.action, 'qty': qty,
                'date_need': s.date_need, 'date_release': s.date_release})
        return kept

    # -- main ---------------------------------------------------------
    def gather(self, cfg):
        run, env = self.run, self.env
        env.flush_all()  # the SQL below must see pending ORM writes
        start = week_start(run.date_from)
        n = run.horizon_weeks
        params = self._params()
        delivery, delivery_refs = self._delivery(start, n)
        raw, raw_refs = self._raw(start, n)
        forecast = self._forecast(run.date_from, run.forecast_lookback_weeks, cfg['history_cutoff'])
        kept = self._kept() + self._other_plan_drafts()
        manual = {
            (l.product_id.id, (l.bucket_start - start).days // 7): l.qty_manual
            for l in run.demand_line_ids if l.source == 'forecast' and l.qty_manual > EPS}

        def allowed(pid):
            return DEFAULT_PARAM | params.get(pid, {})

        seeds = set(delivery) | set(raw) | {k['product_id'] for k in kept} | {p for p, _b in manual}
        seeds |= {pid for pid, q in forecast.items()
                  if q > EPS and allowed(pid)['forecast_method'] == 'avg'}
        seeds |= {pid for pid, prm in params.items() if prm['safety_stock'] > EPS}
        Product = env['product.product']
        products = Product.search([('id', 'in', list(seeds)), ('detailed_type', '=', 'product')])
        products = products.filtered(lambda p: allowed(p.id)['supply_method'] != 'none')

        # BoM closure: pull in every component that is itself planable.
        boms, frontier = {}, products
        while frontier:
            found = env['mrp.bom']._bom_find(frontier, company_id=run.company_id.id, bom_type='normal')
            new = Product
            for p in frontier:
                bom = found.get(p)
                if bom:
                    boms[p.id] = bom
                if resolve_method(allowed(p.id), bom) == 'make' and bom:
                    _b, lines = bom.explode(p, 1.0)
                    new |= Product.browse([l.product_id.id for l, _d in lines])
            new = (new - products).filtered(lambda p: p.detailed_type == 'product')
            new = new.filtered(lambda p: allowed(p.id)['supply_method'] != 'none')
            products |= new
            frontier = new

        ids = products.ids
        return PlanData(
            env, start, n, fields.Date.context_today(run), products,
            params=params, boms=boms,
            delivery={k: v for k, v in delivery.items() if k in ids}, delivery_refs=delivery_refs,
            forecast_avg=forecast, manual=manual,
            raw={k: v for k, v in raw.items() if k in ids}, raw_refs=raw_refs,
            receipts=self._receipts(ids, start, n), onhand=self._onhand(products),
            kept=kept, allowed_picking_type_ids=run.picking_type_ids.ids, cfg=cfg,
            last_lines=self._last_lines([pid for pid in ids if pid in boms]))


def persist(run, result):
    """Replace the run's proposed suggestions and demand lines by ``result``."""
    run.suggestion_ids.filtered(lambda s: s.state == 'proposed').unlink()
    run.demand_line_ids.unlink()
    Suggestion = run.env['buz.plan.suggestion']
    ids = {}
    for vals in result.suggestions:
        key = vals.pop('key')
        parent = vals.pop('parent_key')
        rec = Suggestion.create({
            **vals, 'run_id': run.id,
            'parent_suggestion_id': (
                parent[1] if parent and parent[0] == 'db' else ids.get(parent, False)),
        })
        ids[key] = rec.id
    lines = []
    for vals in result.demand:
        parent = vals.pop('parent_key', None)
        if parent:
            ref = ids.get(parent) if parent[0] == 'tmp' else parent[1]
            vals['origin_ref'] = Suggestion.browse(ref).product_id.display_name if ref else ''
        lines.append({**vals, 'run_id': run.id})
    run.env['buz.plan.demand.line'].create(lines)
    return len(result.suggestions), len(lines)
