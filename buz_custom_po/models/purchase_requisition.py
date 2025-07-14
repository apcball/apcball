from odoo import models, fields

class PurchaseRequisition(models.Model):
    _inherit = 'purchase.requisition'

    purchase_ids = fields.One2many('purchase.order', 'requisition_id', string='Purchase Orders')