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
                    ('claim_ids', '!=', False)
                ])
                record.claims_this_month = self.env['warranty.claim'].search_count([
                    ('claim_date', '>=', fields.Date.today().replace(day=1))
                ])

                if today.month == 1:
                    last_month_start = today.replace(year=today.year - 1, month=12, day=1)
                else:
                    last_month_start = today.replace(month=today.month - 1, day=1)
                last_month_end = today.replace(day=1) - timedelta(days=1)
                record.claims_last_month = self.env['warranty.claim'].search_count([
                    ('claim_date', '>=', last_month_start),
                    ('claim_date', '<=', last_month_end)
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
        return self.env.ref('buz_warranty_management.action_warranty_claim').read()[0]

    def action_view_all_warranties(self):
        self.ensure_one()
        return self.env.ref('buz_warranty_management.action_warranty_card').read()[0]
