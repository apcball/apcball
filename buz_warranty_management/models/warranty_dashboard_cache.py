import logging
import time
import json
from datetime import datetime, timedelta

from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class WarrantyDashboardCache(models.Model):
    _name = 'warranty.dashboard.cache'
    _description = 'Warranty Dashboard Cache'
    _rec_name = 'last_update'
    _order = 'last_update desc'

    # KPI Fields (stored values)
    total_warranties = fields.Integer(string='Total Warranties')
    active_warranties = fields.Integer(string='Active Warranties')
    expired_warranties = fields.Integer(string='Expired Warranties')
    near_expiry_warranties = fields.Integer(string='Near Expiry (30 days)')
    claimed_warranties = fields.Integer(string='Claimed Warranties')

    # Percentage Fields
    active_percentage = fields.Float(string='Active %', digits=(5, 2))
    expired_percentage = fields.Float(string='Expired %', digits=(5, 2))
    claimed_percentage = fields.Float(string='Claimed %', digits=(5, 2))

    # Additional Metrics
    claims_this_month = fields.Integer(string='Claims This Month')
    claims_last_month = fields.Integer(string='Claims Last Month')
    top_products = fields.Text(string='Top Products (JSON)')
    top_customers = fields.Text(string='Top Customers (JSON)')

    # Chart data fields (JSON format)
    warranty_status_chart = fields.Text(string='Warranty Status Chart Data')
    claims_trend_chart = fields.Text(string='Claims Trend Chart Data')
    monthly_comparison_chart = fields.Text(string='Monthly Comparison Chart Data')
    top_products_chart = fields.Text(string='Top Products Chart Data')
    top_customers_chart = fields.Text(string='Top Customers Chart Data')
    claim_types_chart = fields.Text(string='Claim Types Chart Data')
    warranty_expiry_chart = fields.Text(string='Warranty Expiry Chart Data')

    # Tracking Fields
    last_update = fields.Datetime(string='Last Updated', default=fields.Datetime.now)
    update_duration = fields.Float(string='Update Duration (seconds)')
    is_updating = fields.Boolean(string='Is Updating', default=False)

    # Cache validity
    cache_valid_until = fields.Datetime(string='Cache Valid Until')
    cache_status = fields.Selection([
        ('valid', 'Valid'),
        ('expired', 'Expired'),
        ('updating', 'Updating'),
        ('error', 'Error'),
    ], default='expired', string='Cache Status')

    # Trigger tracking
    last_trigger_type = fields.Char(string='Last Trigger Type')
    last_trigger_time = fields.Datetime(string='Last Trigger Time')
    trigger_count = fields.Integer(string='Trigger Count', default=0)

    # -------------------------------------------------------
    # Core helpers
    # -------------------------------------------------------

    @api.model
    def get_or_create_cache(self):
        """Get existing cache or create new one."""
        cache = self.search([], limit=1)
        if not cache:
            cache = self.create({})
            cache._update_all_metrics()
        elif cache.cache_status != 'valid':
            cache._update_all_metrics()
        return cache

    # -------------------------------------------------------
    # Metrics update — single consolidated write
    # -------------------------------------------------------

    def _update_all_metrics(self):
        """Update all cached metrics efficiently — single write at the end."""
        start_time = time.time()
        self.ensure_one()

        try:
            vals = {}
            today = fields.Date.today()
            near_expiry_date = today + timedelta(days=30)

            # --- Main KPIs ---
            self._cr.execute("""
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN state = 'active' THEN 1 END) as active,
                    COUNT(CASE WHEN state = 'expired' OR end_date < %s THEN 1 END) as expired,
                    COUNT(CASE WHEN state = 'active' AND end_date >= %s
                             AND end_date <= %s THEN 1 END) as near_expiry,
                    COUNT(CASE WHEN EXISTS(
                        SELECT 1 FROM service_receipt wc
                        WHERE wc.warranty_card_id = warranty_card.id
                    ) THEN 1 END) as claimed
                FROM warranty_card
            """, (today, today, near_expiry_date))
            result = self._cr.dictfetchone()

            vals.update({
                'total_warranties': result['total'],
                'active_warranties': result['active'],
                'expired_warranties': result['expired'],
                'near_expiry_warranties': result['near_expiry'],
                'claimed_warranties': result['claimed'],
            })

            # Percentages
            if result['total'] > 0:
                vals.update({
                    'active_percentage': (result['active'] / result['total']) * 100,
                    'expired_percentage': (result['expired'] / result['total']) * 100,
                    'claimed_percentage': (result['claimed'] / result['total']) * 100,
                })
            else:
                vals.update({
                    'active_percentage': 0,
                    'expired_percentage': 0,
                    'claimed_percentage': 0,
                })

            # --- Claims metrics ---
            first_day_this_month = today.replace(day=1)
            self._cr.execute(
                "SELECT COUNT(*) FROM service_receipt WHERE request_date >= %s AND service_case_type = 'replacement'",
                (first_day_this_month,),
            )
            claims_this_month = self._cr.fetchone()[0]

            if today.month == 1:
                first_day_last_month = today.replace(year=today.year - 1, month=12, day=1)
            else:
                first_day_last_month = today.replace(month=today.month - 1, day=1)
            last_day_last_month = today.replace(day=1) - timedelta(days=1)
            self._cr.execute(
                "SELECT COUNT(*) FROM service_receipt WHERE request_date >= %s AND request_date <= %s AND service_case_type = 'replacement'",
                (first_day_last_month, last_day_last_month),
            )
            claims_last_month = self._cr.fetchone()[0]

            vals.update({
                'claims_this_month': claims_this_month,
                'claims_last_month': claims_last_month,
            })

            # --- Top products / customers ---
            self._cr.execute("""
                SELECT pt.name, COUNT(*) as count
                FROM warranty_card wc
                JOIN product_product pp ON wc.product_id = pp.id
                JOIN product_template pt ON pp.product_tmpl_id = pt.id
                GROUP BY pt.name
                ORDER BY count DESC LIMIT 10
            """)
            vals['top_products'] = json.dumps(self._cr.fetchall())

            self._cr.execute("""
                SELECT rp.name, COUNT(*) as count
                FROM warranty_card wc
                JOIN res_partner rp ON wc.partner_id = rp.id
                GROUP BY rp.name
                ORDER BY count DESC LIMIT 10
            """)
            vals['top_customers'] = json.dumps(self._cr.fetchall())

            # --- Chart data ---
            vals['warranty_status_chart'] = self._build_warranty_status_chart()
            vals['claims_trend_chart'] = self._build_claims_trend_chart()
            vals['monthly_comparison_chart'] = self._build_monthly_comparison_chart()
            vals['top_products_chart'] = self._build_top_products_chart()
            vals['top_customers_chart'] = self._build_top_customers_chart()
            vals['claim_types_chart'] = self._build_claim_types_chart()
            vals['warranty_expiry_chart'] = self._build_warranty_expiry_chart()

            # --- Final status ---
            update_duration = time.time() - start_time
            vals.update({
                'is_updating': False,
                'cache_status': 'valid',
                'cache_valid_until': fields.Datetime.now() + timedelta(minutes=15),
                'update_duration': update_duration,
                'last_update': fields.Datetime.now(),
            })

            # Single write for everything
            self.write(vals)

            _logger.info("Dashboard cache updated in %.2f seconds", update_duration)

        except Exception as e:
            _logger.error("Error updating dashboard cache: %s", str(e))
            self.write({
                'is_updating': False,
                'cache_status': 'error',
            })

    # -------------------------------------------------------
    # Chart builders — return JSON strings (no write)
    # -------------------------------------------------------

    def _build_warranty_status_chart(self):
        self._cr.execute("SELECT state, COUNT(*) FROM warranty_card GROUP BY state")
        results = self._cr.fetchall()
        colors = {
            'draft': '#6c757d', 'active': '#28a745',
            'expired': '#dc3545', 'cancelled': '#ffc107',
        }
        return json.dumps({
            'type': 'pie',
            'data': {
                'labels': [s.title() for s, _ in results],
                'datasets': [{
                    'data': [c for _, c in results],
                    'backgroundColor': [colors.get(s, '#007bff') for s, _ in results],
                    'borderWidth': 2,
                    'borderColor': '#ffffff',
                }],
            },
            'options': {
                'responsive': True,
                'maintainAspectRatio': False,
                'plugins': {'legend': {'position': 'bottom', 'labels': {'padding': 10, 'usePointStyle': True}}},
            },
        })

    def _build_claims_trend_chart(self, months=12):
        months_back = fields.Date.today() - timedelta(days=months * 30)
        self._cr.execute("""
            SELECT DATE_TRUNC('month', request_date) AS month,
                   COUNT(*) AS cnt,
                   COUNT(CASE WHEN is_under_warranty THEN 1 END) AS w_claims,
                   COUNT(CASE WHEN NOT is_under_warranty THEN 1 END) AS o_claims
            FROM service_receipt WHERE request_date >= %s AND service_case_type = 'replacement'
            GROUP BY month ORDER BY month
        """, (months_back,))
        results = self._cr.fetchall()
        return json.dumps({
            'type': 'line',
            'data': {
                'labels': [r[0].strftime('%b %Y') for r in results],
                'datasets': [
                    {'label': 'Under Warranty', 'data': [r[2] for r in results],
                     'borderColor': '#28a745', 'backgroundColor': 'rgba(40,167,69,0.1)', 'fill': True, 'tension': 0.4},
                    {'label': 'Out of Warranty', 'data': [r[3] for r in results],
                     'borderColor': '#dc3545', 'backgroundColor': 'rgba(220,53,69,0.1)', 'fill': True, 'tension': 0.4},
                ],
            },
            'options': {'responsive': True, 'maintainAspectRatio': False,
                        'scales': {'y': {'beginAtZero': True}},
                        'plugins': {'legend': {'position': 'top'}}},
        })

    def _build_monthly_comparison_chart(self, months=12):
        d = fields.Date.today() - timedelta(days=months * 30)
        self._cr.execute("""
            WITH mw AS (SELECT DATE_TRUNC('month', create_date) AS m, COUNT(*) AS c
                        FROM warranty_card WHERE create_date >= %s GROUP BY m),
                 mc AS (SELECT DATE_TRUNC('month', request_date) AS m, COUNT(*) AS c
                        FROM service_receipt WHERE request_date >= %s AND service_case_type = 'replacement' GROUP BY m)
            SELECT COALESCE(w.m, c.m),
                   COALESCE(w.c, 0), COALESCE(c.c, 0)
            FROM mw w FULL OUTER JOIN mc c ON w.m = c.m ORDER BY 1
        """, (d, d))
        results = self._cr.fetchall()
        return json.dumps({
            'type': 'bar',
            'data': {
                'labels': [r[0].strftime('%b %Y') for r in results],
                'datasets': [
                    {'label': 'New Warranties', 'data': [r[1] for r in results],
                     'backgroundColor': '#007bff', 'borderWidth': 1},
                    {'label': 'Claims', 'data': [r[2] for r in results],
                     'backgroundColor': '#ffc107', 'borderWidth': 1},
                ],
            },
            'options': {'responsive': True, 'scales': {'y': {'beginAtZero': True}},
                        'plugins': {'legend': {'position': 'top'}}},
        })

    def _build_top_products_chart(self, limit=10):
        self._cr.execute("""
            SELECT pt.name, COUNT(wc.id), COUNT(wc2.id)
            FROM warranty_card wc
            JOIN product_product pp ON wc.product_id = pp.id
            JOIN product_template pt ON pp.product_tmpl_id = pt.id
            LEFT JOIN service_receipt wc2 ON wc.id = wc2.warranty_card_id
            GROUP BY pt.name ORDER BY 2 DESC LIMIT %s
        """, (limit,))
        results = self._cr.fetchall()
        return json.dumps({
            'type': 'bar',
            'data': {
                'labels': [r[0] for r in results],
                'datasets': [
                    {'label': 'Warranties', 'data': [r[1] for r in results], 'backgroundColor': '#007bff'},
                    {'label': 'Claims', 'data': [r[2] for r in results], 'backgroundColor': '#dc3545'},
                ],
            },
            'options': {'indexAxis': 'y', 'responsive': True,
                        'scales': {'x': {'beginAtZero': True}},
                        'plugins': {'legend': {'position': 'top'}}},
        })

    def _build_top_customers_chart(self, limit=10):
        self._cr.execute("""
            SELECT rp.name, COUNT(wc.id), COUNT(wc2.id)
            FROM warranty_card wc
            JOIN res_partner rp ON wc.partner_id = rp.id
            LEFT JOIN service_receipt wc2 ON wc.id = wc2.warranty_card_id
            GROUP BY rp.name ORDER BY 2 DESC LIMIT %s
        """, (limit,))
        results = self._cr.fetchall()
        return json.dumps({
            'type': 'bar',
            'data': {
                'labels': [r[0] for r in results],
                'datasets': [
                    {'label': 'Warranties', 'data': [r[1] for r in results], 'backgroundColor': '#28a745'},
                    {'label': 'Claims', 'data': [r[2] for r in results], 'backgroundColor': '#ffc107'},
                ],
            },
            'options': {'indexAxis': 'y', 'responsive': True,
                        'scales': {'x': {'beginAtZero': True}},
                        'plugins': {'legend': {'position': 'top'}}},
        })

    def _build_claim_types_chart(self, months=12):
        d = fields.Date.today() - timedelta(days=months * 30)
        self._cr.execute("""
            SELECT DATE_TRUNC('month', request_date) AS m, service_case_type, COUNT(*)
            FROM service_receipt WHERE request_date >= %s AND service_case_type = 'replacement'
            GROUP BY m, service_case_type ORDER BY m, service_case_type
        """, (d,))
        results = self._cr.fetchall()
        months_list = sorted(set(r[0] for r in results))
        colors = {'replacement': '#28a745'}
        datasets = []
        for ct in ['replacement']:
            data = [next((r[2] for r in results if r[0] == m and r[1] == ct), 0) for m in months_list]
            datasets.append({
                'label': ct.title(), 'data': data,
                'backgroundColor': colors[ct], 'borderColor': colors[ct], 'fill': True,
            })
        return json.dumps({
            'type': 'line',
            'data': {'labels': [m.strftime('%b %Y') for m in months_list], 'datasets': datasets},
            'options': {'responsive': True,
                        'scales': {'y': {'beginAtZero': True, 'stacked': True}, 'x': {'stacked': True}},
                        'plugins': {'legend': {'position': 'top'}}},
        })

    def _build_warranty_expiry_chart(self, months=12):
        today = fields.Date.today()
        future = today + timedelta(days=months * 30)
        self._cr.execute("""
            SELECT DATE_TRUNC('month', end_date), COUNT(*)
            FROM warranty_card WHERE end_date >= %s AND end_date <= %s
            GROUP BY 1 ORDER BY 1
        """, (today, future))
        results = self._cr.fetchall()
        return json.dumps({
            'type': 'bar',
            'data': {
                'labels': [r[0].strftime('%b %Y') for r in results],
                'datasets': [{'label': 'Expiring', 'data': [r[1] for r in results],
                              'backgroundColor': '#dc3545', 'borderWidth': 1}],
            },
            'options': {'responsive': True, 'scales': {'y': {'beginAtZero': True}},
                        'plugins': {'legend': {'display': False}}},
        })

    # -------------------------------------------------------
    # Cron / trigger
    # -------------------------------------------------------

    @api.model
    def _cron_update_dashboard_cache(self):
        """Scheduled job to update dashboard cache."""
        _logger.info("Starting scheduled dashboard cache update")
        cache = self.search([], limit=1) or self.create({})
        cache._update_all_metrics()

    @api.model
    def _trigger_update(self, trigger_type, records=None):
        """Handle cache update triggers — synchronous with debounce."""
        _logger.info("Cache update triggered: %s", trigger_type)

        cache = self.search([], limit=1)
        if not cache:
            cache = self.create({})

        cache.write({
            'last_trigger_type': trigger_type,
            'last_trigger_time': fields.Datetime.now(),
            'trigger_count': cache.trigger_count + 1,
        })

        # Debounce: skip if last update was within 2 minutes
        if cache.last_update:
            elapsed = (fields.Datetime.now() - cache.last_update).total_seconds()
            if elapsed < 120:
                _logger.debug("Skipping update — last update was %.0fs ago", elapsed)
                return

        cache._update_all_metrics()
