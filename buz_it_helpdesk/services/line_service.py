import logging
import re

import requests

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError


_logger = logging.getLogger(__name__)
LINE_INFO_URL = 'https://api.line.me/v2/bot/info'
LINE_GROUP_SUMMARY_URL = 'https://api.line.me/v2/bot/group/%s/summary'
LINE_PUSH_URL = 'https://api.line.me/v2/bot/message/push'
TOKEN_PARAMETER = 'buz_it_helpdesk.line_channel_access_token'
GROUP_PARAMETER_PREFIX = 'buz_it_helpdesk.line_group_id'
LINE_GROUP_RE = re.compile(r'^C[0-9a-fA-F]{32}$')
REQUEST_TIMEOUT = 10


class HelpdeskLineService(models.AbstractModel):
    """Schema-free LINE integration backed by existing System Parameters."""

    _name = 'buz.helpdesk.line.service'
    _description = 'IT Helpdesk LINE Messaging Service'

    @api.model
    def _check_manager(self):
        if not self.env.user.has_group(
            'buz_it_helpdesk.group_it_helpdesk_manager'
        ):
            raise AccessError(
                _('Only Helpdesk Managers can configure LINE notifications.')
            )

    @api.model
    def _allowed_company(self, company_id):
        try:
            company_id = int(company_id)
        except (TypeError, ValueError):
            raise ValidationError(_('Please select a valid company.'))
        company = self.env['res.company'].browse(company_id).exists()
        if not company or company.id not in self.env.companies.ids:
            raise AccessError(
                _('You are not allowed to configure the selected company.')
            )
        return company

    @api.model
    def _parameter(self, key):
        return (
            self.env['ir.config_parameter'].sudo().get_param(key, '') or ''
        ).strip()

    @api.model
    def _group_parameter_key(self, company):
        return '%s.%s' % (GROUP_PARAMETER_PREFIX, company.id)

    @api.model
    def _connection_values(self, company, token=None, group_id=None):
        return {
            'token': (token or '').strip() or self._parameter(TOKEN_PARAMETER),
            'group_id': (
                group_id.strip()
                if isinstance(group_id, str)
                else self._parameter(self._group_parameter_key(company))
            ),
        }

    @api.model
    def _validate_group_id(self, group_id, required=True):
        group_id = (group_id or '').strip()
        if not group_id and not required:
            return ''
        if not LINE_GROUP_RE.fullmatch(group_id):
            raise ValidationError(
                _(
                    'LINE Group ID must start with C and be followed by '
                    '32 hexadecimal characters.'
                )
            )
        return group_id

    @api.model
    def _headers(self, token):
        token = (token or '').strip()
        if not token:
            raise ValidationError(
                _('LINE Channel Access Token is not configured.')
            )
        return {
            'Authorization': 'Bearer %s' % token,
            'Content-Type': 'application/json',
        }

    @api.model
    def _response_detail(self, response):
        try:
            payload = response.json()
            if isinstance(payload, dict):
                return payload.get('message') or response.text or ''
        except (ValueError, AttributeError):
            pass
        return getattr(response, 'text', '') or ''

    @api.model
    def _raise_line_error(self, response, operation):
        status = response.status_code
        if status == 401:
            raise UserError(
                _('LINE rejected the Channel Access Token. Please replace it.')
            )
        if status == 400:
            raise UserError(
                _('LINE rejected the Group ID or request format.')
            )
        if status == 404 and operation == 'group':
            raise UserError(
                _(
                    'LINE group was not found, or the Official Account Bot '
                    'has not joined this group.'
                )
            )
        if status == 429:
            raise UserError(
                _('LINE rate limit was reached. Please try again later.')
            )
        if status >= 500:
            raise UserError(
                _('LINE service is temporarily unavailable. Please try again.')
            )
        detail = self._response_detail(response)
        raise UserError(
            _('LINE API returned HTTP %(status)s: %(detail)s')
            % {
                'status': status,
                'detail': detail[:500] or operation,
            }
        )

    @api.model
    def _request(self, method, url, operation, **kwargs):
        try:
            response = requests.request(
                method,
                url,
                timeout=REQUEST_TIMEOUT,
                **kwargs,
            )
        except requests.exceptions.Timeout:
            raise UserError(_('LINE connection timed out. Please try again.'))
        except requests.exceptions.RequestException:
            raise UserError(
                _('Cannot connect to LINE API. Please check the network.')
            )
        if response.status_code != 200:
            self._raise_line_error(response, operation)
        return response

    @api.model
    def _send_group_message(self, target_id, message, token):
        self._request(
            'POST',
            LINE_PUSH_URL,
            'push',
            headers=self._headers(token),
            json={
                'to': self._validate_group_id(target_id),
                'messages': [{'type': 'text', 'text': message}],
            },
        )
        return True

    @api.model
    def _build_ticket_message(self, ticket):
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

    @api.model
    def _local_datetime_string(self, value=None):
        """Format a UTC datetime in the configuring user's timezone."""
        timezone_name = (
            self.env.context.get('tz')
            or self.env.user.tz
            or 'Asia/Bangkok'
        )
        local_datetime = fields.Datetime.context_timestamp(
            self.with_context(tz=timezone_name),
            value or fields.Datetime.now(),
        )
        return '%s (%s)' % (
            local_datetime.strftime('%Y-%m-%d %H:%M:%S'),
            timezone_name,
        )

    @api.model
    def _send_ticket_notification(self, ticket):
        ticket.ensure_one()
        values = self._connection_values(ticket.company_id)
        if not values['token'] or not values['group_id']:
            _logger.info(
                'LINE notification is not configured for company %s; '
                'Helpdesk Ticket %s was not sent.',
                ticket.company_id.id,
                ticket.id,
            )
            return False
        return self._send_group_message(
            values['group_id'],
            self._build_ticket_message(ticket),
            values['token'],
        )

    @api.model
    def get_line_settings(self, company_id=None):
        self._check_manager()
        companies = self.env.companies.sorted(lambda company: company.name)
        if company_id is None:
            company = self.env.company
        else:
            company = self._allowed_company(company_id)
        if company.id not in companies.ids:
            company = companies[:1]
        return {
            'companies': [
                {'id': company_record.id, 'name': company_record.display_name}
                for company_record in companies
            ],
            'company_id': company.id,
            'company_name': company.display_name,
            'group_id': self._parameter(self._group_parameter_key(company)),
            'token_configured': bool(self._parameter(TOKEN_PARAMETER)),
        }

    @api.model
    def save_line_settings(self, company_id, token='', group_id=''):
        self._check_manager()
        company = self._allowed_company(company_id)
        token = (token or '').strip()
        group_id = self._validate_group_id(group_id, required=False)
        parameters = self.env['ir.config_parameter'].sudo()
        if token:
            parameters.set_param(TOKEN_PARAMETER, token)
        parameters.set_param(self._group_parameter_key(company), group_id)
        return {
            'company_id': company.id,
            'company_name': company.display_name,
            'group_id': group_id,
            'token_configured': bool(token or self._parameter(TOKEN_PARAMETER)),
        }

    @api.model
    def save_and_test_line_settings(
        self,
        company_id,
        token='',
        group_id='',
    ):
        self._check_manager()
        company = self._allowed_company(company_id)
        values = self._connection_values(
            company,
            token=token,
            group_id=self._validate_group_id(group_id),
        )
        headers = self._headers(values['token'])

        bot_response = self._request(
            'GET',
            LINE_INFO_URL,
            'bot',
            headers=headers,
        )
        group_response = self._request(
            'GET',
            LINE_GROUP_SUMMARY_URL % values['group_id'],
            'group',
            headers=headers,
        )
        bot = bot_response.json()
        group = group_response.json()
        if group.get('groupId') != values['group_id']:
            raise UserError(_('LINE returned a different Group ID.'))

        test_message = _(
            '[TEST] IT Helpdesk\n'
            'Company: %(company)s\n'
            'Group: %(group)s\n'
            'Configured by: %(user)s\n'
            'Time: %(time)s\n'
            'New Ticket notifications will be sent to this group.'
        ) % {
            'company': company.display_name,
            'group': group.get('groupName') or values['group_id'],
            'user': self.env.user.display_name,
            'time': self._local_datetime_string(),
        }
        self._send_group_message(
            values['group_id'],
            test_message,
            values['token'],
        )

        saved = self.save_line_settings(
            company.id,
            token=token,
            group_id=values['group_id'],
        )
        saved.update({
            'bot_name': bot.get('displayName') or '',
            'bot_basic_id': bot.get('basicId') or '',
            'group_name': group.get('groupName') or '',
            'group_id': values['group_id'],
        })
        return saved
