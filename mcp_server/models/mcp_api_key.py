# -*- coding: utf-8 -*-

from odoo import models, fields
import secrets


class MCPApiKey(models.Model):
    _name = 'mcp.api.key'
    _description = 'MCP API Key'
    _order = 'create_date desc'

    POLICY_SELECTION = [
        ('read', 'Read Only'),
        ('write', 'Read & Write'),
    ]

    name = fields.Char(string='Name', required=True)
    key = fields.Char(string='API Key', required=True, readonly=True, copy=False, default=lambda self: secrets.token_urlsafe(32))
    policy = fields.Selection(
        POLICY_SELECTION,
        string='Policy',
        default='read',
        required=True,
        help='Read: search, read, reports only. Write: includes create, write, confirm actions.',
    )
    active = fields.Boolean(string='Active', default=True)
    user_id = fields.Many2one('res.users', string='User', required=True, default=lambda self: self.env.user)
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)
    last_used = fields.Datetime(string='Last Used', readonly=True)
    usage_count = fields.Integer(string='Usage Count', readonly=True, default=0)
    note = fields.Text(string='Notes')

    def regenerate_key(self):
        """Regenerate the API key"""
        for record in self:
            record.key = secrets.token_urlsafe(32)
            record.usage_count = 0
            record.last_used = False
