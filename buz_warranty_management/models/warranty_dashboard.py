from odoo import models, fields, api
from datetime import date, timedelta


class WarrantyDashboard(models.TransientModel):
    _name = 'warranty.dashboard'
    _description = 'Warranty Dashboard'
    _log_access = True
    _transient = True

    # KPI Fields
    total_warranties = fields.Integer(
        string='Total Warranties',
        compute='_compute_kpis',
        help='Total number of warranty cards'
    )
    active_warranties = fields.Integer(
        string='Active Warranties',
        compute='_compute_kpis',
        help='Number of active warranty cards'
    )
    expired_warranties = fields.Integer(
        string='Expired Warranties',
        compute='_compute_kpis',
        help='Number of expired warranty cards'
    )
    near_expiry_warranties = fields.Integer(
        string='Near Expiry (30 days)',
        compute='_compute_kpis',
        help='Warranties expiring within 30 days'
    )
    claimed_warranties = fields.Integer(
        string='Claimed Warranties',
        compute='_compute_kpis',
        help='Warranties with at least one claim'
    )
    
    # Percentage Fields
    active_percentage = fields.Float(
        string='Active %',
        compute='_compute_percentages',
        help='Percentage of active warranties'
    )
    expired_percentage = fields.Float(
        string='Expired %',
        compute='_compute_percentages',
        help='Percentage of expired warranties'
    )
    claimed_percentage = fields.Float(
        string='Claimed %',
        compute='_compute_percentages',
        help='Percentage of warranties with claims'
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

    @api.depends()
    def _compute_kpis(self):
        """Compute all KPI values"""
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

    @api.depends('total_warranties', 'active_warranties', 'expired_warranties', 'claimed_warranties')
    def _compute_percentages(self):
        """Compute percentage values"""
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
            
            # Active warranties
            record.active_warranty_ids = self.env['warranty.card'].search([
                ('state', '=', 'active')
            ])
            
            # Expired warranties
            record.expired_warranty_ids = self.env['warranty.card'].search([
                '|',
                ('state', '=', 'expired'),
                ('end_date', '<', today)
            ])
            
            # Near expiry warranties
            record.near_expiry_warranty_ids = self.env['warranty.card'].search([
                ('state', '=', 'active'),
                ('end_date', '>=', today),
                ('end_date', '<=', near_expiry_date)
            ])

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