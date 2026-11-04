# -*- coding: utf-8 -*-
"""Read-only data service for the OWL asset dashboard.

Rules:
  * Never writes. No sudo, no context flags: every query runs as the caller, so
    ACLs and multi-company record rules apply.
  * Accounting figures (cost, accumulated depreciation, NBV) come from
    ``services.ledger.AssetLedger`` so they equal the reconciliation / roll-forward
    reports. Only POSTED lines count as accumulated depreciation.
  * Planned / Draft / Posted / Exception depreciation are reported separately.
"""
from collections import defaultdict

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError

from ..services.ledger import AssetLedger

END_OF_LIFE_MONTHS = 6
WARRANTY_DAYS = 30
TABLE_LIMIT = 10
MONTH_WINDOW_BACK = 5
MONTH_WINDOW_FWD = 6


class BuzAssetDashboardService(models.AbstractModel):
    _name = 'buz.asset.dashboard.service'
    _description = 'บริการข้อมูลแดชบอร์ดทรัพย์สิน'

    # ------------------------------------------------------------------ filters
    @api.model
    def _check_access(self):
        if not self.env.user.has_group('buz_asset_management.group_asset_user'):
            raise AccessError(_("คุณไม่มีสิทธิ์เข้าถึงแดชบอร์ดทรัพย์สิน"))

    @api.model
    def _parse_filters(self, filters):
        filters = filters or {}
        allowed = self.env.companies
        requested = filters.get('company_ids') or []
        companies = allowed.filtered(lambda c: c.id in requested) if requested else allowed
        companies = companies or allowed
        as_of = fields.Date.to_date(filters.get('as_of')) or fields.Date.context_today(self)
        return {
            'companies': companies,
            'as_of': as_of,
            'department_id': filters.get('department_id') or False,
            'category_id': filters.get('category_id') or False,
            'location_id': filters.get('location_id') or False,
            'operational_state': filters.get('operational_state') or False,
        }

    @api.model
    def _asset_matches(self, asset, f):
        return ((not f['department_id'] or asset.department_id.id == f['department_id'])
                and (not f['category_id'] or asset.category_id.id == f['category_id'])
                and (not f['location_id'] or asset.location_id.id == f['location_id'])
                and (not f['operational_state'] or asset.operational_state == f['operational_state']))

    @api.model
    def _filter_options(self, companies):
        scope = [('company_id', 'in', companies.ids + [False])]

        def options(model):
            return [{'id': r.id, 'name': r.display_name} for r in self.env[model].search(scope)]

        return {
            'companies': [{'id': c.id, 'name': c.name} for c in self.env.companies],
            'departments': options('hr.department'),
            'categories': options('buz.asset.category'),
            'locations': options('buz.asset.location'),
            'states': [{'id': k, 'name': v}
                       for k, v in self.env['buz.asset']._fields['operational_state'].selection],
        }

    # --------------------------------------------------------------------- main
    @api.model
    def get_data(self, filters=None):
        self._check_access()
        f = self._parse_filters(filters)
        companies, as_of = f['companies'], f['as_of']

        cost, accum, assets = {}, {}, self.env['buz.asset']
        for company in companies:
            ledger = AssetLedger(self.env, company, as_of)
            live = ledger.live_assets().filtered(lambda a: self._asset_matches(a, f))
            assets |= live
            for asset, value in ledger.cost_by_asset().items():
                if asset in live:
                    cost[asset.id] = value
            for asset, value in ledger.accumulated_by_asset().items():
                if asset in live:
                    accum[asset.id] = value
        nbv = {aid: cost[aid] - accum.get(aid, 0.0) for aid in cost}

        # Prefetch relational names once for the whole set (no N+1).
        assets.mapped('category_id.display_name')
        assets.mapped('department_id.display_name')
        assets.mapped('location_id.display_name')

        total_cost = sum(cost.values())
        total_accum = sum(accum.values())
        currencies = companies.mapped('currency_id')
        currency = (self.env.company.currency_id if self.env.company in companies else companies[:1].currency_id)

        pending = self._pending_depreciation(assets, as_of)
        warranty = self._warranty_rows(assets, as_of)

        return {
            'meta': {
                'as_of': fields.Date.to_string(as_of),
                'company_ids': companies.ids,
                'currency': {'id': currency.id, 'symbol': currency.symbol, 'position': currency.position,
                             'decimals': currency.decimal_places},
                'mixed_currency': len(currencies) > 1,
                'is_empty': not assets,
                'can': self._capabilities(),
            },
            'filters': self._filter_options(companies),
            'kpis': {
                'asset_count': len(assets),
                'gross_cost': total_cost,
                'accumulated_depreciation': total_accum,
                'nbv': total_cost - total_accum,
                'pending_depreciation': pending['total'],
                'pending_breakdown': pending['by_state'],
                'warranty_expiring': warranty['count'],
            },
            'charts': {
                'financial': {'cost': total_cost, 'accumulated': total_accum, 'nbv': total_cost - total_accum},
                'trend': self._trend(assets, as_of),
                'by_category': self._group_assets(assets, 'category_id', nbv),
                'monthly_depreciation': self._monthly_depreciation(assets, as_of),
                'by_status': self._status_counts(assets),
                'by_department': self._group_assets(assets, 'department_id', nbv),
            },
            'tables': {
                'end_of_life': self._end_of_life_rows(assets, as_of, nbv),
                'recent_activities': self._recent_activities(assets),
                'warranty': warranty['rows'],
                'pending_actions': self._pending_actions(assets, companies, as_of),
            },
        }

    # ------------------------------------------------------------------ pieces
    @api.model
    def _capabilities(self):
        user = self.env.user
        return {
            'create_asset': user.has_group('buz_asset_management.group_asset_officer'),
            'import_bill': user.has_group('buz_asset_management.group_asset_officer'),
            'depreciation': user.has_group('buz_asset_management.group_asset_accountant'),
            'transfer': user.has_group('buz_asset_management.group_asset_officer'),
            'qr': user.has_group('buz_asset_management.group_asset_user'),
            'audit': user.has_group('buz_asset_management.group_asset_officer'),
        }

    @api.model
    def _pending_depreciation(self, assets, as_of):
        """Planned / draft / exception depreciation not yet posted, due on or before as_of."""
        by_state = {'planned': 0.0, 'draft_move': 0.0, 'exception': 0.0}
        if assets:
            rows = self.env['buz.asset.depreciation.line']._read_group(
                [('asset_id', 'in', assets.ids), ('state', 'in', list(by_state)),
                 ('depreciation_date', '<=', as_of)],
                ['state'], ['planned_amount:sum'])
            for state, amount in rows:
                by_state[state] = amount or 0.0
        return {'by_state': by_state, 'total': sum(by_state.values())}

    @api.model
    def _group_assets(self, assets, field, nbv):
        buckets = defaultdict(lambda: {'count': 0, 'nbv': 0.0})
        for asset in assets:
            key = asset[field]
            bucket = buckets[key.id or 0]
            bucket['name'] = key.display_name or _('ไม่ระบุ')
            bucket['count'] += 1
            bucket['nbv'] += nbv.get(asset.id, 0.0)
        return sorted(buckets.values(), key=lambda b: -b['nbv'])

    @api.model
    def _status_counts(self, assets):
        labels = dict(self.env['buz.asset']._fields['operational_state'].selection)
        counts = defaultdict(int)
        for asset in assets:
            counts[asset.operational_state] += 1
        return [{'key': k, 'name': labels.get(k, k), 'count': v} for k, v in counts.items()]

    @api.model
    def _monthly_depreciation(self, assets, as_of):
        first = as_of.replace(day=1)
        start = first - relativedelta(months=MONTH_WINDOW_BACK)
        end = first + relativedelta(months=MONTH_WINDOW_FWD + 1)
        months = [start + relativedelta(months=i) for i in range(MONTH_WINDOW_BACK + MONTH_WINDOW_FWD + 1)]
        series = {'posted': defaultdict(float), 'planned': defaultdict(float),
                  'draft': defaultdict(float), 'exception': defaultdict(float)}
        key_map = {'posted': 'posted', 'planned': 'planned', 'draft_move': 'draft', 'exception': 'exception'}
        if assets:
            rows = self.env['buz.asset.depreciation.line']._read_group(
                [('asset_id', 'in', assets.ids), ('state', 'in', list(key_map)),
                 ('depreciation_date', '>=', start), ('depreciation_date', '<', end)],
                ['depreciation_date:month', 'state'], ['planned_amount:sum'])
            for month, state, amount in rows:
                series[key_map[state]][fields.Date.to_date(month)] += amount or 0.0
        return {
            'labels': [m.strftime('%Y-%m') for m in months],
            'series': {k: [v.get(m, 0.0) for m in months] for k, v in series.items()},
        }

    @api.model
    def _trend(self, assets, as_of):
        """Cost / posted accumulated depreciation / NBV at each of the last 12 month-ends.

        Same conventions as AssetLedger (cost by in-service date, posted lines by
        entry date net of reversals). One lines query for all months. Assets
        disposed before ``as_of`` are not in ``assets``, so past months exclude
        them; this is a trend of today's register, not a restated history.
        """
        month_ends = []
        first = as_of.replace(day=1)
        for i in range(11, -1, -1):
            end = first - relativedelta(months=i) + relativedelta(months=1, days=-1)
            month_ends.append(min(end, as_of))
        lines = self.env['buz.asset.depreciation.line'].search_read(
            [('asset_id', 'in', assets.ids), ('state', 'in', ('posted', 'reversed')), ('move_id', '!=', False),
             ('move_id.date', '<=', as_of)],
            ['planned_amount', 'move_id', 'reversal_move_id']) if assets else []
        move_ids = {l['move_id'][0] for l in lines} | {l['reversal_move_id'][0] for l in lines if l['reversal_move_id']}
        dates = {m['id']: m['date'] for m in self.env['account.move'].browse(list(move_ids)).read(['date'])}
        costs = [(a.in_service_date, a.gross_cost) for a in assets if a.in_service_date]
        labels, cost_s, accum_s = [], [], []
        for end in month_ends:
            labels.append(end.strftime('%Y-%m'))
            cost_s.append(sum(c for d, c in costs if d <= end))
            total = 0.0
            for line in lines:
                if dates[line['move_id'][0]] > end:
                    continue
                if line['reversal_move_id'] and dates[line['reversal_move_id'][0]] <= end:
                    continue
                total += line['planned_amount']
            accum_s.append(total)
        return {'labels': labels, 'cost': cost_s, 'accumulated': accum_s,
                'nbv': [c - a for c, a in zip(cost_s, accum_s)]}

    @api.model
    def _end_of_life_rows(self, assets, as_of, nbv):
        horizon = as_of + relativedelta(months=END_OF_LIFE_MONTHS)
        rows = []
        for asset in assets:
            if not asset.in_service_date or asset.useful_life_months <= 0:
                continue
            end = asset.in_service_date + relativedelta(months=asset.useful_life_months)
            if as_of <= end <= horizon:
                rows.append({'id': asset.id, 'code': asset.code, 'name': asset.name,
                             'category': asset.category_id.display_name, 'end_date': fields.Date.to_string(end),
                             'nbv': nbv.get(asset.id, 0.0)})
        return sorted(rows, key=lambda r: r['end_date'])[:TABLE_LIMIT]

    @api.model
    def _warranty_rows(self, assets, as_of):
        if not assets:
            return {'count': 0, 'rows': []}
        domain = [('asset_id', 'in', assets.ids), ('coverage_type', '=', 'warranty'),
                  ('date_end', '>=', as_of), ('date_end', '<=', as_of + relativedelta(days=WARRANTY_DAYS))]
        Coverage = self.env['buz.asset.coverage']
        count = Coverage.search_count(domain)
        recs = Coverage.search(domain, order='date_end, id', limit=TABLE_LIMIT)
        recs.mapped('asset_id.display_name')
        return {'count': count, 'rows': [
            {'id': c.id, 'asset_id': c.asset_id.id, 'asset': c.asset_id.display_name, 'reference': c.reference,
             'date_end': fields.Date.to_string(c.date_end), 'days_left': (c.date_end - as_of).days}
            for c in recs]}

    @api.model
    def _recent_activities(self, assets):
        if not assets:
            return []
        rows = []
        transfers = self.env['buz.asset.transfer'].search(
            [('asset_id', 'in', assets.ids)], order='write_date desc, id desc', limit=TABLE_LIMIT)
        disposals = self.env['buz.asset.disposal'].search(
            [('asset_id', 'in', assets.ids)], order='write_date desc, id desc', limit=TABLE_LIMIT)
        transfers.mapped('asset_id.display_name')
        disposals.mapped('asset_id.display_name')
        t_labels = dict(self.env['buz.asset.transfer']._fields['state'].selection)
        d_labels = dict(self.env['buz.asset.disposal']._fields['state'].selection)
        for t in transfers:
            rows.append({'when': fields.Datetime.to_string(t.write_date), 'type': _('โอนย้าย'),
                         'ref': t.name, 'asset': t.asset_id.display_name, 'status': t_labels.get(t.state, t.state),
                         'model': t._name, 'res_id': t.id})
        for d in disposals:
            rows.append({'when': fields.Datetime.to_string(d.write_date), 'type': _('จำหน่าย'),
                         'ref': d.name, 'asset': d.asset_id.display_name, 'status': d_labels.get(d.state, d.state),
                         'model': d._name, 'res_id': d.id})
        return sorted(rows, key=lambda r: r['when'], reverse=True)[:TABLE_LIMIT]

    @api.model
    def _pending_actions(self, assets, companies, as_of):
        """Counts + drill-down targets for work waiting on accounting (no amounts mutated)."""
        Line, Disposal, Asset = (self.env['buz.asset.depreciation.line'], self.env['buz.asset.disposal'],
                                 self.env['buz.asset'])
        ids = assets.ids
        items = [
            (_('ค่าเสื่อมครบกำหนดยังไม่ลงบัญชี'), Line._name,
             [('asset_id', 'in', ids), ('state', '=', 'planned'), ('depreciation_date', '<=', as_of)]),
            (_('ค่าเสื่อมติดข้อยกเว้น (ล็อกงวด/นโยบายวันที่)'), Line._name,
             [('asset_id', 'in', ids), ('state', '=', 'exception')]),
            (_('การจำหน่ายที่ยังไม่ลงบัญชี'), Disposal._name,
             [('asset_id', 'in', ids), ('state', 'in', ('draft', 'approved'))]),
            (_('ทรัพย์สินรอบันทึกเป็นสินทรัพย์'), Asset._name,
             [('company_id', 'in', companies.ids), ('accounting_state', '=', 'not_capitalized'),
              ('approval_state', '=', 'approved')]),
        ]
        return [{'label': label, 'model': model, 'domain': domain, 'count': self.env[model].search_count(domain)}
                for label, model, domain in items]
