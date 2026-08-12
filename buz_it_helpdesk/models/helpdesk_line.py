import hashlib
import hmac
import logging
import re

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)
LINE_TARGET_RE = re.compile(r'^[CR][0-9a-fA-F]{32}$')


class HelpdeskLineConfig(models.Model):
    _name = 'buz.helpdesk.line.config'
    _description = 'IT Helpdesk LINE Configuration'
    _rec_name = 'name'

    name = fields.Char(default='LINE Messaging API', required=True)
    active = fields.Boolean(default=False)
    channel_access_token = fields.Char(string='Channel Access Token', copy=False)
    channel_secret = fields.Char(string='Channel Secret', copy=False)
    webhook_url = fields.Char(
        string='Webhook URL',
        default=lambda self: self._default_webhook_url(),
        help='Public HTTPS URL configured in the LINE Developers Console.',
    )

    @api.model
    def _default_webhook_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        return '%s/buz_it_helpdesk/line/webhook?db=%s' % (base_url.rstrip('/'), self.env.cr.dbname)

    @api.model
    def get_singleton(self):
        record = self.sudo().search([], limit=1)
        if not record:
            return self.sudo().create({'name': 'LINE Messaging API'})
        if not record.webhook_url:
            record.webhook_url = self._default_webhook_url()
        return record

    @api.constrains('active', 'channel_access_token', 'channel_secret')
    def _check_active_credentials(self):
        for record in self:
            if record.active and (not record.channel_access_token or not record.channel_secret):
                raise ValidationError(_('Channel Access Token and Channel Secret are required when LINE is active.'))

    def action_test_connection(self):
        self.ensure_one()
        self.env['buz.helpdesk.line.service'].test_connection()
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'title': _('LINE'), 'message': _('LINE connection succeeded.'), 'type': 'success', 'sticky': False,
        }}

    @api.model
    def verify_signature(self, body, signature):
        config = self.get_singleton()
        if not config.channel_secret or not signature:
            return False
        digest = hmac.new(config.channel_secret.encode(), body, hashlib.sha256).digest()
        import base64
        return hmac.compare_digest(base64.b64encode(digest).decode(), signature)


class HelpdeskLineGroup(models.Model):
    _name = 'buz.helpdesk.line.group'
    _description = 'IT Helpdesk LINE Group'
    _order = 'name, id'

    name = fields.Char(required=True)
    line_group_id = fields.Char(string='LINE Group/Room ID', required=True, index=True, copy=False)
    active = fields.Boolean(default=True)
    last_event_date = fields.Datetime(readonly=True)
    event_count = fields.Integer(readonly=True, default=0)
    company_ids = fields.One2many('res.company', 'helpdesk_line_group_id', string='Companies')

    _sql_constraints = [
        ('line_group_id_unique', 'unique(line_group_id)', 'This LINE group is already registered.'),
    ]

    @api.constrains('line_group_id')
    def _check_line_group_id(self):
        for record in self:
            if not LINE_TARGET_RE.match(record.line_group_id or ''):
                raise ValidationError(_('LINE Group/Room ID must start with C or R and contain 32 hexadecimal characters.'))

    @api.model
    def register_webhook_group(self, line_group_id, name=None):
        if not LINE_TARGET_RE.match(line_group_id or ''):
            return self.browse()
        record = self.sudo().search([('line_group_id', '=', line_group_id)], limit=1)
        vals = {'last_event_date': fields.Datetime.now(), 'event_count': (record.event_count + 1) if record else 1}
        if name:
            vals['name'] = name
        if record:
            record.write(vals)
            return record
        return self.sudo().create(dict(vals, line_group_id=line_group_id, name=name or line_group_id))
