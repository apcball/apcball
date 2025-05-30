# -*- coding: utf-8 -*-

from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class BackdateLog(models.Model):
    _name = 'backdate.log'
    _description = 'Backdate Log'
    _order = 'create_date desc'
    _rec_name = 'document_name'

    document_name = fields.Char(string='Document', required=True)
    document_model = fields.Char(string='Model', required=True)
    document_id = fields.Integer(string='Document ID', required=True)
    old_date = fields.Datetime(string='Old Date', required=True)
    new_date = fields.Datetime(string='New Date', required=True)
    user_id = fields.Many2one('res.users', string='User', required=True, default=lambda self: self.env.user)
    reason = fields.Text(string='Reason')
    create_date = fields.Datetime(string='Backdate Time', default=fields.Datetime.now)
    
    @api.model
    def log_backdate(self, document, old_date, new_date, reason=None):
        """Log a backdate operation"""
        self.create({
            'document_name': document.display_name,
            'document_model': document._name,
            'document_id': document.id,
            'old_date': old_date,
            'new_date': new_date,
            'reason': reason or '',
        })
        
    def action_view_document(self):
        """Open the backdated document"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self.document_model,
            'res_id': self.document_id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    @api.model
    def cleanup_old_logs(self):
        """Clean up old backdate logs (called by cron job)"""
        # Get retention period from system parameters (default 365 days)
        retention_days = int(self.env['ir.config_parameter'].sudo().get_param(
            'sh_all_in_one_backdate.log_retention_days', '365'
        ))
        
        if retention_days > 0:
            from datetime import datetime, timedelta
            cutoff_date = datetime.now() - timedelta(days=retention_days)
            old_logs = self.search([('create_date', '<', cutoff_date)])
            
            if old_logs:
                count = len(old_logs)
                old_logs.unlink()
                _logger.info(f"Cleaned up {count} old backdate logs older than {retention_days} days")
            else:
                _logger.info("No old backdate logs to clean up")
        else:
            _logger.info("Log cleanup disabled (retention_days = 0)")
        
        return True