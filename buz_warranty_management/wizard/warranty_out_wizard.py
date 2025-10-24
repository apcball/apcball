from odoo import models, fields, api, _
from odoo.exceptions import UserError


class WarrantyOutWizard(models.TransientModel):
    _name = 'warranty.out.wizard'
    _description = 'Out-of-Warranty Quotation Wizard'

    claim_id = fields.Many2one(
        'warranty.claim',
        string='Warranty Claim',
        required=True
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        required=True
    )
    product_id = fields.Many2one(
        'product.product',
        string='Service Product',
        domain=[('type', '=', 'service')],
        required=True,
        help='Service product to be used for repair'
    )
    repair_cost = fields.Float(
        string='Repair Cost',
        required=True,
        help='Estimated cost for out-of-warranty repair'
    )
    description = fields.Text(
        string='Description',
        help='Additional details for the quotation'
    )
    quantity = fields.Float(
        string='Quantity',
        default=1.0,
        required=True
    )

    def action_create_quotation(self):
        self.ensure_one()
        
        if not self.product_id:
            raise UserError(_('Please select a service product.'))
        
        if self.repair_cost <= 0:
            raise UserError(_('Repair cost must be greater than zero.'))
        
        SaleOrder = self.env['sale.order']
        
        order_vals = {
            'partner_id': self.partner_id.id,
            'date_order': fields.Datetime.now(),
            'note': f'Out-of-warranty repair for claim {self.claim_id.name}\n{self.description or ""}',
        }
        
        sale_order = SaleOrder.create(order_vals)
        
        order_line_vals = {
            'order_id': sale_order.id,
            'product_id': self.product_id.id,
            'product_uom_qty': self.quantity,
            'price_unit': self.repair_cost,
            'name': self.product_id.name + (f'\n{self.description}' if self.description else ''),
        }
        
        self.env['sale.order.line'].create(order_line_vals)
        
        self.claim_id.write({
            'quotation_id': sale_order.id,
            'cost_estimate': self.repair_cost,
        })
        
        self.claim_id.message_post(
            body=_('Out-of-warranty quotation %s created.') % sale_order.name,
            subject=_('Quotation Created')
        )
        
        return {
            'name': _('Sale Order'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': sale_order.id,
            'view_mode': 'form',
            'target': 'current',
        }
