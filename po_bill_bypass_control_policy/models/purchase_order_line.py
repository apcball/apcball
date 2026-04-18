from odoo import api, fields, models

class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    @api.depends('qty_received', 'qty_invoiced', 'product_qty', 'order_id.state', 'order_id.allow_bill_bypass')
    def _compute_qty_to_invoice(self):
        super()._compute_qty_to_invoice()
        for line in self:
            if line.order_id.allow_bill_bypass:
                line.qty_to_invoice = max(0.0, line.product_qty - line.qty_invoiced)

    bill_bypass_user_id = fields.Many2one('res.users', related='order_id.bill_bypass_user_id', string="User", store=True)
    bill_bypass_date = fields.Datetime(related='order_id.bill_bypass_date', string="Date", store=True)
