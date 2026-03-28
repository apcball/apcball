from odoo import models, fields, api, _

class StockTransferRecreateWizard(models.TransientModel):
    _name = 'stock.transfer.recreate.wizard'
    _description = 'Stock Transfer Recreate Wizard'

    order_model = fields.Char('Order Model', required=True)
    order_id = fields.Integer('Order ID', required=True)
    line_count = fields.Integer('Number of Lines', readonly=True)
    total_qty = fields.Float('Total Quantity', readonly=True)
    warning_message = fields.Text('Warning Message', readonly=True)

    def action_confirm(self):
        self.ensure_one()
        # Call the appropriate recreation method based on the origin order model
        if self.order_model == 'sale.order':
            order = self.env['sale.order'].browse(self.order_id)
            if order.exists():
                order._recreate_delivery_action()
                order.message_post(body=_("Delivery transfer recreated by %s due to missing or inconsistent picking.", self.env.user.name))
        elif self.order_model == 'purchase.order':
            order = self.env['purchase.order'].browse(self.order_id)
            if order.exists():
                order._recreate_receipt_action()
                order.message_post(body=_("Receipt transfer recreated by %s due to missing or inconsistent picking.", self.env.user.name))
        
        return {'type': 'ir.actions.act_window_close'}
