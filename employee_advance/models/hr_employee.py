# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    advance_box_id = fields.Many2one(
        'employee.advance.box',
        string='Default Advance Box',
        help='Default advance box for this employee. Will be auto-filled in expense reports.'
    )


class HrEmployeePublic(models.Model):
    _inherit = 'hr.employee.public'

    advance_box_id = fields.Many2one(
        'employee.advance.box',
        string='Default Advance Box',
        readonly=True,
        help='Default advance box for this employee. Will be auto-filled in expense reports.'
    )
