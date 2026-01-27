from odoo import models, fields, api
from datetime import date, timedelta


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

    # KPI Fields (now from cache)
    total_warranties = fields.Integer(
        string='Total Warranties',
        compute='_compute_from_cache',
        help='Total number of warranty cards'
    )
    active_warranties = fields.Integer(
        string='Active Warranties',
        compute='_compute_from_cache',
        help='Number of active warranty cards'
    )
    expired_warranties = fields.Integer(
        string='Expired Warranties',
        compute='_compute_from_cache',
        help='Number of expired warranty cards'
    )
    near_expiry_warranties = fields.Integer(
        string='Near Expiry (30 days)',
        compute='_compute_from_cache',
        help='Warranties expiring within 30 days'
    )
    claimed_warranties = fields.Integer(
        string='Claimed Warranties',
        compute='_compute_from_cache',
        help='Warranties with at least one claim'
    )
    
    # Percentage Fields
    active_percentage = fields.Float(
        string='Active %',
        compute='_compute_from_cache',
        help='Percentage of active warranties'
    )
    expired_percentage = fields.Float(
        string='Expired %',
        compute='_compute_from_cache',
        help='Percentage of expired warranties'
    )
    claimed_percentage = fields.Float(
        string='Claimed %',
        compute='_compute_from_cache',
        help='Percentage of warranties with claims'
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

    @api.model
    def get_or_create_dashboard(self):
        """Get existing dashboard or create singleton"""
        dashboard = self.search([], limit=1)
        if not dashboard:
            # Get or create cache first
            cache = self.env['warranty.dashboard.cache'].get_or_create_cache()
            
            # Create dashboard with cache
            dashboard = self.create({
                'name': 'Warranty Dashboard',
                'cache_id': cache.id
            })
            
            # Ensure cache is updated
            if cache.cache_status != 'valid' or not cache.last_update:
                cache._update_all_metrics()
        else:
            # Ensure cache exists and is valid
            if not dashboard.cache_id:
                cache = self.env['warranty.dashboard.cache'].get_or_create_cache()
                dashboard.cache_id = cache.id
            
            # Update cache if stale
            if dashboard.cache_id.cache_status != 'valid':
                dashboard.cache_id._update_all_metrics()
        
        return dashboard

    @api.model
    def get_or_create_dashboard(self):
        """Get existing dashboard record or create new one (singleton)"""
        dashboard = self.search([], limit=1)
        if not dashboard:
            # Create new dashboard
            cache = self.env['warranty.dashboard.cache'].get_or_create_cache()
            dashboard = self.create({
                'cache_id': cache.id
            })
        else:
            # Ensure cache is up to date
            if not dashboard.cache_id:
                cache = self.env['warranty.dashboard.cache'].get_or_create_cache()
                dashboard.cache_id = cache.id
            elif dashboard.cache_id.cache_status != 'valid':
                dashboard.cache_id._update_all_metrics()
        
        return dashboard
    
    @api.model
    def action_open_dashboard(self):
        """Action to open the dashboard singleton record"""
        dashboard = self.get_or_create_dashboard()
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'warranty.dashboard',
            'view_mode': 'form',
            'res_id': dashboard.id,
            'target': 'current',
            'context': {'form_view_initial_mode': 'edit'},
        }

    @api.model
    def default_get(self, fields_list):
        """Initialize with cache reference and ensure cache is updated"""
        res = super().default_get(fields_list)
        
        # Check if we should use singleton pattern
        if self._context.get('dashboard_singleton'):
            # Find existing dashboard record
            existing = self.search([], limit=1)
            if existing:
                # Return existing record's data
                return existing.read(fields_list)[0] if fields_list else {}
        
        # Get or create cache
        cache = self.env['warranty.dashboard.cache'].get_or_create_cache()
        
        # Ensure cache is always fresh when opening dashboard
        if cache.cache_status != 'valid' or not cache.last_update:
            cache._update_all_metrics()
        
        res['cache_id'] = cache.id
        
        return res
    
    @api.model
    def create(self, vals):
        """Override create to implement singleton pattern"""
        # Check if we should use singleton
        if self._context.get('dashboard_singleton'):
            # Check if a dashboard record already exists
            existing = self.search([], limit=1)
            if existing:
                # Update existing record instead of creating new
                existing.write(vals)
                return existing
        
        return super().create(vals)

    @api.depends('cache_id')
    def _compute_from_cache(self):
        """Get values from cache instead of computing"""
        import logging
        _logger = logging.getLogger(__name__)
        
        for record in self:
            try:
                if record.cache_id and record.cache_id.cache_status == 'valid':
                    # Use cached values
                    cache = record.cache_id
                    _logger.debug(f"Using cached values for dashboard {record.id}, cache_id: {cache.id}")
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
                    _logger.debug(f"Successfully assigned claims_this_month: {cache.claims_this_month}")
                else:
                    # Fallback to real-time calculation
                    _logger.debug(f"Using fallback calculation for dashboard {record.id}")
                    record._compute_kpis_fallback()
                    record._compute_percentages_fallback()
            except Exception as e:
                _logger.error(f"Error in _compute_from_cache for dashboard {record.id}: {str(e)}")
                _logger.error(f"Cache ID: {record.cache_id.id if record.cache_id else 'None'}")
                _logger.error(f"Cache status: {record.cache_id.cache_status if record.cache_id else 'None'}")
                raise

    def _compute_kpis_fallback(self):
        """Fallback method for real-time calculation"""
        import logging
        _logger = logging.getLogger(__name__)
        
        for record in self:
            try:
                # Total warranties
                record.total_warranties = self.env['warranty.card'].search_count([])
                
                # Active warranties
                record.active_warranties = self.env['warranty.card'].search_count([
                    ('state', '=', 'active')
                ])
                
                # Expired warranties
                today = fields.Date.today()
                record.expired_warranties = self.env['warranty.card'].search_count([
                    '|',
                    ('state', '=', 'expired'),
                    ('end_date', '<', today)
                ])
                
                # Near expiry warranties (within 30 days)
                near_expiry_date = today + timedelta(days=30)
                record.near_expiry_warranties = self.env['warranty.card'].search_count([
                    ('state', '=', 'active'),
                    ('end_date', '>=', today),
                    ('end_date', '<=', near_expiry_date)
                ])
                
                # Claimed warranties (with at least one claim)
                record.claimed_warranties = self.env['warranty.card'].search_count([
                    ('claim_ids', '!=', False)
                ])
                
                # Calculate claims_this_month in fallback
                _logger.debug("Computing claims_this_month in fallback mode")
                claims_this_month = self.env['warranty.claim'].search_count([
                    ('claim_date', '>=', fields.Date.today().replace(day=1))
                ])
                record.claims_this_month = claims_this_month
                _logger.debug(f"Fallback claims_this_month calculated: {claims_this_month}")
                
                # Calculate claims_last_month in fallback
                _logger.debug("Computing claims_last_month in fallback mode")
                today = fields.Date.today()
                if today.month == 1:
                    last_month_start = today.replace(year=today.year-1, month=12, day=1)
                    last_month_end = today.replace(day=1) - timedelta(days=1)
                else:
                    last_month_start = today.replace(month=today.month-1, day=1)
                    last_month_end = today.replace(day=1) - timedelta(days=1)
                
                claims_last_month = self.env['warranty.claim'].search_count([
                    ('claim_date', '>=', last_month_start),
                    ('claim_date', '<=', last_month_end)
                ])
                record.claims_last_month = claims_last_month
                _logger.debug(f"Fallback claims_last_month calculated: {claims_last_month}")
                
            except Exception as e:
                _logger.error(f"Error in _compute_kpis_fallback for dashboard {record.id}: {str(e)}")
                raise

    def _compute_percentages_fallback(self):
        """Fallback method for percentage calculation"""
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
        """Compute filtered warranty lists for embedded views"""
        for record in self:
            today = fields.Date.today()
            near_expiry_date = today + timedelta(days=30)
            
            # Active warranties (limited to 100 for performance)
            record.active_warranty_ids = self.env['warranty.card'].search([
                ('state', '=', 'active')
            ], limit=100)
            
            # Expired warranties (limited to 100)
            record.expired_warranty_ids = self.env['warranty.card'].search([
                '|',
                ('state', '=', 'expired'),
                ('end_date', '<', today)
            ], limit=100)
            
            # Near expiry warranties (limited to 100)
            record.near_expiry_warranty_ids = self.env['warranty.card'].search([
                ('state', '=', 'active'),
                ('end_date', '>=', today),
                ('end_date', '<=', near_expiry_date)
            ], limit=100)

    def action_refresh_cache(self):
        """Manual cache refresh with user feedback"""
        self.ensure_one()
        
        if not self.cache_id:
            self.cache_id = self.env['warranty.dashboard.cache'].create({})
        
        # Check if already updating
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
        
        # Start background update
        self.cache_id.with_context(
            manual_refresh=True
        )._update_all_metrics_async()
        
        # Show notification
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Refresh Started',
                'message': 'Dashboard is being updated. Data will refresh automatically.',
                'type': 'info',
                'sticky': False,
            }
        }

    def action_force_refresh(self):
        """Force complete refresh of all data"""
        self.ensure_one()
        
        if not self.cache_id:
            self.cache_id = self.env['warranty.dashboard.cache'].create({})
        
        # Force refresh by clearing cache first
        self.cache_id.write({
            'cache_status': 'expired',
            'cache_valid_until': fields.Datetime.now() - timedelta(hours=1)
        })
        
        # Start background update
        self.cache_id.with_context(
            force_refresh=True
        )._update_all_metrics_async()
        
        # Show notification
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Force Refresh Started',
                'message': 'Complete dashboard refresh has been initiated.',
                'type': 'info',
                'sticky': False,
            }
        }

    def action_rebuild_cache(self):
        """Completely rebuild the cache from scratch"""
        self.ensure_one()
        import logging
        _logger = logging.getLogger(__name__)
        
        try:
            # Delete existing cache completely
            if self.cache_id:
                _logger.info(f"Deleting existing cache {self.cache_id.id}")
                self.cache_id.unlink()
                self.cache_id = False
            
            # Create new cache
            _logger.info("Creating new cache record")
            self.cache_id = self.env['warranty.dashboard.cache'].create({})
            
            # Update cache synchronously to ensure it works
            _logger.info("Updating cache metrics synchronously")
            self.cache_id._update_all_metrics()
            
            # Trigger recomputation of all fields
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
            _logger.error(f"Error rebuilding cache: {str(e)}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Cache Rebuild Failed',
                    'message': f'Error rebuilding cache: {str(e)}',
                    'type': 'danger',
                    'sticky': True,
                }
            }

    def action_view_active_warranties(self):
        """Action to view active warranties"""
        self.ensure_one()
        action = self.env.ref('buz_warranty_management.action_warranty_card_active').read()[0]
        return action

    def action_view_expired_warranties(self):
        """Action to view expired warranties"""
        self.ensure_one()
        action = self.env.ref('buz_warranty_management.action_warranty_card_expired').read()[0]
        return action

    def action_view_near_expiry_warranties(self):
        """Action to view near expiry warranties"""
        self.ensure_one()
        action = self.env.ref('buz_warranty_management.action_warranty_card_near_expiry').read()[0]
        return action

    def action_view_claimed_warranties(self):
        """Action to view claimed warranties"""
        self.ensure_one()
        action = self.env.ref('buz_warranty_management.action_warranty_claim').read()[0]
        return action

    def action_view_all_warranties(self):
        """Action to view all warranties"""
        self.ensure_one()
        action = self.env.ref('buz_warranty_management.action_warranty_card').read()[0]
        return action

    @api.model
    def action_open_dashboard(self):
        """Action to open the dashboard - always opens the singleton record"""
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