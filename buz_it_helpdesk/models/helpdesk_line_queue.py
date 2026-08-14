import uuid
from datetime import timedelta
import logging

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class HelpdeskLineQueue(models.Model):
    _name = 'buz.helpdesk.line.queue'
    _description = 'IT Helpdesk LINE Notification Queue'
    _order = 'create_date desc, id desc'

    ticket_id = fields.Many2one('buz.helpdesk.ticket', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one('res.company', required=True, index=True)
    line_group_id = fields.Many2one('buz.helpdesk.line.group', required=True, ondelete='restrict')
    target_id = fields.Char(required=True, index=True, copy=False)
    message = fields.Text(required=True, copy=False)
    state = fields.Selection([('pending', 'Pending'), ('sent', 'Sent'), ('failed', 'Failed')], default='pending', required=True, index=True)
    attempt_count = fields.Integer(default=0, copy=False)
    next_attempt_at = fields.Datetime(default=fields.Datetime.now, copy=False, index=True)
    last_error = fields.Text(copy=False)
    retry_key = fields.Char(default=lambda self: str(uuid.uuid4()), required=True, copy=False, index=True)
    sent_at = fields.Datetime(readonly=True, copy=False)

    _sql_constraints = [
        ('ticket_group_unique', 'unique(ticket_id, line_group_id)', 'A LINE notification is already queued for this Ticket and group.'),
    ]

    @api.model
    def cron_process_pending(self, limit=50):
        records = self.sudo().search([
            ('state', '=', 'pending'), ('next_attempt_at', '<=', fields.Datetime.now()),
        ], order='next_attempt_at, id', limit=limit)
        for record in records:
            record._process_one()
        return True

    def _process_one(self):
        self.ensure_one()
        service = self.env['buz.helpdesk.line.service'].sudo()
        config = service._config()
        self.write({'attempt_count': self.attempt_count + 1})
        try:
            service.send_group_message(
                self.target_id, self.message, retry_key=self.retry_key, config=config,
            )
        except Exception as error:
            retryable = service.is_retryable_error(error)
            if retryable and self.attempt_count < 5:
                delay = min(24 * 60 * 60, 2 ** self.attempt_count * 60)
                self.write({'next_attempt_at': fields.Datetime.now() + timedelta(seconds=delay), 'last_error': str(error)[:2000]})
            else:
                self.write({'state': 'failed', 'last_error': str(error)[:2000]})
            _logger.warning('Helpdesk LINE notification failed for queue %s (attempt %s)', self.id, self.attempt_count)
            return False
        self.write({'state': 'sent', 'sent_at': fields.Datetime.now(), 'last_error': False})
        return True

    def action_retry(self):
        for record in self:
            record.write({'state': 'pending', 'attempt_count': 0, 'next_attempt_at': fields.Datetime.now(), 'last_error': False, 'retry_key': str(uuid.uuid4())})
        return True

