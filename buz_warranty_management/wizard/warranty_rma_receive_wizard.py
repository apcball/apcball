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
    line_ids = fields.One2many(
        'warranty.rma.receive.line',
        'wizard_id',
        string='Return Lines'
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
        
        # Load default line from claim product if available
        if 'claim_id' in self._context:
            claim = self.env['warranty.claim'].browse(self._context['claim_id'])
            if claim.product_id:
                res['line_ids'] = [(0, 0, {
                    'product_id': claim.product_id.id,
                    'lot_id': claim.lot_id.id,
                    'qty': 1.0,
                })]
        
        return res

    def action_create_rma_picking(self):
        self.ensure_one()
        
        if not self.picking_type_id:
            raise UserError(_('Please configure RMA IN Picking Type in Warranty settings.'))
        
        if not self.location_dest_id:
            raise UserError(_('Please configure Repair Location in Warranty settings.'))
        
        if not self.line_ids:
            raise UserError(_('Please add at least one return line.'))
        
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
        
        # Create moves for each line
        for line in self.line_ids:
            move_vals = {
                'name': f'RMA: {line.product_id.name}',
                'product_id': line.product_id.id,
                'product_uom_qty': line.qty,
                'product_uom': line.product_id.uom_id.id,
                'picking_id': picking.id,
                'location_id': customer_location.id,
                'location_dest_id': self.location_dest_id.id,
            }
            
            if line.lot_id:
                move_vals['lot_ids'] = [(6, 0, [line.lot_id.id])]
            
            move = self.env['stock.move'].create(move_vals)
            
            # Link to claim lines if matching product exists
            claim_lines = self.claim_id.claim_line_ids.filtered(
                lambda l: l.product_id == line.product_id
            )
            if claim_lines:
                claim_lines[0].write({'move_ids': [(4, move.id)]})
        
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


class WarrantyRMAReceiveLine(models.TransientModel):
    _name = 'warranty.rma.receive.line'
    _description = 'Warranty RMA Receive Line'

    wizard_id = fields.Many2one(
        'warranty.rma.receive.wizard',
        required=True,
        ondelete='cascade'
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
    uom_id = fields.Many2one(
        'uom.uom',
        string='Unit of Measure',
        related='product_id.uom_id',
        readonly=True
    )
    reason = fields.Text(
        string='Return Reason',
        help='Reason for returning this specific part'
    )
