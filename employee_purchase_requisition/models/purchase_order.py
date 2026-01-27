from odoo import api, fields, models

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    requisition_order = fields.Char(
        string='Requisition Order',
        help='Set a requisition Order'
    )
    analytic_distribution = fields.Json(
        string="Analytic Distribution",
        store=True,
        copy=True
    )
    analytic_precision = fields.Integer(
        string="Analytic Precision",
        default=lambda self: self.env['decimal.precision'].precision_get('Percentage Analytic')
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        help='Employee who requested the PR',
    )
    dept_id = fields.Many2one(
        'hr.department',
        string='Department',
        help='Department of the employee',
    )
    pr_number = fields.Char(
        string='PR Number',
        help='Reference number of the PR',
    )
    destination_location_id = fields.Many2one(
        'stock.location',
        string='Destination Location',
        help='Destination location from requisition',
    )