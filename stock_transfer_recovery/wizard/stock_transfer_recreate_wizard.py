from odoo import models, fields, api, _

class StockTransferRecreateWizard(models.TransientModel):
    _name = 'stock.transfer.recreate.wizard'
    _description = 'Stock Transfer Recreate Wizard'

    order_model = fields.Char('Order Model', required=True)
    order_id = fields.Integer('Order ID')
    order_ids = fields.Char('Order IDs')
    is_batch = fields.Boolean('Is Batch')
    line_count = fields.Integer('Number of Lines', readonly=True)
    total_qty = fields.Float('Total Quantity', readonly=True)
    warning_message = fields.Text('Warning Message', readonly=True)

    def action_confirm(self):
        self.ensure_one()
        # Call the appropriate recreation method based on the origin order model
        if self.is_batch and self.order_ids:
            order_ids_list = [int(i) for i in self.order_ids.split(',')]
            if self.order_model == 'sale.order':
                orders = self.env['sale.order'].browse(order_ids_list)
                for order in orders:
                    if order.can_recreate_transfer:
                        order._recreate_delivery_action()
                        order.message_post(body=_("Delivery transfer recreated by %s due to missing or inconsistent picking (batch action).", self.env.user.name))
                orders.invalidate_recordset(['picking_ids', 'delivery_count'])
            elif self.order_model == 'purchase.order':
                orders = self.env['purchase.order'].browse(order_ids_list)
                for order in orders:
                    if order.can_recreate_transfer:
                        order._recreate_receipt_action()
                        order.message_post(body=_("Receipt transfer recreated by %s due to missing or inconsistent picking (batch action).", self.env.user.name))
                orders.invalidate_recordset(['picking_ids', 'incoming_picking_count'])
        else:
            if self.order_model == 'sale.order':
                order = self.env['sale.order'].browse(self.order_id)
                if order.exists():
                    order._recreate_delivery_action()
                    # Invalidate computed fields so picking_ids count refreshes on client
                    order.invalidate_recordset(['picking_ids', 'delivery_count'])
                    order.message_post(body=_("Delivery transfer recreated by %s due to missing or inconsistent picking.", self.env.user.name))
            elif self.order_model == 'purchase.order':
                order = self.env['purchase.order'].browse(self.order_id)
                if order.exists():
                    order._recreate_receipt_action()
                    order.invalidate_recordset(['picking_ids', 'incoming_picking_count'])
                    order.message_post(body=_("Receipt transfer recreated by %s due to missing or inconsistent picking.", self.env.user.name))

        # Reload the current form view so smart button counts update immediately
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
