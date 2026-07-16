import json
import logging

from odoo import models, fields, api
from datetime import date, timedelta

_logger = logging.getLogger(__name__)


class WarrantyDashboard(models.Model):
    _name = 'warranty.dashboard'
    _description = 'Warranty Dashboard'
    _log_access = True
    _rec_name = 'name'

    # Singleton identifier
    name = fields.Char(
        string='Dashboard Name',
        default='Warranty Dashboard',
        readonly=True
    )

    # Cache reference
    cache_id = fields.Many2one(
        'warranty.dashboard.cache',
        string='Cache Reference',
        readonly=True
    )

    # Cache status fields
    cache_status = fields.Selection(
        related='cache_id.cache_status',
        string='Cache Status'
    )
    last_update = fields.Datetime(
        related='cache_id.last_update',
        string='Last Update'
    )
    cache_valid_until = fields.Datetime(
        related='cache_id.cache_valid_until',
        string='Cache Valid Until'
    )
    update_duration = fields.Float(
        related='cache_id.update_duration',
        string='Update Duration (seconds)'
    )
    trigger_count = fields.Integer(
        related='cache_id.trigger_count',
        string='Trigger Count'
    )

    # KPI Fields (from cache)
    total_warranties = fields.Integer(
        string='Total Warranties',
        compute='_compute_from_cache',
    )
    active_warranties = fields.Integer(
        string='Active Warranties',
        compute='_compute_from_cache',
    )
    expired_warranties = fields.Integer(
        string='Expired Warranties',
        compute='_compute_from_cache',
    )
    near_expiry_warranties = fields.Integer(
        string='Near Expiry (30 days)',
        compute='_compute_from_cache',
    )
    claimed_warranties = fields.Integer(
        string='Claimed Warranties',
        compute='_compute_from_cache',
    )

    # Percentage Fields
    active_percentage = fields.Float(
        string='Active %',
        compute='_compute_from_cache',
    )
    expired_percentage = fields.Float(
        string='Expired %',
        compute='_compute_from_cache',
    )
    claimed_percentage = fields.Float(
        string='Claimed %',
        compute='_compute_from_cache',
    )

    # Additional metrics from cache
    claims_this_month = fields.Integer(
        string='Claims This Month',
        compute='_compute_from_cache'
    )
    claims_last_month = fields.Integer(
        string='Claims Last Month',
        compute='_compute_from_cache'
    )

    # Chart data fields (related to cache)
    warranty_status_chart = fields.Text(
        related='cache_id.warranty_status_chart',
        string='Warranty Status Chart'
    )
    claims_trend_chart = fields.Text(
        related='cache_id.claims_trend_chart',
        string='Claims Trend Chart'
    )
    monthly_comparison_chart = fields.Text(
        related='cache_id.monthly_comparison_chart',
        string='Monthly Comparison Chart'
    )
    top_products_chart = fields.Text(
        related='cache_id.top_products_chart',
        string='Top Products Chart'
    )
    top_customers_chart = fields.Text(
        related='cache_id.top_customers_chart',
        string='Top Customers Chart'
    )
    claim_types_chart = fields.Text(
        related='cache_id.claim_types_chart',
        string='Claim Types Chart'
    )
    warranty_expiry_chart = fields.Text(
        related='cache_id.warranty_expiry_chart',
        string='Warranty Expiry Chart'
    )

    # Filter fields for embedded lists
    active_warranty_ids = fields.Many2many(
        'warranty.card',
        string='Active Warranty Cards',
        compute='_compute_filtered_warranties'
    )
    expired_warranty_ids = fields.Many2many(
        'warranty.card',
        string='Expired Warranty Cards',
        compute='_compute_filtered_warranties'
    )
    near_expiry_warranty_ids = fields.Many2many(
        'warranty.card',
        string='Near Expiry Warranty Cards',
        compute='_compute_filtered_warranties'
    )

    # -------------------------------------------------------
    # Core helpers
    # -------------------------------------------------------

    @api.model
    def get_or_create_dashboard(self):
        """Get existing dashboard record or create singleton."""
        dashboard = self.search([], limit=1)
        if not dashboard:
            cache = self.env['warranty.dashboard.cache'].get_or_create_cache()
            dashboard = self.create({
                'cache_id': cache.id,
            })
        else:
            if not dashboard.cache_id:
                cache = self.env['warranty.dashboard.cache'].get_or_create_cache()
                dashboard.cache_id = cache.id
            elif dashboard.cache_id.cache_status != 'valid':
                dashboard.cache_id._update_all_metrics()
        return dashboard

    @api.model
    def action_open_dashboard(self):
        """Action to open the dashboard – always opens the singleton record."""
        dashboard = self.get_or_create_dashboard()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Warranty Dashboard',
            'res_model': 'warranty.dashboard',
            'res_id': dashboard.id,
            'view_mode': 'form',
            'view_id': self.env.ref('buz_warranty_management.view_warranty_dashboard_form').id,
            'target': 'current',
            'context': {
                'form_view_initial_mode': 'edit',
            },
        }

    # -------------------------------------------------------
    # Compute methods
    # -------------------------------------------------------

    @api.depends('cache_id')
    def _compute_from_cache(self):
        """Get values from cache instead of computing."""
        for record in self:
            try:
                if record.cache_id and record.cache_id.cache_status == 'valid':
                    cache = record.cache_id
                    record.total_warranties = cache.total_warranties
                    record.active_warranties = cache.active_warranties
                    record.expired_warranties = cache.expired_warranties
                    record.near_expiry_warranties = cache.near_expiry_warranties
                    record.claimed_warranties = cache.claimed_warranties
                    record.active_percentage = cache.active_percentage
                    record.expired_percentage = cache.expired_percentage
                    record.claimed_percentage = cache.claimed_percentage
                    record.claims_this_month = cache.claims_this_month
                    record.claims_last_month = cache.claims_last_month
                else:
                    record._compute_kpis_fallback()
                    record._compute_percentages_fallback()
            except Exception as e:
                _logger.error("Error in _compute_from_cache for dashboard %s: %s",
                              record.id, str(e))
                raise

    def _compute_kpis_fallback(self):
        """Fallback method for real-time calculation."""
        for record in self:
            try:
                record.total_warranties = self.env['warranty.card'].search_count([])
                record.active_warranties = self.env['warranty.card'].search_count([
                    ('state', '=', 'active')
                ])
                today = fields.Date.today()
                record.expired_warranties = self.env['warranty.card'].search_count([
                    '|',
                    ('state', '=', 'expired'),
                    ('end_date', '<', today)
                ])
                near_expiry_date = today + timedelta(days=30)
                record.near_expiry_warranties = self.env['warranty.card'].search_count([
                    ('state', '=', 'active'),
                    ('end_date', '>=', today),
                    ('end_date', '<=', near_expiry_date)
                ])
                record.claimed_warranties = self.env['warranty.card'].search_count([
                    ('claim_count', '>', 0)
                ])
                record.claims_this_month = self.env['service.receipt'].search_count([
                    ('request_date', '>=', fields.Date.today().replace(day=1)),
                    ('service_case_type', '=', 'replacement'),
                ])

                if today.month == 1:
                    last_month_start = today.replace(year=today.year - 1, month=12, day=1)
                else:
                    last_month_start = today.replace(month=today.month - 1, day=1)
                last_month_end = today.replace(day=1) - timedelta(days=1)
                record.claims_last_month = self.env['service.receipt'].search_count([
                    ('request_date', '>=', last_month_start),
                    ('request_date', '<=', last_month_end),
                    ('service_case_type', '=', 'replacement'),
                ])
            except Exception as e:
                _logger.error("Error in _compute_kpis_fallback for dashboard %s: %s",
                              record.id, str(e))
                raise

    def _compute_percentages_fallback(self):
        """Fallback method for percentage calculation."""
        for record in self:
            if record.total_warranties > 0:
                record.active_percentage = (record.active_warranties / record.total_warranties) * 100
                record.expired_percentage = (record.expired_warranties / record.total_warranties) * 100
                record.claimed_percentage = (record.claimed_warranties / record.total_warranties) * 100
            else:
                record.active_percentage = 0
                record.expired_percentage = 0
                record.claimed_percentage = 0

    @api.depends()
    def _compute_filtered_warranties(self):
        """Compute filtered warranty lists for embedded views."""
        for record in self:
            today = fields.Date.today()
            near_expiry_date = today + timedelta(days=30)

            record.active_warranty_ids = self.env['warranty.card'].search([
                ('state', '=', 'active')
            ], limit=100)

            record.expired_warranty_ids = self.env['warranty.card'].search([
                '|',
                ('state', '=', 'expired'),
                ('end_date', '<', today)
            ], limit=100)

            record.near_expiry_warranty_ids = self.env['warranty.card'].search([
                ('state', '=', 'active'),
                ('end_date', '>=', today),
                ('end_date', '<=', near_expiry_date)
            ], limit=100)

    # -------------------------------------------------------
    # Cache actions
    # -------------------------------------------------------

    def action_refresh_cache(self):
        """Manual cache refresh with user feedback."""
        self.ensure_one()

        if not self.cache_id:
            self.cache_id = self.env['warranty.dashboard.cache'].create({})

        if self.cache_id.is_updating:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Update in Progress',
                    'message': 'Dashboard is already updating. Please wait...',
                    'type': 'warning',
                    'sticky': False,
                }
            }

        self.cache_id._update_all_metrics()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Refresh Complete',
                'message': 'Dashboard data has been updated.',
                'type': 'success',
                'sticky': False,
            }
        }

    def action_force_refresh(self):
        """Force complete refresh of all data."""
        self.ensure_one()

        if not self.cache_id:
            self.cache_id = self.env['warranty.dashboard.cache'].create({})

        self.cache_id.write({
            'cache_status': 'expired',
            'cache_valid_until': fields.Datetime.now() - timedelta(hours=1)
        })

        self.cache_id._update_all_metrics()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Force Refresh Complete',
                'message': 'Dashboard data has been force-refreshed.',
                'type': 'success',
                'sticky': False,
            }
        }

    def action_rebuild_cache(self):
        """Completely rebuild the cache from scratch."""
        self.ensure_one()
        try:
            if self.cache_id:
                self.cache_id.unlink()
                self.cache_id = False

            self.cache_id = self.env['warranty.dashboard.cache'].create({})
            self.cache_id._update_all_metrics()
            self._compute_from_cache()

            _logger.info("Cache rebuild completed successfully")

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Cache Rebuilt',
                    'message': 'Dashboard cache has been completely rebuilt.',
                    'type': 'success',
                    'sticky': False,
                }
            }
        except Exception as e:
            _logger.error("Error rebuilding cache: %s", str(e))
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Cache Rebuild Failed',
                    'message': 'Error rebuilding cache: %s' % str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }

    # -------------------------------------------------------
    # Navigation actions
    # -------------------------------------------------------

    def action_view_active_warranties(self):
        self.ensure_one()
        return self.env.ref('buz_warranty_management.action_warranty_card_active').read()[0]

    def action_view_expired_warranties(self):
        self.ensure_one()
        return self.env.ref('buz_warranty_management.action_warranty_card_expired').read()[0]

    def action_view_near_expiry_warranties(self):
        self.ensure_one()
        return self.env.ref('buz_warranty_management.action_warranty_card_near_expiry').read()[0]

    def action_view_claimed_warranties(self):
        self.ensure_one()
        action = self.env.ref('buz_warranty_management.action_warranty_card').read()[0]
        action['domain'] = [('claim_count', '>', 0)]
        return action

    def action_view_all_warranties(self):
        self.ensure_one()
        return self.env.ref('buz_warranty_management.action_warranty_card').read()[0]

    # -------------------------------------------------------
    # RPC endpoints (for new client-action OWL dashboard)
    # -------------------------------------------------------

    @api.model
    def _ensure_cache_valid(self):
        """Ensure cache is valid, refresh if not."""
        cache = self.env['warranty.dashboard.cache']
        record = cache.search([], limit=1) or cache.create({})
        if record.cache_status != 'valid':
            record._update_all_metrics()
        elif record.cache_valid_until and record.cache_valid_until < fields.Datetime.now():
            record._update_all_metrics()
        return record

    @api.model
    def _build_warranty_domain(self, filters):
        """Build search domain for warranty.card from filters."""
        domain = []
        if filters.get('date_from'):
            domain.append(('create_date', '>=', filters['date_from']))
        if filters.get('date_to'):
            domain.append(('create_date', '<=', filters['date_to'] + ' 23:59:59'))
        if filters.get('product_id'):
            domain.append(('product_id', '=', int(filters['product_id'])))
        if filters.get('customer_id'):
            domain.append(('partner_id', '=', int(filters['customer_id'])))
        return domain

    @api.model
    def _build_claim_domain(self, filters):
        """Build search domain for Service Receipt claims from filters."""
        domain = []
        if filters.get('date_from'):
            domain.append(('request_date', '>=', filters['date_from']))
        if filters.get('date_to'):
            domain.append(('request_date', '<=', filters['date_to']))
        if filters.get('product_id'):
            domain.append(('warranty_card_id.product_id', '=', int(filters['product_id'])))
        if filters.get('customer_id'):
            domain.append(('warranty_card_id.partner_id', '=', int(filters['customer_id'])))
        return domain

    @api.model
    def _has_active_filters(self, filters):
        """Check if any non-default filter is set."""
        return bool(filters.get('date_from') or filters.get('date_to')
                    or filters.get('product_id') or filters.get('customer_id'))

    @api.model
    def _compute_filtered_kpis(self, filters):
        """Compute KPIs directly from models with filter domain."""
        w_domain = self._build_warranty_domain(filters)
        c_domain = self._build_claim_domain(filters)
        today = fields.Date.today()
        near_expiry = today + timedelta(days=30)

        card = self.env['warranty.card']
        claim = self.env['service.receipt']

        all_ids = card.search(w_domain)
        total = len(all_ids)
        active = len(all_ids.filtered(lambda r: r.state == 'active'))
        expired = len(all_ids.filtered(
            lambda r: r.state == 'expired' or (r.end_date and r.end_date < today)
        ))
        near_exp = len(all_ids.filtered(
            lambda r: r.state == 'active' and r.end_date and today <= r.end_date <= near_expiry
        ))
        claimed = len(all_ids.filtered(lambda r: r.claim_count > 0))

        active_pct = (active / total * 100) if total else 0
        expired_pct = (expired / total * 100) if total else 0
        claimed_pct = (claimed / total * 100) if total else 0

        first_this = today.replace(day=1)
        c_domain_this = c_domain + [('request_date', '>=', first_this)]
        claims_this = claim.search_count(c_domain_this)

        if today.month == 1:
            first_last = today.replace(year=today.year - 1, month=12, day=1)
        else:
            first_last = today.replace(month=today.month - 1, day=1)
        last_day_last = today.replace(day=1) - timedelta(days=1)
        c_domain_last = c_domain + [('request_date', '>=', first_last), ('request_date', '<=', last_day_last)]
        claims_last = claim.search_count(c_domain_last)

        return {
            'total_warranties': total,
            'active_warranties': active,
            'expired_warranties': expired,
            'near_expiry_warranties': near_exp,
            'claimed_warranties': claimed,
            'active_percentage': active_pct,
            'expired_percentage': expired_pct,
            'claimed_percentage': claimed_pct,
            'claims_this_month': claims_this,
            'claims_last_month': claims_last,
        }

    @api.model
    def _compute_filtered_status_chart(self, filters):
        """Compute warranty status pie chart data with filters."""
        domain = self._build_warranty_domain(filters)
        card = self.env['warranty.card']
        all_ids = card.search(domain)
        states = {}
        for r in all_ids:
            st = r.state
            states[st] = states.get(st, 0) + 1
        color_map = {'draft': '#6b7280', 'active': '#10b981', 'expired': '#ef4444', 'cancelled': '#f59e0b'}
        return [{'label': k.title(), 'value': v, 'color': color_map.get(k, '#6366f1')}
                for k, v in sorted(states.items(), key=lambda x: -x[1])]

    @api.model
    def _compute_filtered_trend(self, filters, months=12):
        """Compute claims trend data with filters."""
        domain = self._build_claim_domain(filters)
        claim = self.env['service.receipt']
        today = fields.Date.today()
        cutoff = today - timedelta(days=months * 30)
        domain.append(('request_date', '>=', cutoff))

        results = claim.search(domain, order='request_date')
        monthly = {}
        for r in results:
            key = r.request_date.strftime('%b %Y') if r.request_date else 'Unknown'
            if key not in monthly:
                monthly[key] = {'period': key, 'under_warranty': 0, 'out_of_warranty': 0}
            if r.is_under_warranty:
                monthly[key]['under_warranty'] += 1
            else:
                monthly[key]['out_of_warranty'] += 1
        return sorted(monthly.values(), key=lambda x: x['period'])

    @api.model
    def _compute_filtered_monthly_comparison(self, filters, months=12):
        """Compute monthly comparison with filters."""
        w_domain = self._build_warranty_domain(filters)
        c_domain = self._build_claim_domain(filters)
        card = self.env['warranty.card']
        claim = self.env['service.receipt']
        today = fields.Date.today()
        monthly = {}
        for i in range(months - 1, -1, -1):
            m_start = today - timedelta(days=30 * i)
            key = m_start.strftime('%b %Y')
            monthly[key] = {'period': key, 'warranties': 0, 'claims': 0}

        for r in card.search(w_domain + [('create_date', '>=', today - timedelta(days=months * 30))]):
            key = r.create_date.strftime('%b %Y') if r.create_date else 'Unknown'
            if key in monthly:
                monthly[key]['warranties'] += 1

        for r in claim.search(c_domain + [('request_date', '>=', today - timedelta(days=months * 30))]):
            key = r.request_date.strftime('%b %Y') if r.request_date else 'Unknown'
            if key in monthly:
                monthly[key]['claims'] += 1

        return sorted(monthly.values(), key=lambda x: x['period'])

    @api.model
    def get_dashboard_data(self, filters=None):
        """Return complete dashboard data as structured dict (for JSON RPC).

        When filters are active, computes data directly from models.
        With default filters, returns the global cached data (fast path).
        """
        if filters is None:
            filters = {}

        if self._has_active_filters(filters):
            # Filtered path: compute directly from models
            return {
                'kpi': self._compute_filtered_kpis(filters),
                'warranty_status': self._compute_filtered_status_chart(filters),
                'claims_trend': self._compute_filtered_trend(filters),
                'monthly_comparison': self._compute_filtered_monthly_comparison(filters),
                'top_products': [],
                'top_customers': [],
                'claim_types': [],
                'warranty_expiry': [],
                'recent_warranties': [],
            }

        # Default path: use global cache
        cache = self._ensure_cache_valid()

        def _parse_json_blob(field_val):
            if not field_val:
                return None
            try:
                return json.loads(field_val) if isinstance(field_val, str) else field_val
            except (json.JSONDecodeError, TypeError):
                return None

        def _extract_status_chart(blob):
            cfg = _parse_json_blob(blob)
            if not cfg or 'data' not in cfg:
                return []
            labels = cfg['data'].get('labels', [])
            datasets = cfg['data'].get('datasets', [{}])
            colors = (datasets[0] or {}).get('backgroundColor', [])
            values = (datasets[0] or {}).get('data', [])
            return [
                {'label': labels[i], 'value': values[i], 'color': colors[i] if i < len(colors) else '#6c757d'}
                for i in range(min(len(labels), len(values)))
            ]

        def _extract_trend_chart(blob, field_map):
            cfg = _parse_json_blob(blob)
            if not cfg or 'data' not in cfg:
                return []
            labels = cfg['data'].get('labels', [])
            datasets = cfg['data'].get('datasets', [])
            result = []
            for i, lbl in enumerate(labels):
                row = {'period': lbl}
                for ds in datasets:
                    ds_label = ds.get('label', '')
                    data = ds.get('data', [])
                    target_field = field_map.get(ds_label, ds_label.lower().replace(' ', '_'))
                    row[target_field] = data[i] if i < len(data) else 0
                result.append(row)
            return result

        def _extract_top_chart(blob, name_field='name'):
            cfg = _parse_json_blob(blob)
            if not cfg or 'data' not in cfg:
                return []
            labels = cfg['data'].get('labels', [])
            datasets = cfg['data'].get('datasets', [])
            result = []
            for i, lbl in enumerate(labels):
                row = {name_field: lbl}
                for ds in datasets:
                    ds_label = ds.get('label', '')
                    data = ds.get('data', [])
                    target_field = ds_label.lower().replace(' ', '_')
                    row[target_field] = data[i] if i < len(data) else 0
                result.append(row)
            return result

        def _extract_claim_types_chart(blob):
            cfg = _parse_json_blob(blob)
            if not cfg or 'data' not in cfg:
                return []
            labels = cfg['data'].get('labels', [])
            datasets = cfg['data'].get('datasets', [])
            result = []
            for i, lbl in enumerate(labels):
                row = {'period': lbl}
                for ds in datasets:
                    ds_label = ds.get('label', '').lower()
                    data = ds.get('data', [])
                    row[ds_label] = data[i] if i < len(data) else 0
                result.append(row)
            return result

        def _extract_expiry_chart(blob):
            cfg = _parse_json_blob(blob)
            if not cfg or 'data' not in cfg:
                return []
            labels = cfg['data'].get('labels', [])
            datasets = cfg['data'].get('datasets', [{}])
            data_values = (datasets[0] or {}).get('data', [])
            return [
                {'period': labels[i], 'count': data_values[i] if i < len(data_values) else 0}
                for i in range(len(labels))
            ]

        # Recent warranties
        recent_warranties = []
        try:
            warranty_model = self.env['warranty.card']
            whiny = warranty_model.search([], order='create_date desc', limit=10)
            for w in whiny:
                recent_warranties.append({
                    'id': w.id,
                    'name': w.name,
                    'partner_name': w.partner_id.name if w.partner_id else '',
                    'product_name': w.product_id.display_name if w.product_id else '',
                    'start_date': str(w.start_date) if w.start_date else '',
                    'end_date': str(w.end_date) if w.end_date else '',
                    'state': w.state,
                    'days_remaining': w.days_remaining,
                    'claim_count': w.claim_count,
                })
        except Exception:
            pass

        return {
            'kpi': {
                'total_warranties': cache.total_warranties,
                'active_warranties': cache.active_warranties,
                'expired_warranties': cache.expired_warranties,
                'near_expiry_warranties': cache.near_expiry_warranties,
                'claimed_warranties': cache.claimed_warranties,
                'active_percentage': cache.active_percentage,
                'expired_percentage': cache.expired_percentage,
                'claimed_percentage': cache.claimed_percentage,
                'claims_this_month': cache.claims_this_month,
                'claims_last_month': cache.claims_last_month,
            },
            'warranty_status': _extract_status_chart(cache.warranty_status_chart),
            'claims_trend': _extract_trend_chart(cache.claims_trend_chart, {'Under Warranty': 'under_warranty', 'Out of Warranty': 'out_of_warranty'}),
            'monthly_comparison': _extract_trend_chart(cache.monthly_comparison_chart, {'New Warranties': 'warranties', 'Claims': 'claims'}),
            'top_products': _extract_top_chart(cache.top_products_chart),
            'top_customers': _extract_top_chart(cache.top_customers_chart),
            'claim_types': _extract_claim_types_chart(cache.claim_types_chart),
            'warranty_expiry': _extract_expiry_chart(cache.warranty_expiry_chart),
            'recent_warranties': recent_warranties,
        }

    @api.model
    def get_filter_options(self):
        """Return filter dropdown options for dashboard.

        Safe approach: derive partner list from warranty.card records
        instead of searching non-stored computed fields.
        """
        # Products with warranty config (stored field -> safe to search)
        tmpl_ids = self.env['product.template'].sudo().search([
            ('warranty_type', '!=', False)
        ]).ids
        products = self.env['product.product'].sudo().search([
            ('product_tmpl_id', 'in', tmpl_ids)
        ], order='name')

        # Partners with warranty cards (via read_group, not computed field)
        card_model = self.env['warranty.card'].sudo()
        partner_data = card_model.read_group([], ['partner_id'], ['partner_id'])
        partner_ids = [p['partner_id'][0] for p in partner_data if p.get('partner_id')]
        customers = self.env['res.partner'].sudo().browse(partner_ids)

        return {
            'products': [{'id': p.id, 'name': p.display_name} for p in products],
            'customers': [{'id': c.id, 'name': c.name} for c in customers],
        }

    @api.model
    def refresh_dashboard_data(self, filters=None):
        """Force refresh cache then return data."""
        if filters is None:
            filters = {}
        cache = self.env['warranty.dashboard.cache'].search([], limit=1)
        if cache:
            cache.write({'cache_status': 'expired'})
        return self.get_dashboard_data(filters)

    @api.model
    def rebuild_cache(self):
        """Completely rebuild cache from scratch."""
        cache_model = self.env['warranty.dashboard.cache']
        cache_model.search([]).unlink()
        cache = cache_model.create({})
        cache._update_all_metrics()
        return {'status': 'ok', 'message': 'Cache rebuilt'}
