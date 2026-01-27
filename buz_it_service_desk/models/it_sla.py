# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ITSLA(models.Model):
    _name = 'it.sla'
    _description = 'IT Service Level Agreement'
    _order = 'priority'

    name = fields.Char(string='SLA Name', required=True)
    priority = fields.Selection([
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ], string='Priority', required=True, default='medium')
    response_time = fields.Integer(string='Response Time (hours)', required=True, default=24,
                                   help="Maximum time to first respond to the ticket")
    resolve_time = fields.Integer(string='Resolve Time (hours)', required=True, default=72,
                                 help="Maximum time to resolve the ticket")
    warning_time = fields.Integer(string='Warning Time (hours)', required=True, default=48,
                                 help="Time before deadline to send warning")
    active = fields.Boolean(string='Active', default=True)
    description = fields.Text(string='Description')
    
    @api.constrains('response_time', 'resolve_time', 'warning_time')
    def _check_time_values(self):
        for sla in self:
            if sla.response_time <= 0 or sla.resolve_time <= 0 or sla.warning_time <= 0:
                raise ValidationError(_('Time values must be positive.'))
            if sla.warning_time >= sla.resolve_time:
                raise ValidationError(_('Warning time must be less than resolve time.'))

    @api.model
    def get_sla_by_priority(self, priority):
        """Get SLA record by priority"""
        return self.search([('priority', '=', priority), ('active', '=', True)], limit=1)