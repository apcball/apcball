# -*- coding: utf-8 -*-
from odoo import fields, models

class ResCompany(models.Model):
    _inherit = 'res.company'

    default_department_id = fields.Many2one('hr.department', string='Default Budget Department')
    budget_control_type = fields.Selection([
        ('hard', 'Hard (Block)'),
        ('soft', 'Soft (Warning)'),
    ], string='Budget Control Type', default='hard', required=True)
    enable_forecast = fields.Boolean(string='Enable Budget Forecast', default=False)
    budget_aging_days_limit = fields.Integer(string='Budget Aging Days Limit', default=30)
