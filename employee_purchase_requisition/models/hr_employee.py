# -*- coding: utf-8 -*-
from odoo import fields, models


class HrEmployeePrivate(models.Model):
    """Class to add new field in employee form"""

    _inherit = 'hr.employee'

    employee_location_id = fields.Many2one(
        comodel_name='stock.location',
        string="Destination Location",
        help='Select a employee location from the location list')
