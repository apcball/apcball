from odoo import fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    employee_id = fields.Many2one(
        'hr.employee', string='Employee',
        related='user_id.employee_id', store=True, readonly=True)
    department_id = fields.Many2one(
        'hr.department', string='Department',
        related='employee_id.department_id', store=True, readonly=True)
