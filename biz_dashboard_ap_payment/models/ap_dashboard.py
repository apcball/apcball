# -*- coding: utf-8 -*-
"""Engine of the Budget & Payment Control dashboard.

All aggregation and the Excel rendering live here (AbstractModel, no table) so
the controller stays a thin HTTP layer and tests can call the engine directly.

Access flow (order matters, same as biz_smart_finance): group gate as the real
user -> company scope check against ``user.company_ids`` -> ``sudo()`` with
every domain scoped by ``company_id in cids``.

Data sources (see README.md for the Thai write-up):

* ยอดจ่ายประจำเดือน  : posted vendor bills whose due date falls in the month.
* ยอดการใช้งบประมาณ   : lines of confirmed ``monthly.budget.plan`` of the month
                        (biz_monthly_analytic_budget).
* ขออนุมัติเพิ่มเติม  : ``buz.monthly.budget.approval.request`` created in the month.
* ประมาณการเดือนถัดไป : unpaid bills due next month + confirmed POs with
                        ``payment_date`` next month and something left to bill.
* budget columns per vendor/project/category: confirmed POs with
  ``payment_date`` in the month (approved = PO total, used = billed).
"""
import calendar
import copy
import io
import threading
import time
from collections import OrderedDict
from datetime import date, datetime, timedelta

from odoo import api, fields, models, tools, _
from odoo.exceptions import AccessError

MONTHS_TH = [
    'มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน',
    'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม',
]
MONTHS_TH_SHORT = [
    'ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.',
    'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.',
]
WEEK_STARTS = (1, 8, 15, 22)
BILL_TYPES = ('in_invoice', 'in_refund')
PO_STATES = ('purchase', 'done')
REQ_STATES = ('pending', 'approved', 'rejected')
TOP_VENDORS = 5
# PO unbilled amounts are computed untaxed from the PO lines; bills are
# compared on their tax-inclusive total, so they are grossed up by the
# PO's own tax ratio to keep every column on the same basis.
GROSS_UP_PO = True

# Server-side payload cache (per worker process). TTL in seconds comes from the
# system parameter ``biz_dashboard_ap_payment.cache_ttl`` (0 disables it); the
# dashboard's refresh button bypasses it.
CACHE_TTL_PARAM = 'biz_dashboard_ap_payment.cache_ttl'
DEFAULT_CACHE_TTL = 120
OPTIONS_TTL = 600
CACHE_MAX_ENTRIES = 200
_CACHE = {}
_CACHE_LOCK = threading.Lock()


def _cache_get(key, ttl):
    hit = _CACHE.get(key)
    if hit and time.monotonic() - hit[0] < ttl:
        return hit[1]
    return None


def _cache_set(key, value):
    with _CACHE_LOCK:
        if len(_CACHE) >= CACHE_MAX_ENTRIES:
            _CACHE.clear()
        _CACHE[key] = (time.monotonic(), value)


def clear_cache():
    with _CACHE_LOCK:
        _CACHE.clear()


SHEETS = ('vendor', 'project', 'category', 'all')
TABS = OrderedDict([
    ('vendor', {'label': 'ร้านค้า', 'title': 'สรุปตามร้านค้า', 'column': 'ร้านค้า / ผู้ขาย'}),
    ('project', {'label': 'โครงการ', 'title': 'สรุปตามโครงการ', 'column': 'โครงการ'}),
    ('category', {'label': 'หมวดค่าใช้จ่าย', 'title': 'สรุปตามหมวดค่าใช้จ่าย', 'column': 'หมวดค่าใช้จ่าย'}),
])
ROW_AMOUNT_KEYS = (
    'month_total', 'month_cash', 'month_credit', 'month_paid', 'month_residual',
    'budget_approved', 'budget_used', 'budget_remaining',
    'req_pending', 'req_approved', 'req_rejected',
    'next_total', 'next_cash', 'next_credit',
)
NO_VENDOR = ('none', 'ไม่ระบุร้านค้า')
NO_PROJECT = ('none', 'ไม่ระบุโครงการ')
NO_CATEGORY = ('none', 'ไม่ระบุหมวด')
TAX_ROW = ('tax', 'ภาษี / ปัดเศษ')


def _month_range(year, month):
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def _next_month(year, month):
    return (year + 1, 1) if month == 12 else (year, month + 1)


