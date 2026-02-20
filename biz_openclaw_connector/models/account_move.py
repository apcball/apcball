# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging
import json

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    openclaw_job_ids = fields.One2many('openclaw.job', 'move_id', string='OpenClaw Jobs')
    openclaw_suggestion_ids = fields.One2many('openclaw.suggestion', 'move_id', string='OpenClaw Suggestions')
    openclaw_job_count = fields.Integer(string='Job Count', compute='_compute_openclaw_counts')
    openclaw_suggestion_count = fields.Integer(string='Suggestion Count', compute='_compute_openclaw_counts')

    @api.depends('openclaw_job_ids', 'openclaw_suggestion_ids')
    def _compute_openclaw_counts(self):
        for move in self:
            move.openclaw_job_count = len(move.openclaw_job_ids)
            move.openclaw_suggestion_count = len(move.openclaw_suggestion_ids)

    def action_ai_audit(self):
        self.ensure_one()
        if self.state not in ['draft']:
            raise UserError(_('AI Audit is only available for draft invoices'))
        
        payload = self._prepare_audit_payload()
        
        job = self.env['openclaw.job'].create_job(
            model_name='account.move',
            record_id=self.id,
            event_type='invoice_audit',
            payload=payload
        )
        
        _logger.info('Created OpenClaw audit job %s for invoice %s', job.id, self.name)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('AI Audit Queued'),
                'message': _('Invoice has been queued for AI audit. Job #%s will be processed shortly.') % job.id,
                'type': 'info',
                'sticky': False,
            }
        }

    def _prepare_audit_payload(self):
        lines_data = []
        for line in self.invoice_line_ids:
            line_data = {
                'product': line.product_id.name if line.product_id else line.name,
                'description': line.name,
                'quantity': line.quantity,
                'price_unit': float(line.price_unit),
                'discount': line.discount,
                'taxes': [tax.name for tax in line.tax_ids],
                'account': line.account_id.code if line.account_id else '',
                'subtotal': float(line.price_subtotal),
            }
            lines_data.append(line_data)
        
        payload = {
            'event_type': 'invoice_audit',
            'model_name': 'account.move',
            'record_id': self.id,
            'data': {
                'invoice_type': self.move_type,
                'invoice_number': self.name,
                'invoice_date': self.invoice_date.strftime('%Y-%m-%d') if self.invoice_date else None,
                'due_date': self.invoice_date_due.strftime('%Y-%m-%d') if self.invoice_date_due else None,
                'partner': {
                    'id': self.partner_id.id,
                    'name': self.partner_id.name,
                    'vat': self.partner_id.vat or '',
                    'email': self.partner_id.email or '',
                } if self.partner_id else None,
                'journal': self.journal_id.name if self.journal_id else '',
                'amount_untaxed': float(self.amount_untaxed),
                'amount_tax': float(self.amount_tax),
                'amount_total': float(self.amount_total),
                'currency': self.currency_id.name if self.currency_id else '',
                'state': self.state,
                'payment_reference': self.ref or self.payment_reference or '',
                'lines': lines_data,
            }
        }
        return payload

    def action_view_openclaw_jobs(self):
        self.ensure_one()
        return {
            'name': _('OpenClaw Jobs'),
            'type': 'ir.actions.act_window',
            'res_model': 'openclaw.job',
            'view_mode': 'tree,form',
            'domain': [('model_name', '=', 'account.move'), ('record_id', '=', self.id)],
            'context': {'default_model_name': 'account.move', 'default_record_id': self.id},
        }

    def action_view_openclaw_suggestions(self):
        self.ensure_one()
        return {
            'name': _('OpenClaw Suggestions'),
            'type': 'ir.actions.act_window',
            'res_model': 'openclaw.suggestion',
            'view_mode': 'tree,form',
            'domain': [('model_name', '=', 'account.move'), ('record_id', '=', self.id)],
            'context': {'default_model_name': 'account.move', 'default_record_id': self.id},
        }
