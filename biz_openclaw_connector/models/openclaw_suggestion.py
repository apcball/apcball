# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging
import json

_logger = logging.getLogger(__name__)


class OpenClawSuggestion(models.Model):
    _name = 'openclaw.suggestion'
    _description = 'OpenClaw Suggestion'
    _order = 'create_date desc, id desc'

    name = fields.Char(string='Name', compute='_compute_name', store=True)
    model_name = fields.Char(string='Model', required=True, help='Odoo model name')
    record_id = fields.Integer(string='Record ID', required=True, help='ID of the record')
    
    suggestion_type = fields.Selection([
        ('risk_alert', 'Risk Alert'),
        ('error_correction', 'Error Correction'),
        ('optimization', 'Optimization'),
        ('compliance', 'Compliance'),
        ('duplicate', 'Duplicate Detection'),
        ('anomaly', 'Anomaly Detection'),
        ('other', 'Other'),
    ], string='Suggestion Type', required=True)
    
    risk_score = fields.Float(string='Risk Score', help='Risk score from 0.0 to 1.0', digits=(3, 2))
    confidence = fields.Float(string='Confidence (%)', help='AI confidence from 0 to 100', digits=(5, 2))
    
    summary = fields.Text(string='Summary', required=True)
    details_json = fields.Text(string='Details JSON', help='Detailed JSON data about the suggestion')
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
    ], string='State', default='draft', required=True, tracking=True)
    
    user_id = fields.Many2one('res.users', string='Approved/Rejected By', readonly=True)
    approval_date = fields.Datetime(string='Approval Date', readonly=True)
    notes = fields.Text(string='Notes')
    
    job_id = fields.Many2one('openclaw.job', string='Job', required=True, ondelete='cascade')
    move_id = fields.Many2one('account.move', string='Invoice', ondelete='cascade', help='Related invoice if model is account.move')

    @api.depends('model_name', 'record_id', 'suggestion_type')
    def _compute_name(self):
        for suggestion in self:
            suggestion.name = f"{suggestion.suggestion_type}: {suggestion.model_name} #{suggestion.record_id}"

    def action_accept(self):
        self.ensure_one()
        self.write({
            'state': 'accepted',
            'user_id': self.env.user.id,
            'approval_date': fields.Datetime.now(),
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Suggestion Accepted'),
                'message': _('Suggestion has been accepted'),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_reject(self):
        self.ensure_one()
        self.write({
            'state': 'rejected',
            'user_id': self.env.user.id,
            'approval_date': fields.Datetime.now(),
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Suggestion Rejected'),
                'message': _('Suggestion has been rejected'),
                'type': 'warning',
                'sticky': False,
            }
        }

    def open_record(self):
        self.ensure_one()
        try:
            model = self.env[self.model_name]
            record = model.browse(self.record_id)
            if not record.exists():
                raise UserError(_('Record not found: %s #%s') % (self.model_name, self.record_id))
            return {
                'type': 'ir.actions.act_window',
                'res_model': self.model_name,
                'res_id': self.record_id,
                'view_mode': 'form',
                'target': 'current',
            }
        except Exception as e:
            raise UserError(_('Cannot open record: %s') % str(e))

    @api.model
    def create_from_response(self, job, suggestion_data):
        vals = {
            'model_name': job.model_name,
            'record_id': job.record_id,
            'suggestion_type': suggestion_data.get('type', 'other'),
            'risk_score': suggestion_data.get('risk_score', 0.0),
            'confidence': suggestion_data.get('confidence', 0.0),
            'summary': suggestion_data.get('summary', ''),
            'details_json': json.dumps(suggestion_data.get('details', {}), ensure_ascii=False),
            'job_id': job.id,
        }
        if job.model_name == 'account.move':
            vals['move_id'] = job.record_id
        return self.create(vals)
