import json
import logging
import requests

from odoo import api, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)
LINE_INFO_URL = 'https://api.line.me/v2/bot/info'
LINE_PUSH_URL = 'https://api.line.me/v2/bot/message/push'


class HelpdeskLineService(models.AbstractModel):
    _name = 'buz.helpdesk.line.service'
    _description = 'IT Helpdesk LINE Messaging Service'

    @api.model
    def _config(self, config=None):
        if config:
            return config.sudo()
        return self.env['buz.helpdesk.line.config'].sudo().get_singleton()

    @api.model
    def _headers(self, retry_key=None, config=None):
        token = (self._config(config).channel_access_token or '').strip()
        if not token:
            raise UserError(_('LINE Channel Access Token is not configured.'))
        headers = {'Authorization': 'Bearer %s' % token, 'Content-Type': 'application/json'}
        if retry_key:
            headers['X-Line-Retry-Key'] = retry_key
        return headers

    @api.model
    def test_connection(self, config=None):
        try:
            response = requests.get(LINE_INFO_URL, headers=self._headers(config=config), timeout=15)
        except requests.exceptions.RequestException as error:
            raise UserError(_('Cannot connect to LINE API: %s') % error)
        if response.status_code != 200:
            raise UserError(_('LINE API connection failed (HTTP %s).') % response.status_code)
        return True

    @api.model
    def send_group_message(self, target_id, message, retry_key, config=None):
        try:
            response = requests.post(
                LINE_PUSH_URL,
                headers=self._headers(retry_key, config=config),
                json={'to': target_id, 'messages': [{'type': 'text', 'text': message}]},
                timeout=15,
            )
        except requests.exceptions.RequestException as error:
            raise error
        if response.status_code in (200, 409):
            return True
        try:
            detail = response.json().get('message', response.text)
        except (ValueError, AttributeError):
            detail = response.text
        raise UserError(_('LINE API returned HTTP %s: %s') % (response.status_code, detail[:500]))

    @api.model
    def is_retryable_error(self, error):
        if isinstance(error, (requests.exceptions.Timeout, requests.exceptions.ConnectionError, requests.exceptions.RequestException)):
            return True
        text = str(error)
        return any(marker in text for marker in ('HTTP 429', 'HTTP 500', 'HTTP 501', 'HTTP 502', 'HTTP 503', 'HTTP 504'))

    @api.model
    def build_ticket_message(self, ticket):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '').rstrip('/')
        url = '%s/web#id=%s&model=%s&view_type=form' % (base_url, ticket.id, ticket._name)
        priority = dict(ticket._fields['priority'].selection).get(ticket.priority, ticket.priority)
        return _('New IT Helpdesk Ticket\nTicket: %(ticket)s\nSubject: %(subject)s\nRequester: %(requester)s\nCompany: %(company)s\nPriority: %(priority)s\nOpen: %(url)s') % {
            'ticket': ticket.display_name,
            'subject': ticket.subject,
            'requester': ticket.requester_id.display_name,
            'company': ticket.company_id.display_name,
            'priority': priority,
            'url': url,
        }

