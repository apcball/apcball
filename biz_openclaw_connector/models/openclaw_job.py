# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging
import json

_logger = logging.getLogger(__name__)


class OpenClawJob(models.Model):
    _name = 'openclaw.job'
    _description = 'OpenClaw Job Queue'
    _order = 'create_date desc, id desc'

    name = fields.Char(string='Name', compute='_compute_name', store=True)
    model_name = fields.Char(string='Model', required=True, help='Odoo model name (e.g., account.move)')
    record_id = fields.Integer(string='Record ID', required=True, help='ID of the record being processed')
    event_type = fields.Selection([
        ('invoice_audit', 'Invoice Audit'),
        ('partner_audit', 'Partner Audit'),
        ('expense_audit', 'Expense Audit'),
        ('general_audit', 'General Audit'),
    ], string='Event Type', required=True)
    
    payload_json = fields.Text(string='Payload JSON', help='JSON payload sent to OpenClaw API')
    response_json = fields.Text(string='Response JSON', help='JSON response from OpenClaw API')
    
    state = fields.Selection([
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('done', 'Done'),
        ('error', 'Error'),
    ], string='State', default='pending', required=True)
    
    error_message = fields.Text(string='Error Message')
    retry_count = fields.Integer(string='Retry Count', default=0)
    max_retries = fields.Integer(string='Max Retries', default=3)
    
    attempted_at = fields.Datetime(string='Attempted At')
    completed_at = fields.Datetime(string='Completed At')
    config_id = fields.Many2one('openclaw.config', string='Configuration', required=True, ondelete='restrict')
    move_id = fields.Many2one('account.move', string='Invoice', ondelete='cascade', help='Related invoice if model is account.move')
    
    suggestion_ids = fields.One2many('openclaw.suggestion', 'job_id', string='Suggestions')
    suggestion_count = fields.Integer(string='Suggestion Count', compute='_compute_suggestion_count')

    @api.depends('model_name', 'record_id', 'event_type')
    def _compute_name(self):
        for job in self:
            job.name = f"{job.event_type}: {job.model_name} #{job.record_id}"

    @api.depends('suggestion_ids')
    def _compute_suggestion_count(self):
        for job in self:
            job.suggestion_count = len(job.suggestion_ids)

    def action_retry(self):
        self.ensure_one()
        if self.retry_count >= self.max_retries:
            raise UserError(_('Maximum retry attempts (%s) reached') % self.max_retries)
        self.write({
            'state': 'pending',
            'error_message': False,
            'attempted_at': False,
            'completed_at': False,
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Job Retried'),
                'message': _('Job has been queued for retry'),
                'type': 'info',
                'sticky': False,
            }
        }

    def action_mark_done(self):
        self.ensure_one()
        self.write({
            'state': 'done',
            'completed_at': fields.Datetime.now(),
        })

    def action_mark_error(self):
        self.ensure_one()
        self.write({
            'state': 'error',
            'completed_at': fields.Datetime.now(),
        })

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
    def create_job(self, model_name, record_id, event_type, payload):
        config = self.env['openclaw.config'].get_active_config()
        vals = {
            'model_name': model_name,
            'record_id': record_id,
            'event_type': event_type,
            'payload_json': json.dumps(payload, ensure_ascii=False),
            'config_id': config.id,
        }
        if model_name == 'account.move':
            vals['move_id'] = record_id
        return self.create(vals)

    @api.model
    def process_pending_jobs(self, limit=50):
        jobs = self.search([
            ('state', '=', 'pending'),
            ('retry_count', '<', 3),
        ], limit=limit, order='create_date asc')
        
        _logger.info('Processing %d pending OpenClaw jobs', len(jobs))
        
        for job in jobs:
            try:
                job.write({
                    'state': 'processing',
                    'attempted_at': fields.Datetime.now(),
                })
                
                self.env['openclaw.client'].send_job(job)
                
            except Exception as e:
                error_msg = str(e)
                retry_count = job.retry_count + 1
                state = 'pending' if retry_count < job.max_retries else 'error'
                
                job.write({
                    'state': state,
                    'error_message': error_msg,
                    'retry_count': retry_count,
                })
                
                _logger.error('Error processing job %s: %s', job.name, error_msg)
        
        return len(jobs)
