from odoo import models, fields, api
from datetime import date, timedelta


class WarrantyDashboard(models.TransientModel):
    _name = 'warranty.dashboard'
    _description = 'Warranty Dashboard'
    _log_access = True
    _transient = True

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
    def default_get(self, fields_list):
        """Initialize with cache reference"""
        res = super().default_get(fields_list)
        
        # Get or create cache
        cache = self.env['warranty.dashboard.cache'].get_or_create_cache()
        res['cache_id'] = cache.id
        
        return res

    @api.depends('cache_id')
    def _compute_from_cache(self):
        """Get values from cache instead of computing"""
        for record in self:
            if record.cache_id and record.cache_id.cache_status == 'valid':
                # Use cached values
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
                # Fallback to real-time calculation
                record._compute_kpis_fallback()
                record._compute_percentages_fallback()

    def _compute_kpis_fallback(self):
        """Fallback method for real-time calculation"""
        for record in self:
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