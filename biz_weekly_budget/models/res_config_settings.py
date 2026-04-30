# -*- coding: utf-8 -*-
from odoo import fields, models

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    budget_default_department_id = fields.Many2one(
        related='company_id.default_department_id',
        readonly=False,
    )
    budget_control_type = fields.Selection(
        related='company_id.budget_control_type',
        readonly=False,
    )
    enable_forecast = fields.Boolean(
        related='company_id.enable_forecast',
        readonly=False,
    )
    budget_aging_days_limit = fields.Integer(
        related='company_id.budget_aging_days_limit',
        readonly=False,
    )
