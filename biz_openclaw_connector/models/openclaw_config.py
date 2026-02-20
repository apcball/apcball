# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import requests
import logging

_logger = logging.getLogger(__name__)


class OpenClawConfig(models.Model):
    _name = 'openclaw.config'
    _description = 'OpenClaw Configuration'
    _rec_name = 'name'

    name = fields.Char(string='Name', required=True, default='OpenClaw API')
    base_url = fields.Char(string='Base URL', required=True, help='e.g., https://api.openclaw.com')
    api_token = fields.Char(string='API Token', required=True, password=True, help='OpenClaw API authentication token')
    timeout = fields.Integer(string='Timeout (seconds)', default=30, required=True, help='Request timeout in seconds')
    active = fields.Boolean(string='Active', default=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)

    _sql_constraints = [
        ('unique_active_company', 'UNIQUE(company_id, active)', 'Only one active configuration per company is allowed')
    ]

    @api.constrains('active')
    def _check_single_active(self):
        for config in self:
            if config.active:
                active_configs = self.search([
                    ('company_id', '=', config.company_id.id),
                    ('active', '=', True),
                    ('id', '!=', config.id)
                ])
                if active_configs:
                    raise ValidationError(_('Only one active configuration per company is allowed'))

    def test_connection(self):
        self.ensure_one()
        try:
            url = f"{self.base_url.rstrip('/')}/api/health"
            headers = {
                'Authorization': f'Bearer {self.api_token}',
                'Content-Type': 'application/json'
            }
            response = requests.get(url, headers=headers, timeout=self.timeout)
            
            if response.status_code in [200, 204]:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Connection Successful'),
                        'message': _('Successfully connected to OpenClaw API'),
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                raise UserError(_('Connection failed: HTTP %s - %s') % (response.status_code, response.text[:200]))
        except requests.exceptions.ConnectionError:
            raise UserError(_('Could not connect to the API Base URL. Please check if the URL is correct and accessible from the server.'))
        except requests.exceptions.Timeout:
            raise UserError(_('Connection timed out after %s seconds. Please check your network or increase the timeout setting.') % self.timeout)
        except Exception as e:
            raise UserError(_('Connection failed: %s') % str(e))

    @api.model
    def get_active_config(self, company=None):
        company = company or self.env.company
        config = self.search([
            ('company_id', '=', company.id),
            ('active', '=', True)
        ], limit=1)
        if not config:
            raise UserError(_('No active OpenClaw configuration found for company %s') % company.name)
        return config
