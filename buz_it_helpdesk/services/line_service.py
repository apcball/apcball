import logging

import requests

from odoo import api, models, _
from odoo.exceptions import UserError


_logger = logging.getLogger(__name__)
LINE_INFO_URL = 'https://api.line.me/v2/bot/info'
LINE_PUSH_URL = 'https://api.line.me/v2/bot/message/push'
TOKEN_PARAMETER = 'buz_it_helpdesk.line_channel_access_token'
GROUP_PARAMETER = 'buz_it_helpdesk.line_group_id'


class HelpdeskLineService(models.AbstractModel):
    """Schema-free LINE integration backed by existing System Parameters."""

    _name = 'buz.helpdesk.line.service'
    _description = 'IT Helpdesk LINE Messaging Service'

    @api.model
    def _parameter(self, key):
        return (
            self.env['ir.config_parameter'].sudo().get_param(key, '') or ''
        ).strip()

    @api.model
    def _company_parameter(self, base_key, company):
        company_value = self._parameter('%s.%s' % (base_key, company.id))
        return company_value or self._parameter(base_key)

    @api.model
    def connection_values(self, company):
        """Return company-specific values with global fallback."""
        return {
            'token': self._company_parameter(TOKEN_PARAMETER, company),
            'group_id': self._company_parameter(GROUP_PARAMETER, company),
        }

    @api.model
    def _headers(self, token):
        token = (token or '').strip()
        if not token:
            raise UserError(_('LINE Channel Access Token is not configured.'))
        return {
            'Authorization': 'Bearer %s' % token,
            'Content-Type': 'application/json',
        }

    @api.model
    def test_connection(self, company):
        values = self.connection_values(company)
        try:
            response = requests.get(
                LINE_INFO_URL,
                headers=self._headers(values['token']),
                timeout=10,
            )
        except requests.exceptions.RequestException as error:
            raise UserError(_('Cannot connect to LINE API: %s') % error)
        if response.status_code != 200:
            raise UserError(
                _('LINE API connection failed (HTTP %s).')
                % response.status_code
            )
        return True

    @api.model
    def send_group_message(self, target_id, message, token):
        response = requests.post(
            LINE_PUSH_URL,
            headers=self._headers(token),
            json={
                'to': (target_id or '').strip(),
                'messages': [{'type': 'text', 'text': message}],
            },
            timeout=10,
        )
        if response.status_code == 200:
            return True
        try:
            detail = response.json().get('message', response.text)
        except (ValueError, AttributeError):
            detail = response.text
        raise UserError(
            _('LINE API returned HTTP %s: %s')
            % (response.status_code, detail[:500])
        )

    @api.model
    def send_ticket_notification(self, ticket):
        ticket.ensure_one()
        values = self.connection_values(ticket.company_id)
        if not values['token'] or not values['group_id']:
            _logger.info(
                'LINE notification is not configured for company %s; '
                'Helpdesk Ticket %s was not sent.',
                ticket.company_id.id,
                ticket.id,
            )
            return False
        return self.send_group_message(
            values['group_id'],
            self.build_ticket_message(ticket),
            values['token'],
        )

    @api.model
    def build_ticket_message(self, ticket):
        base_url = self.env['ir.config_parameter'].sudo().get_param(
            'web.base.url', ''
        ).rstrip('/')
        url = '%s/web#id=%s&model=%s&view_type=form' % (
            base_url,
            ticket.id,
            ticket._name,
        )
        priority = dict(ticket._fields['priority'].selection).get(
            ticket.priority,
            ticket.priority,
        )
        return _(
            'New IT Helpdesk Ticket\n'
            'Ticket: %(ticket)s\n'
            'Subject: %(subject)s\n'
            'Requester: %(requester)s\n'
            'Company: %(company)s\n'
            'Priority: %(priority)s\n'
            'Open: %(url)s'
        ) % {
            'ticket': ticket.display_name,
            'subject': ticket.subject,
            'requester': ticket.requester_id.display_name,
            'company': ticket.company_id.display_name,
            'priority': priority,
            'url': url,
        }
