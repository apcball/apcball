# -*- coding: utf-8 -*-

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    service_receipt_attendee_employee_ids = fields.Many2many(
        'hr.employee',
        related='company_id.service_receipt_attendee_employee_ids',
        string='Service Receipt Calendar Employees',
        readonly=False,
        help='Employees who should receive service receipt calendar appointments automatically.',
    )
