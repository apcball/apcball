from odoo import models, fields, api, _
from odoo.exceptions import UserError


class WarrantyRMAReceiveWizard(models.TransientModel):
    _name = 'warranty.rma.receive.wizard'
    _description = 'Warranty RMA Receive Wizard'

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
        string='Product',
        required=True
    )
    lot_id = fields.Many2one(
        'stock.lot',
        string='Lot/Serial Number',
        domain="[('product_id', '=', product_id)]"
    )
    qty = fields.Float(
        string='Quantity',
        default=1.0,
        required=True
    )
    picking_type_id = fields.Many2one(
        'stock.picking.type',
        string='Picking Type',
        required=True
    )
    location_dest_id = fields.Many2one(
        'stock.location',
        string='Destination Location',
        required=True,
        domain="[('usage', '=', 'internal')]"
    )
    notes = fields.Text(string='Notes')
    generate_return_label = fields.Boolean(
        string='Generate Return Label',
        default=True
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        ICP = self.env['ir.config_parameter'].sudo()
        
        picking_type_id = ICP.get_param('buz_warranty_management.warranty_rma_in_picking_type_id')
        if picking_type_id:
            res['picking_type_id'] = int(picking_type_id)
        
        location_id = ICP.get_param('buz_warranty_management.warranty_repair_location_id')
        if location_id:
            res['location_dest_id'] = int(location_id)
        
        return res

    def action_create_rma_picking(self):
        self.ensure_one()
        
        if not self.picking_type_id:
            raise UserError(_('Please configure RMA IN Picking Type in Warranty settings.'))
        
        if not self.location_dest_id:
            raise UserError(_('Please configure Repair Location in Warranty settings.'))
        
        # Get customer location
        customer_location = self.partner_id.property_stock_customer
        
        # Create picking
        picking_vals = {
            'partner_id': self.partner_id.id,
            'picking_type_id': self.picking_type_id.id,
            'location_id': customer_location.id,
            'location_dest_id': self.location_dest_id.id,
            'origin': self.claim_id.name,
            'note': self.notes,
        }
        picking = self.env['stock.picking'].create(picking_vals)
        
        # Create move
        move_vals = {
            'name': f'RMA: {self.product_id.name}',
            'product_id': self.product_id.id,
            'product_uom_qty': self.qty,
            'product_uom': self.product_id.uom_id.id,
            'picking_id': picking.id,
            'location_id': customer_location.id,
            'location_dest_id': self.location_dest_id.id,
        }
        
        if self.lot_id:
            move_vals['lot_ids'] = [(6, 0, [self.lot_id.id])]
        
        self.env['stock.move'].create(move_vals)
        
        # Link picking to claim
        self.claim_id.write({
            'rma_in_picking_ids': [(4, picking.id)],
            'status': 'awaiting_return'
        })
        
        # Post message
        self.claim_id.message_post(
            body=_('RMA IN picking created: %s', picking.name),
            subject=_('RMA IN Created')
        )
        
        return {
            'name': _('RMA IN Picking'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'res_id': picking.id,
            'view_mode': 'form',
            'target': 'current',
        }
