from odoo import models, fields, api
import logging
import time
import threading
import json
from datetime import datetime, timedelta

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
    warranty_type_chart = fields.Text(string='Warranty Type Chart Data')
    claims_trend_chart = fields.Text(string='Claims Trend Chart Data')
    monthly_comparison_chart = fields.Text(string='Monthly Comparison Chart Data')
    top_products_chart = fields.Text(string='Top Products Chart Data')
    top_customers_chart = fields.Text(string='Top Customers Chart Data')
    claim_types_chart = fields.Text(string='Claim Types Chart Data')
    claim_resolution_chart = fields.Text(string='Claim Resolution Chart Data')
    warranty_expiry_chart = fields.Text(string='Warranty Expiry Chart Data')
    financial_impact_chart = fields.Text(string='Financial Impact Chart Data')
    
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

    @api.model
    def get_or_create_cache(self):
        """Get existing cache or create new one"""
        cache = self.search([], limit=1)
        if not cache:
            cache = self.create({})
            cache._update_all_metrics()
        elif cache.cache_status != 'valid':
            # Update if cache is invalid
            cache._update_all_metrics()
        return cache

    def _update_all_metrics(self):
        """Update all cached metrics efficiently"""
        start_time = time.time()
        
        try:
            # Use SQL queries for better performance - simplified for compatibility
            today = fields.Date.today()
            near_expiry_date = today + timedelta(days=30)
            
            self._cr.execute("""
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN state = 'active' THEN 1 END) as active,
                    COUNT(CASE WHEN state = 'expired' OR end_date < %s THEN 1 END) as expired,
                    COUNT(CASE WHEN state = 'active' AND end_date >= %s
                             AND end_date <= %s THEN 1 END) as near_expiry,
                    COUNT(CASE WHEN EXISTS(SELECT 1 FROM warranty_claim wc WHERE wc.warranty_card_id = warranty_card.id)
                             THEN 1 END) as claimed
                FROM warranty_card
            """, (today, today, near_expiry_date))
            
            result = self._cr.dictfetchone()
            
            # Update cache values
            self.write({
                'total_warranties': result['total'],
                'active_warranties': result['active'],
                'expired_warranties': result['expired'],
                'near_expiry_warranties': result['near_expiry'],
                'claimed_warranties': result['claimed'],
            })
            
            # Calculate percentages
            if result['total'] > 0:
                self.write({
                    'active_percentage': (result['active'] / result['total']) * 100,
                    'expired_percentage': (result['expired'] / result['total']) * 100,
                    'claimed_percentage': (result['claimed'] / result['total']) * 100,
                })
            
            # Update additional metrics
            self._update_additional_metrics()
            
            # Update cache status
            update_duration = time.time() - start_time
            self.write({
                'is_updating': False,
                'cache_status': 'valid',
                'cache_valid_until': fields.Datetime.now() + timedelta(minutes=15),
                'update_duration': update_duration,
                'last_update': fields.Datetime.now()
            })
            
            _logger.info(f"Dashboard cache updated in {update_duration:.2f} seconds")
            
        except Exception as e:
            _logger.error(f"Error updating dashboard cache: {str(e)}")
            self.write({
                'is_updating': False,
                'cache_status': 'error'
            })

    def _update_additional_metrics(self):
        """Update additional metrics like claims this month, top products, etc."""
        try:
            # Claims this month - use simpler date calculation
            _logger.debug("Executing claims_this_month query")
            today = fields.Date.today()
            first_day_this_month = today.replace(day=1)
            
            self._cr.execute("""
                SELECT COUNT(*) FROM warranty_claim
                WHERE claim_date >= %s
            """, (first_day_this_month,))
            claims_this_month_result = self._cr.fetchone()
            claims_this_month = claims_this_month_result[0] if claims_this_month_result else 0
            _logger.debug(f"Claims this month query result: {claims_this_month_result}")
            
            # Claims last month - use simpler date calculation
            _logger.debug("Executing claims_last_month query")
            if today.month == 1:
                first_day_last_month = today.replace(year=today.year-1, month=12, day=1)
                last_day_last_month = today.replace(day=1) - timedelta(days=1)
            else:
                first_day_last_month = today.replace(month=today.month-1, day=1)
                last_day_last_month = today.replace(day=1) - timedelta(days=1)
            
            self._cr.execute("""
                SELECT COUNT(*) FROM warranty_claim
                WHERE claim_date >= %s AND claim_date <= %s
            """, (first_day_last_month, last_day_last_month))
            claims_last_month_result = self._cr.fetchone()
            claims_last_month = claims_last_month_result[0] if claims_last_month_result else 0
            _logger.debug(f"Claims last month query result: {claims_last_month_result}")
            
            _logger.debug(f"Writing claims metrics: this_month={claims_this_month}, last_month={claims_last_month}")
            self.write({
                'claims_this_month': claims_this_month,
                'claims_last_month': claims_last_month,
            })
            _logger.debug(f"Successfully wrote claims metrics to cache {self.id}")
            
        except Exception as e:
            _logger.error(f"Error in _update_additional_metrics: {str(e)}")
            _logger.error(f"Cache ID: {self.id}")
            raise
        
        # Top products (JSON format)
        self._cr.execute("""
            SELECT pt.name, COUNT(*) as count
            FROM warranty_card wc
            JOIN product_product pp ON wc.product_id = pp.id
            JOIN product_template pt ON pp.product_tmpl_id = pt.id
            GROUP BY pt.name
            ORDER BY count DESC
            LIMIT 10
        """)
        top_products = json.dumps(self._cr.fetchall())
        
        # Top customers (JSON format)
        self._cr.execute("""
            SELECT rp.name, COUNT(*) as count
            FROM warranty_card wc
            JOIN res_partner rp ON wc.partner_id = rp.id
            GROUP BY rp.name
            ORDER BY count DESC
            LIMIT 10
        """)
        top_customers = json.dumps(self._cr.fetchall())
        
        self.write({
            'top_products': top_products,
            'top_customers': top_customers,
        })
        
        # Update chart data
        self._prepare_warranty_status_chart()
        self._prepare_claims_trend_chart()
        self._prepare_monthly_comparison_chart()
        self._prepare_top_products_chart()
        self._prepare_top_customers_chart()
        self._prepare_claim_types_chart()
        self._prepare_warranty_expiry_chart()

    @api.model
    def _cron_update_dashboard_cache(self):
        """Scheduled job to update dashboard cache"""
        _logger.info("Starting dashboard cache update")
        start_time = time.time()
        
        try:
            # Check if already updating
            if self.search([('is_updating', '=', True)]):
                _logger.warning("Cache update already in progress, skipping")
                return
            
            # Get or create cache record
            cache = self.search([], limit=1) or self.create({})
            
            # Mark as updating
            cache.write({
                'is_updating': True,
                'cache_status': 'updating'
            })
            
            # Update all metrics
            cache._update_all_metrics()
            
            # Mark as complete
            update_duration = time.time() - start_time
            cache.write({
                'is_updating': False,
                'cache_status': 'valid',
                'cache_valid_until': fields.Datetime.now() + timedelta(minutes=15),
                'update_duration': update_duration,
                'last_update': fields.Datetime.now()
            })
            
            _logger.info(f"Dashboard cache updated in {update_duration:.2f} seconds")
            
        except Exception as e:
            _logger.error(f"Error updating dashboard cache: {str(e)}")
            if cache:
                cache.write({
                    'is_updating': False,
                    'cache_status': 'error'
                })

    @api.model
    def _trigger_update(self, trigger_type, records=None):
        """Handle cache update triggers"""
        _logger.info(f"Cache update triggered: {trigger_type}")
        
        # Get or create cache
        cache = self.search([], limit=1)
        if not cache:
            cache = self.create({})
        
        # Update trigger info
        cache.write({
            'last_trigger_type': trigger_type,
            'last_trigger_time': fields.Datetime.now(),
            'trigger_count': cache.trigger_count + 1,
        })
        
        # Check if we should update immediately or debounce
        if cache._should_update_immediately(trigger_type):
            cache._update_all_metrics_async()
        else:
            # Schedule update with debounce
            cache._schedule_debounced_update()
    
    def _should_update_immediately(self, trigger_type):
        """Determine if update should be immediate"""
        # High priority triggers
        immediate_triggers = [
            'warranty_card_created',
            'warranty_card_deleted',
            'warranty_claim_created',
            'warranty_claim_deleted',
        ]
        
        if trigger_type in immediate_triggers:
            return True
        
        # Check if last update was recent (within 2 minutes)
        if self.last_update and (fields.Datetime.now() - self.last_update).seconds < 120:
            return False
        
        return True
    
    def _schedule_debounced_update(self):
        """Schedule debounced update to avoid too frequent updates"""
        # Cancel any existing scheduled update
        self.env['ir.cron'].search([
            ('name', '=', 'Debounced Dashboard Cache Update')
        ]).unlink()
        
        # Schedule new update in 2 minutes
        self.env['ir.cron'].create({
            'name': 'Debounced Dashboard Cache Update',
            'model_id': self.env.ref('buz_warranty_management.model_warranty_dashboard_cache').id,
            'state': 'code',
            'code': f'model.browse({self.id})._update_all_metrics_async()',
            'interval_number': 2,
            'interval_type': 'minutes',
            'numbercall': 1,
            'active': True,
            'doall': False,
        })
    
    def _update_all_metrics_async(self):
        """Update metrics asynchronously in background"""
        self.ensure_one()
        
        # Mark as updating
        self.write({
            'is_updating': True,
            'cache_status': 'updating'
        })
        
        # Use Odoo's background job if available, otherwise use thread
        if self.env['ir.module.module'].search([('name', '=', 'queue_job')], limit=1).state == 'installed':
            # Use queue_job if installed
            self.with_delay()._update_all_metrics_job()
        else:
            # Use simple thread
            import threading
            thread = threading.Thread(
                target=self._update_all_metrics_thread,
                args=(self.env.cr.dbname, self.id, self._context)
            )
            thread.daemon = True
            thread.start()
    
    @api.model
    def _update_all_metrics_thread(self, db_name, cache_id, context):
        """Thread-based update for metrics"""
        try:
            # New environment for the thread
            import odoo
            from odoo import registry as reg_module
            registry = reg_module.Registry(db_name)
            with registry.cursor() as cr:
                env = api.Environment(cr, odoo.SUPERUSER_ID, context or {})
                cache = env['warranty.dashboard.cache'].browse(cache_id)
                
                try:
                    cache._update_all_metrics()
                    cr.commit()
                except Exception as e:
                    _logger.error(f"Error in async cache update: {str(e)}")
                    import traceback
                    _logger.error(traceback.format_exc())
                    cache.write({
                        'is_updating': False,
                        'cache_status': 'error'
                    })
                    cr.commit()
        except Exception as e:
            _logger.error(f"Error in thread setup: {str(e)}")
            import traceback
            _logger.error(traceback.format_exc())
    
    def _prepare_warranty_status_chart(self):
        """Prepare data for warranty status pie chart"""
        self._cr.execute("""
            SELECT state, COUNT(*) as count
            FROM warranty_card
            GROUP BY state
        """)
        
        results = self._cr.fetchall()
        labels = []
        data = []
        colors = {
            'draft': '#6c757d',
            'active': '#28a745',
            'expired': '#dc3545',
            'cancelled': '#ffc107'
        }
        
        for state, count in results:
            labels.append(state.title())
            data.append(count)
        
        chart_data = {
            'type': 'pie',
            'data': {
                'labels': labels,
                'datasets': [{
                    'data': data,
                    'backgroundColor': [colors.get(r[0], '#007bff') for r in results],
                    'borderWidth': 2,
                    'borderColor': '#ffffff'
                }]
            },
            'options': {
                'responsive': True,
                'maintainAspectRatio': False,
                'plugins': {
                    'legend': {
                        'position': 'bottom',
                        'labels': {
                            'padding': 10,
                            'usePointStyle': True
                        }
                    }
                }
            }
        }
        
        self.warranty_status_chart = json.dumps(chart_data)
    
    
    def _prepare_claims_trend_chart(self, months=12):
        """Prepare data for claims trend line chart"""
        months_back_date = fields.Date.today() - timedelta(days=months*30)
        self._cr.execute("""
            SELECT
                DATE_TRUNC('month', claim_date) as month,
                COUNT(*) as claims_count,
                COUNT(CASE WHEN is_under_warranty THEN 1 END) as warranty_claims,
                COUNT(CASE WHEN NOT is_under_warranty THEN 1 END) as out_warranty_claims
            FROM warranty_claim
            WHERE claim_date >= %s
            GROUP BY DATE_TRUNC('month', claim_date)
            ORDER BY month
        """, (months_back_date,))
        
        results = self._cr.fetchall()
        labels = [r[0].strftime('%b %Y') for r in results]
        warranty_claims = [r[2] for r in results]
        out_warranty_claims = [r[3] for r in results]
        
        chart_data = {
            'type': 'line',
            'data': {
                'labels': labels,
                'datasets': [
                    {
                        'label': 'Under Warranty Claims',
                        'data': warranty_claims,
                        'borderColor': '#28a745',
                        'backgroundColor': 'rgba(40, 167, 69, 0.1)',
                        'fill': True,
                        'tension': 0.4
                    },
                    {
                        'label': 'Out of Warranty Claims',
                        'data': out_warranty_claims,
                        'borderColor': '#dc3545',
                        'backgroundColor': 'rgba(220, 53, 69, 0.1)',
                        'fill': True,
                        'tension': 0.4
                    }
                ]
            },
            'options': {
                'responsive': True,
                'maintainAspectRatio': False,
                'scales': {
                    'y': {'beginAtZero': True}
                },
                'plugins': {
                    'legend': {'position': 'top'}
                }
            }
        }
        
        self.claims_trend_chart = json.dumps(chart_data)
    
    
    def _prepare_monthly_comparison_chart(self, months=12):
        """Prepare data for monthly comparison bar chart"""
        months_back_date = fields.Date.today() - timedelta(days=months*30)
        self._cr.execute("""
            WITH monthly_warranties AS (
                SELECT
                    DATE_TRUNC('month', create_date) as month,
                    COUNT(*) as warranties_count
                FROM warranty_card
                WHERE create_date >= %s
                GROUP BY DATE_TRUNC('month', create_date)
            ),
            monthly_claims AS (
                SELECT
                    DATE_TRUNC('month', claim_date) as month,
                    COUNT(*) as claims_count
                FROM warranty_claim
                WHERE claim_date >= %s
                GROUP BY DATE_TRUNC('month', claim_date)
            )
            SELECT
                COALESCE(w.month, c.month) as month,
                COALESCE(w.warranties_count, 0) as warranties,
                COALESCE(c.claims_count, 0) as claims
            FROM monthly_warranties w
            FULL OUTER JOIN monthly_claims c ON w.month = c.month
            ORDER BY month
        """, (months_back_date, months_back_date))
        
        results = self._cr.fetchall()
        labels = [r[0].strftime('%b %Y') for r in results]
        warranties = [r[1] for r in results]
        claims = [r[2] for r in results]
        
        chart_data = {
            'type': 'bar',
            'data': {
                'labels': labels,
                'datasets': [
                    {
                        'label': 'New Warranties',
                        'data': warranties,
                        'backgroundColor': '#007bff',
                        'borderColor': '#0056b3',
                        'borderWidth': 1
                    },
                    {
                        'label': 'Claims',
                        'data': claims,
                        'backgroundColor': '#ffc107',
                        'borderColor': '#d39e00',
                        'borderWidth': 1
                    }
                ]
            },
            'options': {
                'responsive': True,
                'scales': {
                    'y': {'beginAtZero': True}
                },
                'plugins': {
                    'legend': {'position': 'top'}
                }
            }
        }
        
        self.monthly_comparison_chart = json.dumps(chart_data)
    
    
    def _prepare_top_products_chart(self, limit=10):
        """Prepare data for top products horizontal bar chart"""
        self._cr.execute("""
            SELECT
                pt.name,
                COUNT(wc.id) as warranty_count,
                COUNT(wc2.id) as claim_count
            FROM warranty_card wc
            JOIN product_product pp ON wc.product_id = pp.id
            JOIN product_template pt ON pp.product_tmpl_id = pt.id
            LEFT JOIN warranty_claim wc2 ON wc.id = wc2.warranty_card_id
            GROUP BY pt.name
            ORDER BY warranty_count DESC
            LIMIT %s
        """, (limit,))
        
        results = self._cr.fetchall()
        labels = [r[0] for r in results]
        warranties = [r[1] for r in results]
        claims = [r[2] for r in results]
        
        chart_data = {
            'type': 'bar',
            'data': {
                'labels': labels,
                'datasets': [
                    {
                        'label': 'Warranties',
                        'data': warranties,
                        'backgroundColor': '#007bff',
                        'borderColor': '#0056b3',
                        'borderWidth': 1
                    },
                    {
                        'label': 'Claims',
                        'data': claims,
                        'backgroundColor': '#dc3545',
                        'borderColor': '#bd2130',
                        'borderWidth': 1
                    }
                ]
            },
            'options': {
                'indexAxis': 'y',
                'responsive': True,
                'scales': {
                    'x': {'beginAtZero': True}
                },
                'plugins': {
                    'legend': {'position': 'top'}
                }
            }
        }
        
        self.top_products_chart = json.dumps(chart_data)
    
    
    def _prepare_top_customers_chart(self, limit=10):
        """Prepare data for top customers horizontal bar chart"""
        self._cr.execute("""
            SELECT
                rp.name,
                COUNT(wc.id) as warranty_count,
                COUNT(wc2.id) as claim_count
            FROM warranty_card wc
            JOIN res_partner rp ON wc.partner_id = rp.id
            LEFT JOIN warranty_claim wc2 ON wc.id = wc2.warranty_card_id
            GROUP BY rp.name
            ORDER BY warranty_count DESC
            LIMIT %s
        """, (limit,))
        
        results = self._cr.fetchall()
        labels = [r[0] for r in results]
        warranties = [r[1] for r in results]
        claims = [r[2] for r in results]
        
        chart_data = {
            'type': 'bar',
            'data': {
                'labels': labels,
                'datasets': [
                    {
                        'label': 'Warranties',
                        'data': warranties,
                        'backgroundColor': '#28a745',
                        'borderColor': '#1e7e34',
                        'borderWidth': 1
                    },
                    {
                        'label': 'Claims',
                        'data': claims,
                        'backgroundColor': '#ffc107',
                        'borderColor': '#d39e00',
                        'borderWidth': 1
                    }
                ]
            },
            'options': {
                'indexAxis': 'y',
                'responsive': True,
                'scales': {
                    'x': {'beginAtZero': True}
                },
                'plugins': {
                    'legend': {'position': 'top'}
                }
            }
        }
        
        self.top_customers_chart = json.dumps(chart_data)
    
    
    def _prepare_claim_types_chart(self, months=12):
        """Prepare data for claim types stacked area chart"""
        months_back_date = fields.Date.today() - timedelta(days=months*30)
        self._cr.execute("""
            SELECT
                DATE_TRUNC('month', claim_date) as month,
                claim_type,
                COUNT(*) as count
            FROM warranty_claim
            WHERE claim_date >= %s
            GROUP BY DATE_TRUNC('month', claim_date), claim_type
            ORDER BY month, claim_type
        """, (months_back_date,))
        
        results = self._cr.fetchall()
        # Process results for stacked chart
        months_list = sorted(set(r[0] for r in results))
        claim_types = ['repair', 'replace', 'refund']
        
        datasets = []
        colors = {
            'repair': '#007bff',
            'replace': '#28a745',
            'refund': '#ffc107'
        }
        
        for claim_type in claim_types:
            data = []
            for month in months_list:
                count = next((r[2] for r in results if r[0] == month and r[1] == claim_type), 0)
                data.append(count)
            
            datasets.append({
                'label': claim_type.title(),
                'data': data,
                'backgroundColor': colors[claim_type],
                'borderColor': colors[claim_type],
                'fill': True
            })
        
        chart_data = {
            'type': 'line',
            'data': {
                'labels': [m.strftime('%b %Y') for m in months_list],
                'datasets': datasets
            },
            'options': {
                'responsive': True,
                'scales': {
                    'y': {'beginAtZero': True, 'stacked': True},
                    'x': {'stacked': True}
                },
                'plugins': {
                    'legend': {'position': 'top'}
                }
            }
        }
        
        self.claim_types_chart = json.dumps(chart_data)
    
    
    def _prepare_warranty_expiry_chart(self, months=12):
        """Prepare data for warranty expiry forecast chart"""
        today = fields.Date.today()
        future_date = today + timedelta(days=months*30)
        self._cr.execute("""
            SELECT
                DATE_TRUNC('month', end_date) as expiry_month,
                COUNT(*) as expiring_count
            FROM warranty_card
            WHERE end_date >= %s
            AND end_date <= %s
            GROUP BY DATE_TRUNC('month', end_date)
            ORDER BY expiry_month
        """, (today, future_date))
        
        results = self._cr.fetchall()
        labels = [r[0].strftime('%b %Y') for r in results]
        data = [r[1] for r in results]
        
        chart_data = {
            'type': 'bar',
            'data': {
                'labels': labels,
                'datasets': [{
                    'label': 'Warranties Expiring',
                    'data': data,
                    'backgroundColor': '#dc3545',
                    'borderColor': '#bd2130',
                    'borderWidth': 1
                }]
            },
            'options': {
                'responsive': True,
                'scales': {
                    'y': {'beginAtZero': True}
                },
                'plugins': {
                    'legend': {'display': False}
                }
            }
        }
        
        self.warranty_expiry_chart = json.dumps(chart_data)
    
    def _update_all_metrics_job(self):
        """Queue job for updating metrics"""
        try:
            self._update_all_metrics()
        except Exception as e:
            _logger.error(f"Error in queue job cache update: {str(e)}")
            self.write({
                'is_updating': False,
                'cache_status': 'error'
            })