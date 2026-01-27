# -*- coding: utf-8 -*-
"""
Approval Token Model
====================

This model stores secure tokens for portal approval links.
Tokens are single-use and have configurable expiration.
"""

import secrets
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ApprovalToken(models.Model):
    _name = 'approval.token'
    _description = 'Approval Token'
    _order = 'create_date desc'
    _rec_name = 'token'

    # Token identification
    token = fields.Char(
        string='Token',
        required=True,
        readonly=True,
        index=True,
        copy=False,
    )
    
    # Related document
    res_model = fields.Char(
        string='Document Model',
        required=True,
        readonly=True,
        index=True,
    )
    res_id = fields.Integer(
        string='Document ID',
        required=True,
        readonly=True,
        index=True,
    )
    res_name = fields.Char(
        string='Document Name',
        readonly=True,
    )
    
    # Approver information
    approver_id = fields.Many2one(
        'res.users',
        string='Approver',
        required=True,
        readonly=True,
        ondelete='cascade',
    )
    line_user_id = fields.Char(
        string='LINE User ID',
        readonly=True,
    )
    
    # Token state
    state = fields.Selection([
        ('active', 'Active'),
        ('used', 'Used'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ], string='State', default='active', readonly=True, index=True)
    
    # Expiration
    expiry_datetime = fields.Datetime(
        string='Expires On',
        required=True,
        readonly=True,
    )
    is_expired = fields.Boolean(
        string='Is Expired',
        compute='_compute_is_expired',
        store=True,
    )
    
    # Usage tracking
    used_datetime = fields.Datetime(
        string='Used On',
        readonly=True,
    )
    action_taken = fields.Selection([
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], string='Action Taken', readonly=True)
    
    # Rate limiting
    view_count = fields.Integer(
        string='View Count',
        default=0,
        readonly=True,
    )
    last_view_datetime = fields.Datetime(
        string='Last Viewed',
        readonly=True,
    )
    
    @api.depends('expiry_datetime', 'state')
    def _compute_is_expired(self):
        """Compute if the token has expired."""
        now = fields.Datetime.now()
        for token in self:
            if token.state != 'active':
                token.is_expired = False
            else:
                token.is_expired = token.expiry_datetime and token.expiry_datetime < now

    @api.model
    def generate_token(self, res_model, res_id, approver_id, res_name=None, line_user_id=None):
        """
        Generate a new secure approval token.
        
        Args:
            res_model: The model name of the document
            res_id: The ID of the document
            approver_id: The ID of the approver user
            res_name: Optional display name of the document
            line_user_id: Optional LINE user ID of the approver
            
        Returns:
            approval.token record
        """
        # Get expiry days from config
        ICP = self.env['ir.config_parameter'].sudo()
        expiry_days = int(ICP.get_param('line_portal_notification.token_expiry_days', 7))
        
        # Generate secure token
        token_value = secrets.token_urlsafe(32)
        
        # Calculate expiry datetime
        expiry_datetime = fields.Datetime.now() + timedelta(days=expiry_days)
        
        # Cancel any existing active tokens for same document/approver
        existing_tokens = self.sudo().search([
            ('res_model', '=', res_model),
            ('res_id', '=', res_id),
            ('approver_id', '=', approver_id),
            ('state', '=', 'active'),
        ])
        existing_tokens.write({'state': 'cancelled'})
        
        # Create new token
        return self.sudo().create({
            'token': token_value,
            'res_model': res_model,
            'res_id': res_id,
            'res_name': res_name,
            'approver_id': approver_id,
            'line_user_id': line_user_id,
            'expiry_datetime': expiry_datetime,
        })

    def validate_token(self, token_value, res_model, res_id):
        """
        Validate a token for a specific document.
        
        Args:
            token_value: The token string
            res_model: The model name
            res_id: The document ID
            
        Returns:
            approval.token record if valid, False otherwise
        """
        token = self.sudo().search([
            ('token', '=', token_value),
            ('res_model', '=', res_model),
            ('res_id', '=', res_id),
            ('state', '=', 'active'),
        ], limit=1)
        
        if not token:
            return False
            
        # Check expiration
        if token.expiry_datetime < fields.Datetime.now():
            token.write({'state': 'expired'})
            return False
            
        return token

    def mark_as_used(self, action):
        """
        Mark the token as used after approval/rejection.
        
        Args:
            action: 'approved' or 'rejected'
        """
        self.ensure_one()
        self.write({
            'state': 'used',
            'used_datetime': fields.Datetime.now(),
            'action_taken': action,
        })

    def increment_view_count(self):
        """Increment view count for rate limiting."""
        self.ensure_one()
        self.sudo().write({
            'view_count': self.view_count + 1,
            'last_view_datetime': fields.Datetime.now(),
        })

    def check_rate_limit(self, max_views=50):
        """
        Check if the token has exceeded rate limit.
        
        Args:
            max_views: Maximum allowed views (default 50)
            
        Returns:
            True if rate limited, False otherwise
        """
        self.ensure_one()
        return self.view_count >= max_views

    def get_portal_url(self):
        """
        Get the full portal URL for this token.
        
        Returns:
            str: Complete portal URL with token
        """
        self.ensure_one()
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return f"{base_url}/my/approve/{self.res_model}/{self.res_id}?token={self.token}"

    @api.model
    def _cron_expire_tokens(self):
        """Cron job to expire old tokens."""
        expired_tokens = self.search([
            ('state', '=', 'active'),
            ('expiry_datetime', '<', fields.Datetime.now()),
        ])
        expired_tokens.write({'state': 'expired'})
        return True

    def action_resend_notification(self):
        """Resend the approval notification using this token."""
        self.ensure_one()
        if self.state != 'active':
            raise UserError(_("Can only resend active tokens."))
            
        record = self.env[self.res_model].browse(self.res_id)
        if not record.exists():
             raise UserError(_("Related document not found."))
             
        if hasattr(record, 'send_line_approval_notification_by_token'):
            return record.send_line_approval_notification_by_token(self)
        else:
            raise UserError(_("The document model '%s' does not support resending notifications via token.") % self.res_model)
