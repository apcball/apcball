from odoo import models, fields, api, _

class PurchaseOrderRejectWizard(models.TransientModel):
    _name = 'purchase.order.reject.wizard'
    _description = 'Purchase Order Reject Wizard'

    purchase_order_id = fields.Many2one('purchase.order', string='Purchase Order')
    rejection_reason = fields.Text(string='Rejection Reason', required=True)

    def action_reject(self):
        self.ensure_one()
        self.purchase_order_id.reject_approval(self.rejection_reason)
        return {'type': 'ir.actions.act_window_close'}