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
    # เพิ่มฟิลด์ analytic_precision
    analytic_precision = fields.Integer(
        string="Analytic Precision",
        default=lambda self: self.env['decimal.precision'].precision_get('Percentage Analytic')
    )