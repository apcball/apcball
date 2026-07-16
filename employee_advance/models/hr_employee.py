# -*- coding: utf-8 -*-
from odoo import fields, models


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
        compute='_compute_advance_box_id',
        readonly=True,
        help='Default advance box for this employee. Will be auto-filled in expense reports.'
    )

    def _compute_advance_box_id(self):
        employees = self.env['hr.employee'].sudo().browse(self.ids)
        boxes = {emp.id: emp.advance_box_id for emp in employees}
        for record in self:
            record.advance_box_id = boxes.get(record.id, False)
