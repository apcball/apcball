# -*- coding: utf-8 -*-

from odoo import models, api, _
from odoo.exceptions import UserError
import requests
import logging
import json

_logger = logging.getLogger(__name__)


class OpenClawClient(models.AbstractModel):
    _name = 'openclaw.client'
    _description = 'OpenClaw API Client'

    @api.model
    def _get_config(self):
        return self.env['openclaw.config'].get_active_config()

    @api.model
    def send_job(self, job):
        config = self._get_config()
        
        try:
            url = f"{config.base_url.rstrip('/')}/api/jobs"
            headers = {
                'Authorization': f'Bearer {config.api_token}',
                'Content-Type': 'application/json',
            }
            
            payload = json.loads(job.payload_json) if job.payload_json else {}
            
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=config.timeout
            )
            
            self.handle_response(job, response)
            
        except requests.exceptions.ConnectionError as e:
            raise UserError(_('Connection error: %s') % str(e))
        except requests.exceptions.Timeout as e:
            raise UserError(_('Request timeout: %s') % str(e))
        except requests.exceptions.RequestException as e:
            raise UserError(_('API request failed: %s') % str(e))
        except Exception as e:
            raise UserError(_('Unexpected error: %s') % str(e))

    @api.model
    def handle_response(self, job, response):
        try:
            if response.status_code == 200:
                response_data = response.json()
                
                job.write({
                    'response_json': json.dumps(response_data, ensure_ascii=False),
                    'state': 'done',
                    'completed_at': self.env['fields.Datetime'].now(),
                })
                
                suggestions = response_data.get('suggestions', [])
                if suggestions:
                    for suggestion_data in suggestions:
                        try:
                            self.env['openclaw.suggestion'].create_from_response(job, suggestion_data)
                        except Exception as e:
                            _logger.error('Error creating suggestion from job %s: %s', job.id, str(e))
                
                _logger.info('Job %s completed successfully with %d suggestions', job.id, len(suggestions))
                
            elif response.status_code == 401:
                raise UserError(_('Authentication failed. Please check your API token.'))
            elif response.status_code == 403:
                raise UserError(_('Access forbidden. Check your API permissions.'))
            elif response.status_code == 404:
                raise UserError(_('API endpoint not found. Please check your Base URL configuration.'))
            elif response.status_code == 429:
                raise UserError(_('Rate limit exceeded. Please try again later.'))
            elif response.status_code >= 500:
                raise UserError(_('Server error (HTTP %s). Please try again later.') % response.status_code)
            else:
                error_msg = response.text if response.text else 'Unknown error'
                raise UserError(_('API request failed: HTTP %s - %s') % (response.status_code, error_msg[:200]))
                
        except json.JSONDecodeError as e:
            raise UserError(_('Invalid JSON response from API: %s') % str(e))
        except Exception as e:
            raise
