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
            # Use SQL queries for better performance
            self._cr.execute("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(CASE WHEN state = 'active' THEN 1 END) as active,
                    COUNT(CASE WHEN state = 'expired' OR end_date < CURRENT_DATE THEN 1 END) as expired,
                    COUNT(CASE WHEN state = 'active' AND end_date >= CURRENT_DATE 
                             AND end_date <= CURRENT_DATE + INTERVAL '30 days' THEN 1 END) as near_expiry,
                    COUNT(CASE WHEN EXISTS(SELECT 1 FROM warranty_claim wc WHERE wc.warranty_card_id = warranty_card.id) 
                             THEN 1 END) as claimed
                FROM warranty_card
            """)
            
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
        # Claims this month
        self._cr.execute("""
            SELECT COUNT(*) FROM warranty_claim 
            WHERE claim_date >= date_trunc('month', CURRENT_DATE)
        """)
        claims_this_month = self._cr.fetchone()[0]
        
        # Claims last month
        self._cr.execute("""
            SELECT COUNT(*) FROM warranty_claim 
            WHERE claim_date >= date_trunc('month', CURRENT_DATE - INTERVAL '1 month')
            AND claim_date < date_trunc('month', CURRENT_DATE)
        """)
        claims_last_month = self._cr.fetchone()[0]
        
        self.write({
            'claims_this_month': claims_this_month,
            'claims_last_month': claims_last_month,
        })
        
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
        with api.Environment.manage():
            # New environment for the thread
            from odoo import registry
            registry = registry.Registry(db_name)
            with registry.cursor() as cr:
                env = api.Environment(cr, 1, context)
                cache = env['warranty.dashboard.cache'].browse(cache_id)
                
                try:
                    cache._update_all_metrics()
                except Exception as e:
                    _logger.error(f"Error in async cache update: {str(e)}")
                    cache.write({
                        'is_updating': False,
                        'cache_status': 'error'
                    })
    
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