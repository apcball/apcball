# -*- coding: utf-8 -*-
import json
import logging

try:
    import requests
except ImportError:
    requests = None

from odoo import fields, models, api
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class AiDiscussConfig(models.Model):
    _name = 'ai.discuss.config'
    _description = 'AI Discuss Bot Configuration'
    _order = 'active desc, sequence, name'

    name = fields.Char(string='Configuration Name', required=True, translate=True)
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(string='Active', default=True, help='Only one configuration can be active at a time')

    # API Configuration
    base_url = fields.Char(
        string='Base URL',
        required=True,
        default='http://194.233.93.92:3334/v1',
        help='Base URL for the AI API endpoint'
    )
    api_key = fields.Char(
        string='API Key',
        required=True,
        default='sml_live_lf5AnZDJMwsC1Ftxt8Kv_K_Ijpy-J3ll',
        help='API key for authentication'
    )
    model_name = fields.Char(
        string='Model Name',
        required=True,
        default='sml/auto',
        help='Model name to use for AI responses'
    )

    # Generation Parameters
    max_tokens = fields.Integer(
        string='Max Tokens',
        default=500,
        help='Maximum number of tokens in the response'
    )
    temperature = fields.Float(
        string='Temperature',
        default=0.7,
        help='Sampling temperature (0.0 to 2.0)'
    )

    # System Prompt
    system_prompt = fields.Text(
        string='System Prompt',
        default='''You are a helpful AI assistant for an ERP system. Your role is to help users find information about:

1. Stock quantities across warehouses
2. Document numbers (Sales Orders, Purchase Orders, Invoices, Delivery Notes)

Answer in the same language as the user's query (Thai or English).
Be concise and helpful. If you cannot find the requested information, politely suggest the user provide more details.''',
        help='System prompt that defines the AI behavior'
    )

    # API Configuration - Advanced
    timeout = fields.Integer(string='Timeout (seconds)', default=30)
    retry_count = fields.Integer(string='Retry Count', default=2)

    # Statistics
    last_used = fields.Datetime(string='Last Used', readonly=True)
    total_calls = fields.Integer(string='Total Calls', readonly=True, default=0)
    successful_calls = fields.Integer(string='Successful Calls', readonly=True, default=0)
    failed_calls = fields.Integer(string='Failed Calls', readonly=True, default=0)

    @api.constrains('active')
    def _check_unique_active(self):
        for record in self:
            if record.active:
                active_configs = self.search([
                    ('active', '=', True),
                    ('id', '!=', record.id)
                ])
                if active_configs:
                    active_configs.write({'active': False})

    @api.constrains('temperature')
    def _check_temperature(self):
        for record in self:
            if record.temperature < 0 or record.temperature > 2.0:
                raise ValidationError('Temperature must be between 0.0 and 2.0')

    def get_active_config(self):
        """Get the currently active configuration."""
        return self.search([('active', '=', True)], limit=1)

    def write(self, vals):
        # Reset active flag for other configs if this one is being activated
        if vals.get('active'):
            if any(config.active for config in self):
                self.search([('active', '=', True), ('id', 'not in', self.ids)]).write({'active': False})
        return super(AiDiscussConfig, self).write(vals)

    def increment_stats(self, success=True):
        """Increment call statistics."""
        self.ensure_one()
        self.write({
            'last_used': fields.Datetime.now(),
            'total_calls': self.total_calls + 1,
            'successful_calls': self.successful_calls + 1 if success else self.successful_calls,
            'failed_calls': self.failed_calls + 1 if not success else self.failed_calls,
        })

    def test_connection(self):
        """Test the API connection."""
        self.ensure_one()

        # Prepare test payload
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": "Hello, are you working?"},
            ],
            "max_tokens": 10,
        }

        url = self.base_url.rstrip('/') + '/chat/completions'
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}',
        }

        if not requests:
            raise UserError('Python \'requests\' library is not installed.')

        try:
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()

            if 'choices' in data and len(data['choices']) > 0:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Success',
                        'message': 'Connection successful! AI API is responding.',
                        'type': 'success',
                    }
                }
            else:
                raise UserError('Unexpected response format from AI API')

        except requests.exceptions.Timeout:
            raise UserError(f'Connection timeout after {self.timeout} seconds')
        except requests.exceptions.RequestException as e:
            raise UserError(f'Connection failed: {str(e)}')
        except json.JSONDecodeError as e:
            raise UserError(f'Invalid response format: {str(e)}')
        except Exception as e:
            raise UserError(f'Test failed: {str(e)}')
