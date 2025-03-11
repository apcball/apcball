# -*- coding: utf-8 -*-
from odoo import fields, models


class Department(models.Model):
    """ Class for adding new field in employee department"""

    _inherit = 'hr.department'

    department_location_id = fields.Many2one(
        comodel_name='stock.location',
        string='Destination Location',
        help='Select a department location from the list of locations.')