def _week_index(day):
    """1-7 -> 0, 8-14 -> 1, 15-21 -> 2, 22-end -> 3."""
    return min(3, (day - 1) // 7)


def _to_int(value):
    if value in (None, False, '', 'all', 'false', 'null'):
        return False
    try:
        return int(value)
    except (TypeError, ValueError):
        return False


def _pct(part, total):
    return round(part / total * 100.0, 1) if total else 0.0


class ApDashboard(models.AbstractModel):
    _name = 'biz.ap.dashboard'
    _description = 'Budget & Payment Control Dashboard Engine'

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @api.model
    def get_dashboard_data(self, filters=None, refresh=False):
        """Payload for the dashboard. Results are cached per filter set for a
        short TTL (the access gate and company check always run first);
        ``refresh=True`` recomputes and replaces the cached entry."""
        self._check_access()
        f = self._normalize_filters(filters or {})
        ttl = self._cache_ttl()
        key = ('data',) + self._cache_scope(f) + (
            f['month'], f['year'], f['company_id'], f['project_id'], f['partner_id'])
        if ttl and not refresh:
            cached = _cache_get(key, ttl)
            if cached is not None:
                data = copy.deepcopy(cached)
                data['from_cache'] = True
                return data
        data = self.sudo()._build(f)
        data['from_cache'] = False
        data['cache_ttl'] = ttl
        if ttl:
            _cache_set(key, copy.deepcopy(data))
        return data

    @api.model
    def build_export(self, filters=None, sheet='all'):
        if sheet not in SHEETS:
            raise ValueError('Unknown sheet: %s' % sheet)
        # same cache entry as the screen: the export matches what the user sees
        data = self.get_dashboard_data(filters)
        return self._render_xlsx(data, sheet)

    # ------------------------------------------------------------------
    # Cache
    # ------------------------------------------------------------------
    def _cache_ttl(self):
        # never cache while tests run (baseline-delta tests re-read the same
        # filters), unless a test opts in through the context
        if tools.config['test_enable'] and not self.env.context.get('ap_dashboard_cache'):
            return 0
        try:
            return max(0, int(self.env['ir.config_parameter'].sudo().get_param(
                CACHE_TTL_PARAM, DEFAULT_CACHE_TTL)))
        except (TypeError, ValueError):
            return DEFAULT_CACHE_TTL

    def _cache_scope(self, f):
        """Everything besides the filters that changes the payload."""
        return (
            self.env.cr.dbname,
            tuple(sorted(f['cids'])),
            tuple(sorted(self.env.user.company_ids.ids)),
            f['currency'].id,
            self.env.lang or '',
            f['today'],
        )

    # ------------------------------------------------------------------
    # Access / filters
    # ------------------------------------------------------------------
    def _check_access(self):
        if self.env.su:
            return
        user = self.env.user
        if not (user.has_group('biz_monthly_analytic_budget.group_monthly_budget_user')
                or user.has_group('account.group_account_invoice')):
            raise AccessError(_('ต้องเป็น Budget User หรือ Accounting / Invoicing user'))

    def _normalize_filters(self, filters):
        user = self.env.user
        today = fields.Date.context_today(self)
        month = _to_int(filters.get('month')) or today.month
        year = _to_int(filters.get('year')) or today.year
        if not 1 <= month <= 12:
            month = today.month
        if not 2000 <= year <= 2100:
            year = today.year

        allowed = user.company_ids.ids
        company_id = _to_int(filters.get('company_id'))
        if company_id and company_id not in allowed:
            raise AccessError(_('ไม่มีสิทธิ์ดูข้อมูลของบริษัทนี้'))
        cids = [company_id] if company_id else allowed

        partner_id = _to_int(filters.get('partner_id'))
        if partner_id:
            partner = self.env['res.partner'].sudo().browse(partner_id).exists()
            partner_id = partner.commercial_partner_id.id if partner else False

        company = self.env['res.company'].browse(company_id) if company_id else user.company_id
        date_from, date_to = _month_range(year, month)
        next_year, next_month = _next_month(year, month)
        next_from, next_to = _month_range(next_year, next_month)
        return {
            'month': month,
            'year': year,
            'company_id': company_id,
            'cids': cids,
            'project_id': _to_int(filters.get('project_id')),
            'partner_id': partner_id,
            'currency': company.currency_id,
            'date_from': date_from,
            'date_to': date_to,
            'next_from': next_from,
            'next_to': next_to,
            'today': today,
        }

    # ------------------------------------------------------------------
    # Pure helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _month_range(year, month):
        return _month_range(year, month)

    @staticmethod
    def _next_month(year, month):
        return _next_month(year, month)

    @staticmethod
    def _week_index(day):
        return _week_index(day)

    @staticmethod
    def _is_cash_term(term, inv_date=None, due_date=None):
        """เงินสด (ชำระทันที) = no payment term, or every term line is
        "0 days after" (immediate), or the due date is not after the
        invoice date. Everything else is credit."""
        if not term:
            return True
        lines = term.line_ids
        if lines and all(
            line.nb_days == 0 and line.delay_type == 'days_after' for line in lines
        ):
            return True
        if inv_date and due_date and due_date <= inv_date:
            return True
        return False

    def _is_cash(self, f, term, inv_date=None, due_date=None):
        """_is_cash_term with the per-term part memoised for one build."""
        cache = f.setdefault('_term_cache', {})
        if term.id not in cache:
            cache[term.id] = self._is_cash_term(term)
        return cache[term.id] or bool(inv_date and due_date and due_date <= inv_date)

    @staticmethod
    def _po_tax_factor(po):
        if not GROSS_UP_PO or not po.amount_untaxed:
            return 1.0
        return po.amount_total / po.amount_untaxed

    def _convert(self, amount, from_currency, company, day, to_currency):
        if not amount or not from_currency or from_currency == to_currency:
            return amount or 0.0
        return from_currency._convert(amount, to_currency, company, day or fields.Date.today())

    @staticmethod
    def _week_labels(date_from, date_to):
        """Four buckets with the mockup style 'สัปดาห์ 1 (1-7 มี.ค.)'."""
        short = MONTHS_TH_SHORT[date_from.month - 1]
        labels = []
        for index, start in enumerate(WEEK_STARTS):
            end = WEEK_STARTS[index + 1] - 1 if index < 3 else date_to.day
            labels.append({
                'label': 'สัปดาห์ %d' % (index + 1),
                'range': '%d-%d %s' % (start, end, short),
                'cash': 0.0, 'credit': 0.0, 'total': 0.0,
            })
        return labels

    # ---- rows -----------------------------------------------------------
    @staticmethod
    def _new_row(key, name, rec_id=0):
        row = {'seq': 0, 'id': rec_id, 'key': key, 'name': name, 'budget_pct': 0.0}
        for field in ROW_AMOUNT_KEYS:
            row[field] = 0.0
        return row

    def _accumulate(self, rows, bucket, **amounts):
        key, name = bucket[0], bucket[1]
        rec_id = bucket[2] if len(bucket) > 2 else 0
        row = rows.get(key)
        if row is None:
            row = rows[key] = self._new_row(key, name, rec_id)
        for field, value in amounts.items():
            row[field] += value or 0.0

    @staticmethod
    def _finalize_rows(rows):
        ordered = sorted(
            rows.values(),
            key=lambda r: (-r['month_total'], -r['next_total'], -r['budget_approved'], r['name']),
        )
        for seq, row in enumerate(ordered, 1):
            row['seq'] = seq
            row['budget_pct'] = _pct(row['budget_used'], row['budget_approved'])
            for field in ROW_AMOUNT_KEYS:
                row[field] = round(row[field], 2)
        return ordered

    @staticmethod
    def _footer(rows):
        footer = {'seq': None, 'id': 0, 'key': 'total', 'name': 'รวมทั้งสิ้น'}
        for field in ROW_AMOUNT_KEYS:
            footer[field] = round(sum(r[field] for r in rows), 2)
        footer['budget_pct'] = _pct(footer['budget_used'], footer['budget_approved'])
        return footer

    # ---- bucket keys ------------------------------------------------------
    @staticmethod
    def _vendor_bucket(partner):
        partner = partner.commercial_partner_id if partner else partner
        if not partner:
            return NO_VENDOR
        return ('p:%d' % partner.id, partner.name or partner.display_name, partner.id)

    def _project_domain(self, f, model):
        """Project filter on bills / POs. ``project_id`` on them comes from the
        optional job_costing_management; without it no document carries a project,
        so a project filter leaves only the budget lines."""
        if not f['project_id']:
            return []
        if 'project_id' not in self.env[model]._fields:
            return [('id', '=', 0)]
        return [('project_id', '=', f['project_id'])]

    @staticmethod
    def _project_of(record):
        """Project of a bill / PO, or an empty recordset when the field is absent."""
        if 'project_id' in record._fields:
            return record.project_id
        return record.env['project.project']

    @staticmethod
    def _project_bucket(project):
        if not project:
            return NO_PROJECT
        return ('p:%d' % project.id, project.name, project.id)

    @staticmethod
    def _category_bucket(product, account=None):
        if product and product.categ_id:
            categ = product.categ_id
            return ('cat:%d' % categ.id, categ.complete_name or categ.name, categ.id)
        if account:
            return ('acc:%d' % account.id, '%s %s' % (account.code or '', account.name), account.id)
        return NO_CATEGORY

    # ------------------------------------------------------------------
    # Domains
    # ------------------------------------------------------------------
    def _bill_domain(self, f, date_from, date_to, unpaid_only=False):
        domain = [
            ('move_type', 'in', BILL_TYPES),
            ('state', '=', 'posted'),
            ('company_id', 'in', f['cids']),
            '|',
            '&', ('invoice_date_due', '>=', date_from), ('invoice_date_due', '<=', date_to),
            '&', '&', ('invoice_date_due', '=', False),
            ('invoice_date', '>=', date_from), ('invoice_date', '<=', date_to),
        ]
        domain += self._project_domain(f, 'account.move')
        if f['partner_id']:
            domain.append(('commercial_partner_id', '=', f['partner_id']))
        if unpaid_only:
            domain.append(('payment_state', 'in', ('not_paid', 'partial')))
        return domain

    def _search_bills(self, domain):
        """One query for the needed columns instead of loading every stored
        field of account.move, then warm the line / product caches in batch."""
        Move = self.env['account.move']
        bills = Move.search_fetch(domain, [
            'move_type', 'company_id', 'invoice_date', 'invoice_date_due',
            'amount_total_signed', 'amount_residual_signed', 'invoice_payment_term_id',
            'partner_id', 'commercial_partner_id',
        ] + (['project_id'] if 'project_id' in Move._fields else []))
        lines = self.env['account.move.line'].search_fetch(
            [('move_id', 'in', bills.ids), ('display_type', '=', 'product')],
            ['move_id', 'balance', 'product_id', 'account_id'])
        by_move = {}
        for line in lines:
            by_move.setdefault(line.move_id.id, []).append(line)
        lines.product_id.categ_id.mapped('complete_name')
        return bills, by_move

    def _po_domain(self, f, date_from, date_to):
        domain = [
            ('state', 'in', PO_STATES),
            ('company_id', 'in', f['cids']),
            ('payment_date', '>=', date_from),
            ('payment_date', '<=', date_to),
        ]
        domain += self._project_domain(f, 'purchase.order')
        if f['partner_id']:
            domain.append(('partner_id.commercial_partner_id', '=', f['partner_id']))
        return domain

    @staticmethod
    def _request_currency(req):
        """Currency of ``amount_requested``: the PO / bill currency (kept in the
        document currency), company currency for PRs."""
        doc = req.ref_po_id if req.document_type == 'po' else (
            req.ref_bill_id if req.document_type == 'bill' else False)
        return (doc and doc.currency_id) or req.company_id.currency_id

    def _request_domain(self, f):
        start = datetime.combine(f['date_from'], datetime.min.time())
        end = datetime.combine(f['date_to'] + timedelta(days=1), datetime.min.time())
        return [
            ('state', 'in', REQ_STATES),
            ('company_id', 'in', f['cids']),
            ('create_date', '>=', start),
            ('create_date', '<', end),
        ]

    # ------------------------------------------------------------------
    # Record -> values
    # ------------------------------------------------------------------
    def _bill_vals(self, bill, f):
        """Amounts in the presentation currency; bills positive, refunds negative."""
        day = bill.invoice_date_due or bill.invoice_date
        company_ccy = bill.company_id.currency_id
        conv = lambda amount: self._convert(amount, company_ccy, bill.company_id, day, f['currency'])
        total = conv(-bill.amount_total_signed)
        residual = conv(-bill.amount_residual_signed)
        return {
            'date': day,
            'week': _week_index(day.day),
            'is_cash': self._is_cash(
                f, bill.invoice_payment_term_id, bill.invoice_date, bill.invoice_date_due),
            'total': total,
            'residual': residual,
            'paid': total - residual,
            'vendor': self._vendor_bucket(bill.commercial_partner_id or bill.partner_id),
            'project': self._project_bucket(self._project_of(bill)),
        }

    def _bill_line_shares(self, bill, vals, f, lines=None):
        """[(bucket, fraction)] per product line by untaxed amount, plus a tax /
        rounding remainder so the category table adds up to the bill total."""
        total = vals['total']
        if not total:
            return []
        company_ccy = bill.company_id.currency_id
        shares = []
        allocated = 0.0
        if lines is None:
            lines = [l for l in bill.invoice_line_ids if l.display_type == 'product']
        for line in lines:
            amount = self._convert(line.balance, company_ccy, bill.company_id, vals['date'], f['currency'])
            if not amount:
                continue
            allocated += amount
            shares.append((self._category_bucket(line.product_id, line.account_id), amount / total))
        remainder = total - allocated
        if abs(remainder) > 0.005:
            shares.append((TAX_ROW, remainder / total))
        return shares

    @staticmethod
    def _line_unbilled(line):
        """Untaxed amount of a PO line not yet covered by a non-cancelled bill line."""
        if not line.product_qty:
            return 0.0
        billed = sum(line.invoice_lines.filtered(
            lambda l: l.move_id.state != 'cancel').mapped('quantity'))
        return line.price_subtotal * max(0.0, line.product_qty - billed) / line.product_qty

    def _po_unbilled(self, po):
        """Untaxed amount of the PO still to be billed."""
        return sum(self._line_unbilled(l) for l in po.order_line
                   if l.display_type in (False, 'product', ''))

    def _po_vals(self, po, f):
        factor = self._po_tax_factor(po)
        day = po.payment_date
        conv = lambda amount: self._convert(amount, po.currency_id, po.company_id, day, f['currency'])
        remaining = self._po_unbilled(po) * factor
        approved = po.amount_total
        return {
            'date': day,
            'week': _week_index(day.day),
            'is_cash': self._is_cash(f, po.payment_term_id),
            'factor': factor,
            'approved': conv(approved),
            'used': conv(approved - remaining),
            'remaining': conv(remaining),
            'vendor': self._vendor_bucket(po.partner_id),
            'project': self._project_bucket(self._project_of(po)),
        }

    def _po_line_shares(self, po):
        """[(bucket, approved_fraction, remaining_fraction)] per product line."""
        lines = [l for l in po.order_line if l.display_type in (False, 'product', '')]
        untaxed = sum(l.price_subtotal for l in lines)
        remaining_total = sum(self._line_unbilled(l) for l in lines)
        shares = []
        for line in lines:
            bucket = self._category_bucket(line.product_id)
            approved_share = line.price_subtotal / untaxed if untaxed else 0.0
            unbilled = self._line_unbilled(line)
            remaining_share = unbilled / remaining_total if remaining_total else 0.0
            shares.append((bucket, approved_share, remaining_share))
        return shares

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------
    def _build(self, f):
        currency = f['currency']
        rows = {'vendor': OrderedDict(), 'project': OrderedDict(), 'category': OrderedDict()}

        def add(buckets, **amounts):
            self._accumulate(rows['vendor'], buckets['vendor'], **amounts)
            self._accumulate(rows['project'], buckets['project'], **amounts)

        # 1. ยอดจ่ายประจำเดือน --------------------------------------------------
        kpi_payment = {'total': 0.0, 'cash': 0.0, 'credit': 0.0, 'paid': 0.0, 'residual': 0.0, 'count': 0}
        weekly = self._week_labels(f['date_from'], f['date_to'])
        bills, bill_lines = self._search_bills(self._bill_domain(f, f['date_from'], f['date_to']))
        for bill in bills:
            v = self._bill_vals(bill, f)
            cash = v['total'] if v['is_cash'] else 0.0
            credit = 0.0 if v['is_cash'] else v['total']
            kpi_payment['total'] += v['total']
            kpi_payment['cash'] += cash
            kpi_payment['credit'] += credit
            kpi_payment['paid'] += v['paid']
            kpi_payment['residual'] += v['residual']
            kpi_payment['count'] += 1
            weekly[v['week']]['cash'] += cash
            weekly[v['week']]['credit'] += credit
            amounts = dict(month_total=v['total'], month_cash=cash, month_credit=credit,
                           month_paid=v['paid'], month_residual=v['residual'])
            add(v, **amounts)
            for bucket, share in self._bill_line_shares(bill, v, f, bill_lines.get(bill.id, [])):
                self._accumulate(rows['category'], bucket,
                                 **{k: val * share for k, val in amounts.items()})

        # 2. งบประมาณจาก PO ต่อร้านค้า / โครงการ / หมวด ---------------------------
        pos = self.env['purchase.order'].search(self._po_domain(f, f['date_from'], f['date_to']))
        for po in pos:
            v = self._po_vals(po, f)
            # project budget columns come from the monthly budget lines (below)
            self._accumulate(rows['vendor'], v['vendor'], budget_approved=v['approved'],
                             budget_used=v['used'], budget_remaining=v['remaining'])
            for bucket, approved_share, remaining_share in self._po_line_shares(po):
                remaining = v['remaining'] * remaining_share
                approved = v['approved'] * approved_share
                self._accumulate(rows['category'], bucket, budget_approved=approved,
                                 budget_used=approved - remaining, budget_remaining=remaining)

        # 2b. งบประมาณต่อโครงการ / CapEx-OpEx จาก monthly.budget.line ------------
        for line in self._budget_lines(f):
            conv = lambda amount: self._convert(
                amount, line.currency_id, line.company_id, f['date_from'], currency)
            approved = conv(line.budget_amount + line.carried_amount)
            used = conv(line.reserved_amount + line.used_amount)
            amounts = {'budget_approved': approved, 'budget_used': used,
                       'budget_remaining': approved - used}
            self._accumulate(rows['project'], self._project_bucket(line.project_id), **amounts)
            if line.category:
                label = dict(line._fields['category'].selection)[line.category]
                self._accumulate(rows['category'], ('budget:%s' % line.category, label, 0), **amounts)

        # 3. ขออนุมัติงบประมาณเพิ่มเติม -------------------------------------------
        kpi_request = {state: {'amount': 0.0, 'count': 0} for state in REQ_STATES}
        requests = self.env['buz.monthly.budget.approval.request'].search(self._request_domain(f))
        request_shares = {}
        for req in requests:
            po = req.ref_po_id
            if (f['project_id'] or f['partner_id']) and not po:
                continue
            if f['project_id'] and self._project_of(po).id != f['project_id']:
                continue
            if f['partner_id'] and po.partner_id.commercial_partner_id.id != f['partner_id']:
                continue
            amount = self._convert(
                req.amount_requested, self._request_currency(req), req.company_id,
                fields.Date.to_date(req.create_date), currency)
            kpi_request[req.state]['amount'] += amount
            kpi_request[req.state]['count'] += 1
            field = 'req_%s' % req.state
            buckets = {
                'vendor': self._vendor_bucket(po.partner_id) if po else NO_VENDOR,
                'project': self._project_bucket(self._project_of(po)) if po else NO_PROJECT,
            }
            add(buckets, **{field: amount})
            if po and po.id not in request_shares:
                request_shares[po.id] = self._po_line_shares(po)
            shares = request_shares[po.id] if po else []
            if not shares:
                self._accumulate(rows['category'], NO_CATEGORY, **{field: amount})
            for bucket, approved_share, _unused in shares:
                self._accumulate(rows['category'], bucket, **{field: amount * approved_share})

        # 4. ประมาณการยอดจ่ายเดือนถัดไป ------------------------------------------
        kpi_forecast = {'total': 0.0, 'cash': 0.0, 'credit': 0.0, 'from_bills': 0.0, 'from_po': 0.0}
        forecast_weekly = self._week_labels(f['next_from'], f['next_to'])

        def add_forecast(v, amount, buckets_cat):
            cash = amount if v['is_cash'] else 0.0
            credit = 0.0 if v['is_cash'] else amount
            kpi_forecast['total'] += amount
            kpi_forecast['cash'] += cash
            kpi_forecast['credit'] += credit
            forecast_weekly[v['week']]['cash'] += cash
            forecast_weekly[v['week']]['credit'] += credit
            add(v, next_total=amount, next_cash=cash, next_credit=credit)
            for bucket, share in buckets_cat:
                self._accumulate(rows['category'], bucket, next_total=amount * share,
                                 next_cash=cash * share, next_credit=credit * share)

        next_bills, next_lines = self._search_bills(
            self._bill_domain(f, f['next_from'], f['next_to'], unpaid_only=True))
        for bill in next_bills:
            v = self._bill_vals(bill, f)
            kpi_forecast['from_bills'] += v['residual']
            add_forecast(v, v['residual'], self._bill_line_shares(bill, v, f, next_lines.get(bill.id, [])))

        next_pos = self.env['purchase.order'].search(
            self._po_domain(f, f['next_from'], f['next_to'])
        ).filtered(lambda po: self._po_unbilled(po) > 0.005)
        for po in next_pos:
            v = self._po_vals(po, f)
            kpi_forecast['from_po'] += v['remaining']
            add_forecast(v, v['remaining'],
                         [(b, remaining_share) for b, _a, remaining_share in self._po_line_shares(po)])

        # 5. ยอดการใช้งบประมาณ (monthly budget plan) ------------------------------
        kpi_budget = self._allocation_summary(f)

        # 6. Finalize --------------------------------------------------------------
        for bucket in weekly + forecast_weekly:
            bucket['cash'] = round(bucket['cash'], 2)
            bucket['credit'] = round(bucket['credit'], 2)
            bucket['total'] = round(bucket['cash'] + bucket['credit'], 2)

        total = kpi_payment['total']
        kpi_payment.update({
            'cash_pct': _pct(kpi_payment['cash'], total),
            'credit_pct': _pct(kpi_payment['credit'], total),
            'paid_pct': _pct(kpi_payment['paid'], total),
            'residual_pct': _pct(kpi_payment['residual'], total),
        })
        kpi_forecast.update({
            'cash_pct': _pct(kpi_forecast['cash'], kpi_forecast['total']),
            'credit_pct': _pct(kpi_forecast['credit'], kpi_forecast['total']),
        })
        for key in ('total', 'cash', 'credit', 'paid', 'residual'):
            kpi_payment[key] = round(kpi_payment[key], 2)
        for key in ('total', 'cash', 'credit', 'from_bills', 'from_po'):
            kpi_forecast[key] = round(kpi_forecast[key], 2)
        for state in REQ_STATES:
            kpi_request[state]['amount'] = round(kpi_request[state]['amount'], 2)
        kpi_request['total'] = round(sum(kpi_request[s]['amount'] for s in REQ_STATES), 2)

        tables = {}
        for tab, data in rows.items():
            finalized = self._finalize_rows(data)
            tables[tab] = {'rows': finalized, 'footer': self._footer(finalized)}

        return {
            'filters': {
                'month': f['month'],
                'year': f['year'],
                'company_id': f['company_id'],
                'project_id': f['project_id'],
                'partner_id': f['partner_id'],
                'month_label': '%s %d' % (MONTHS_TH[f['month'] - 1], f['year']),
                'next_month_label': '%s %d' % (MONTHS_TH[f['next_from'].month - 1], f['next_from'].year),
                'date_from': fields.Date.to_string(f['date_from']),
                'date_to': fields.Date.to_string(f['date_to']),
                'next_from': fields.Date.to_string(f['next_from']),
                'next_to': fields.Date.to_string(f['next_to']),
            },
            'currency': {'id': currency.id, 'name': currency.name, 'symbol': currency.symbol},
            'as_of': fields.Date.to_string(f['today']),
            'updated_at': fields.Datetime.to_string(fields.Datetime.now()),
            'options': self._options(f),
            'kpi_payment': kpi_payment,
            'kpi_budget': kpi_budget,
            'kpi_request': kpi_request,
            'kpi_forecast': kpi_forecast,
            'weekly': weekly,
            'forecast_weekly': forecast_weekly,
            'vendor_share': self._vendor_share(tables['vendor']['rows'], total),
            'tables': tables,
            'tabs': [dict(meta, id=key) for key, meta in TABS.items()],
        }

    def _budget_lines(self, f):
        """Budget lines of confirmed monthly plans of the month (project filter applied)."""
        domain = [
            ('plan_id.state', '=', 'confirmed'),
            ('plan_id.date_from', '>=', f['date_from']),
            ('plan_id.date_from', '<=', f['date_to']),
            ('company_id', 'in', f['cids']),
        ]
        if f['project_id']:
            domain.append(('project_id', '=', f['project_id']))
        lines = self.env['monthly.budget.line'].search(domain)
        lines.mapped('plan_id')  # prefetch
        return lines

    def _allocation_summary(self, f):
        lines = self._budget_lines(f)
        approved = reserved = used = 0.0
        for line in lines:
            conv = lambda amount: self._convert(
                amount, line.currency_id, line.company_id, f['date_from'], f['currency'])
            approved += conv(line.budget_amount + line.carried_amount)
            reserved += conv(line.reserved_amount)
            used += conv(line.used_amount)
        remaining = approved - reserved - used
        return {
            'approved': round(approved, 2),
            'reserved': round(reserved, 2),
            'used': round(used, 2),
            'remaining': round(remaining, 2),
            'pct': _pct(reserved + used, approved),
            'plan_count': len(lines.mapped('plan_id')),
            'scope_note': ('งบประมาณตามแผนรายเดือน (เฉพาะบรรทัดงบของโครงการที่เลือก)'
                           if f['project_id'] else
                           'งบประมาณตามแผนรายเดือน (ไม่กรองตามร้านค้า)'),
        }

    @staticmethod
    def _vendor_share(vendor_rows, total):
        positive = [r for r in vendor_rows if r['month_total'] > 0]
        top = positive[:TOP_VENDORS]
        rest = sum(r['month_total'] for r in positive[TOP_VENDORS:])
        items = [
            {'id': r['id'], 'name': r['name'], 'amount': r['month_total'],
             'pct': _pct(r['month_total'], total)}
            for r in top
        ]
        if rest > 0:
            items.append({'id': 0, 'name': 'อื่น ๆ', 'amount': round(rest, 2), 'pct': _pct(rest, total)})
        return {'total': round(total, 2), 'items': items}

    def _options(self, f):
        """Filter lists. They change rarely, so they get their own, longer cache;
        only ``name`` is fetched (browsing partners would load every column)."""
        ttl = min(OPTIONS_TTL, self._cache_ttl() * 5)
        key = ('options',) + self._cache_scope(f)
        options = _cache_get(key, ttl) if ttl else None
        if options is None:
            projects = self.env['project.project'].search_fetch(
                ['|', ('company_id', 'in', f['cids']), ('company_id', '=', False)],
                ['name'], order='name', limit=500)
            vendors = self.env['res.partner'].search_fetch(
                [('supplier_rank', '>', 0), ('parent_id', '=', False)],
                ['name'], order='name', limit=1000)
            options = {
                'companies': [{'id': c.id, 'name': c.name} for c in self.env.user.company_ids],
                'projects': [{'id': p.id, 'name': p.name} for p in projects],
                'vendors': [{'id': p.id, 'name': p.name} for p in vendors],
                'months': [{'id': i + 1, 'name': name} for i, name in enumerate(MONTHS_TH)],
            }
            if ttl:
                _cache_set(key, options)
        options = dict(options, vendors=list(options['vendors']))
        if f['partner_id'] and all(v['id'] != f['partner_id'] for v in options['vendors']):
            partner = self.env['res.partner'].browse(f['partner_id'])
            options['vendors'].append({'id': partner.id, 'name': partner.name})
        options['years'] = sorted(
            {f['today'].year + delta for delta in range(-3, 2)} | {f['year']})
        return options

    # ------------------------------------------------------------------
    # Excel
    # ------------------------------------------------------------------
    def _render_xlsx(self, data, sheet):
        import xlsxwriter

        output = io.BytesIO()
        book = xlsxwriter.Workbook(output, {'in_memory': True})
        fmt = {
            'title': book.add_format({'bold': True, 'font_size': 14}),
            'h2': book.add_format({'bold': True, 'font_size': 11, 'bg_color': '#DCE6F7', 'border': 1}),
            'head': book.add_format({'bold': True, 'bg_color': '#DCE6F7', 'border': 1,
                                     'align': 'center', 'valign': 'vcenter', 'text_wrap': True}),
            'group_pay': book.add_format({'bold': True, 'bg_color': '#DCE6F7', 'border': 1, 'align': 'center'}),
            'group_budget': book.add_format({'bold': True, 'bg_color': '#DDF3E8', 'border': 1, 'align': 'center'}),
            'group_req': book.add_format({'bold': True, 'bg_color': '#FDE9D6', 'border': 1, 'align': 'center'}),
            'group_next': book.add_format({'bold': True, 'bg_color': '#ECE3FB', 'border': 1, 'align': 'center'}),
            'label': book.add_format({'border': 1}),
            'text': book.add_format({'border': 1}),
            'int': book.add_format({'border': 1, 'num_format': '0'}),
            'money': book.add_format({'border': 1, 'num_format': '#,##0.00'}),
            'pct': book.add_format({'border': 1, 'num_format': '0.0"%"'}),
            'foot': book.add_format({'bold': True, 'border': 1, 'top': 2}),
            'foot_money': book.add_format({'bold': True, 'border': 1, 'top': 2, 'num_format': '#,##0.00'}),
            'foot_pct': book.add_format({'bold': True, 'border': 1, 'top': 2, 'num_format': '0.0"%"'}),
        }
        self._xlsx_summary(book.add_worksheet('สรุป'), data, fmt)
        for tab, meta in TABS.items():
            if sheet in (tab, 'all'):
                self._xlsx_table(book.add_worksheet(meta['label']), data, tab, meta, fmt)
        book.close()
        return output.getvalue()

    def _xlsx_summary(self, ws, data, fmt):
        filters = data['filters']
        options = data['options']

        def option_name(key, rec_id, default='ทั้งหมด'):
            for item in options[key]:
                if item['id'] == rec_id:
                    return item['name']
            return default

        ws.write(0, 0, 'Dashboard ควบคุมงบประมาณและยอดจ่าย (Budget & Payment Control)', fmt['title'])
        ws.write(1, 0, 'ข้อมูล ณ วันที่ %s' % data['as_of'])
        ws.write(2, 0, 'เดือน / ปี'); ws.write(2, 1, filters['month_label'])
        ws.write(3, 0, 'บริษัท'); ws.write(3, 1, option_name('companies', filters['company_id']))
        ws.write(4, 0, 'โครงการ'); ws.write(4, 1, option_name('projects', filters['project_id']))
        ws.write(5, 0, 'ร้านค้า / ผู้ขาย'); ws.write(5, 1, option_name('vendors', filters['partner_id']))
        ws.write(6, 0, 'สกุลเงิน'); ws.write(6, 1, data['currency']['name'])

        row = 8
        pay = data['kpi_payment']
        row = self._xlsx_block(ws, row, '1. ยอดจ่ายประจำเดือน (%s)' % filters['month_label'], [
            ('รวม', pay['total'], None),
            ('เงินสด (ชำระทันที)', pay['cash'], pay['cash_pct']),
            ('เครดิต (ครบกำหนดเดือนนี้)', pay['credit'], pay['credit_pct']),
            ('ชำระแล้ว', pay['paid'], pay['paid_pct']),
            ('ค้างชำระ (ยังไม่ชำระ)', pay['residual'], pay['residual_pct']),
        ], fmt)
        budget = data['kpi_budget']
        row = self._xlsx_block(ws, row, '2. ยอดการใช้งบประมาณ', [
            ('งบประมาณที่ได้รับอนุมัติ', budget['approved'], None),
            ('งบผูกพันจาก PO', budget['reserved'], None),
            ('งบใช้จริง (รับสินค้า/บริการแล้ว)', budget['used'], None),
            ('งบคงเหลือ', budget['remaining'], None),
            ('% ใช้แล้ว', None, budget['pct']),
        ], fmt)
        req = data['kpi_request']
        row = self._xlsx_block(ws, row, '3. ยอดขออนุมัติงบประมาณเพิ่มเติม', [
            ('รวม', req['total'], None),
            ('รออนุมัติ (%d รายการ)' % req['pending']['count'], req['pending']['amount'], None),
            ('อนุมัติแล้ว (%d รายการ)' % req['approved']['count'], req['approved']['amount'], None),
            ('ไม่อนุมัติ (%d รายการ)' % req['rejected']['count'], req['rejected']['amount'], None),
        ], fmt)
        fc = data['kpi_forecast']
        row = self._xlsx_block(ws, row, '4. ประมาณการยอดจ่ายเดือนถัดไป (%s)' % filters['next_month_label'], [
            ('รวม', fc['total'], None),
            ('เงินสด (ชำระทันที)', fc['cash'], fc['cash_pct']),
            ('เครดิต (ครบกำหนดเดือนหน้า)', fc['credit'], fc['credit_pct']),
            ('จากใบแจ้งหนี้ค้างชำระ', fc['from_bills'], None),
            ('จาก PO ที่ยังไม่ตั้งบิล', fc['from_po'], None),
        ], fmt)

        for title, buckets in (
            ('ยอดจ่ายรายสัปดาห์ (%s)' % filters['month_label'], data['weekly']),
            ('ประมาณการยอดจ่ายรายสัปดาห์ (%s)' % filters['next_month_label'], data['forecast_weekly']),
        ):
            ws.write(row, 0, title, fmt['h2'])
            row += 1
            for col, label in enumerate(('สัปดาห์', 'เงินสด', 'เครดิต', 'รวม')):
                ws.write(row, col, label, fmt['head'])
            row += 1
            for bucket in buckets:
                ws.write(row, 0, '%s (%s)' % (bucket['label'], bucket['range']), fmt['text'])
                ws.write_number(row, 1, bucket['cash'], fmt['money'])
                ws.write_number(row, 2, bucket['credit'], fmt['money'])
                ws.write_number(row, 3, bucket['total'], fmt['money'])
                row += 1
            row += 1

        ws.write(row, 0, 'สัดส่วนยอดจ่ายประจำเดือนตามร้านค้า', fmt['h2'])
        row += 1
        for col, label in enumerate(('ร้านค้า', 'ยอด', '%')):
            ws.write(row, col, label, fmt['head'])
        row += 1
        for item in data['vendor_share']['items']:
            ws.write(row, 0, item['name'], fmt['text'])
            ws.write_number(row, 1, item['amount'], fmt['money'])
            ws.write_number(row, 2, item['pct'], fmt['pct'])
            row += 1
        ws.set_column(0, 0, 44)
        ws.set_column(1, 3, 18)

    @staticmethod
    def _xlsx_block(ws, row, title, lines, fmt):
        ws.write(row, 0, title, fmt['h2'])
        ws.write_blank(row, 1, None, fmt['h2'])
        ws.write_blank(row, 2, None, fmt['h2'])
        row += 1
        for label, amount, pct in lines:
            ws.write(row, 0, label, fmt['label'])
            if amount is None:
                ws.write_blank(row, 1, None, fmt['label'])
            else:
                ws.write_number(row, 1, amount, fmt['money'])
            if pct is None:
                ws.write_blank(row, 2, None, fmt['label'])
            else:
                ws.write_number(row, 2, pct, fmt['pct'])
            row += 1
        return row + 1

    @staticmethod
    def _xlsx_table(ws, data, tab, meta, fmt):
        filters = data['filters']
        table = data['tables'][tab]
        ws.write(0, 0, 'รายละเอียดยอดจ่าย %s (%s)' % (meta['title'], filters['month_label']), fmt['title'])
        ws.write(1, 0, 'ข้อมูล ณ วันที่ %s · สกุลเงิน %s' % (data['as_of'], data['currency']['name']))

        groups = [
            ('', 2, 'head'),
            ('ยอดจ่ายประจำเดือน (%s)' % filters['month_label'], 5, 'group_pay'),
            ('การใช้งบประมาณ (PO)', 4, 'group_budget'),
            ('ขออนุมัติเพิ่มเติม (เดือนนี้)', 3, 'group_req'),
            ('ประมาณการยอดจ่ายเดือนถัดไป (%s)' % filters['next_month_label'], 3, 'group_next'),
        ]
        col = 0
        for label, span, style in groups:
            if span > 1:
                ws.merge_range(3, col, 3, col + span - 1, label, fmt[style])
            else:
                ws.write(3, col, label, fmt[style])
            col += span
        columns = [
            ('ลำดับ', 'seq', 'int'), (meta['column'], 'name', 'text'),
            ('รวม', 'month_total', 'money'), ('เงินสด', 'month_cash', 'money'),
            ('เครดิต', 'month_credit', 'money'), ('ชำระแล้ว', 'month_paid', 'money'),
            ('ค้างชำระ', 'month_residual', 'money'),
            ('งบอนุมัติ', 'budget_approved', 'money'), ('ใช้แล้ว', 'budget_used', 'money'),
            ('% ใช้แล้ว', 'budget_pct', 'pct'), ('คงเหลือ', 'budget_remaining', 'money'),
            ('รออนุมัติ', 'req_pending', 'money'), ('อนุมัติแล้ว', 'req_approved', 'money'),
            ('ไม่อนุมัติ', 'req_rejected', 'money'),
            ('รวม', 'next_total', 'money'), ('เงินสด', 'next_cash', 'money'),
            ('เครดิต', 'next_credit', 'money'),
        ]
        for col, (label, _key, _style) in enumerate(columns):
            ws.write(4, col, label, fmt['head'])
        row = 5
        for record in table['rows']:
            for col, (_label, key, style) in enumerate(columns):
                value = record[key]
                if style == 'text':
                    ws.write(row, col, value, fmt['text'])
                else:
                    ws.write_number(row, col, value or 0, fmt[style])
            row += 1
        footer = table['footer']
        for col, (_label, key, style) in enumerate(columns):
            if key == 'seq':
                ws.write_blank(row, col, None, fmt['foot'])
            elif style == 'text':
                ws.write(row, col, footer[key], fmt['foot'])
            else:
                ws.write_number(row, col, footer[key] or 0, fmt['foot_pct' if style == 'pct' else 'foot_money'])
        ws.set_column(0, 0, 7)
        ws.set_column(1, 1, 36)
        ws.set_column(2, len(columns) - 1, 15)
        ws.freeze_panes(5, 2)
