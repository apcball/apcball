# -*- coding: utf-8 -*-
"""
LINE Notification Configuration Settings
=========================================

Adds LINE API configuration to Odoo General Settings.
"""

from odoo import api, fields, models, _


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # LINE API Credentials
    line_channel_access_token = fields.Char(
        string='LINE Channel Access Token',
        config_parameter='line_portal_notification.channel_access_token',
        help="Channel Access Token from LINE Developers Console",
    )
    line_channel_secret = fields.Char(
        string='LINE Channel Secret',
        config_parameter='line_portal_notification.channel_secret',
        help="Channel Secret from LINE Developers Console",
    )
    
    # Token Configuration
    line_token_expiry_days = fields.Integer(
        string='Token Expiry (Days)',
        config_parameter='line_portal_notification.token_expiry_days',
        default=7,
        help="Number of days before approval tokens expire. Default is 7 days.",
    )
    
    # Rate Limiting
    line_max_token_views = fields.Integer(
        string='Max Token Views',
        config_parameter='line_portal_notification.max_token_views',
        default=50,
        help="Maximum number of times a token can be viewed before being rate limited.",
    )
    
    # Message Template (using Char since Text is not supported for config_parameter)
    line_message_template = fields.Char(
        string='LINE Message Template',
        config_parameter='line_portal_notification.message_template',
        help="Custom message template. Use placeholders: {doc_name}, {amount}, {portal_url}",
    )

    @api.model
    def get_values(self):
        """Get configuration values."""
        res = super().get_values()
        ICP = self.env['ir.config_parameter'].sudo()
        
        res.update(
            line_channel_access_token=ICP.get_param('line_portal_notification.channel_access_token', ''),
            line_channel_secret=ICP.get_param('line_portal_notification.channel_secret', ''),
            line_token_expiry_days=int(ICP.get_param('line_portal_notification.token_expiry_days', 7)),
            line_max_token_views=int(ICP.get_param('line_portal_notification.max_token_views', 50)),
            line_message_template=ICP.get_param('line_portal_notification.message_template', ''),
        )
        return res

    def set_values(self):
        """Set configuration values."""
        super().set_values()
        ICP = self.env['ir.config_parameter'].sudo()
        
        ICP.set_param('line_portal_notification.channel_access_token', self.line_channel_access_token or '')
        ICP.set_param('line_portal_notification.channel_secret', self.line_channel_secret or '')
        ICP.set_param('line_portal_notification.token_expiry_days', self.line_token_expiry_days or 7)
        ICP.set_param('line_portal_notification.max_token_views', self.line_max_token_views or 50)
        ICP.set_param('line_portal_notification.message_template', self.line_message_template or '')
