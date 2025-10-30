from odoo import models, fields, api, _
from odoo.exceptions import UserError


class TransferFromBatchWizard(models.TransientModel):
    _name = 'transfer.from.batch.wizard'
    _description = 'Wizard to Create Transfer from Batch'

    batch_id = fields.Many2one('stock.picking.batch', string='Source Batch', readonly=True)
    origin = fields.Char(string='Source', readonly=True)
    dest_location_id = fields.Many2one(
        'stock.location', 
        string='Destination Location', 
        required=True,
        domain="[('usage', '=', 'internal')]"
    )

    def create_transfer_from_batch(self):
        """Create a new internal transfer based on the batch"""
        if not self.batch_id:
            raise UserError(_('No batch selected.'))
        
        # Get the source location from the batch's pickings
        # Use the destination of the original batch as the source for the new transfer
        source_location = None
        if self.batch_id.picking_ids:
            # Use the destination of the first picking as the source for the new transfer
            source_location = self.batch_id.picking_ids[0].location_dest_id
        
        if not source_location:
            raise UserError(_('Could not determine source location from the batch.'))
        
        # Create a new picking for internal transfer
        picking_vals = {
            'picking_type_id': self._get_internal_transfer_type().id,
            'location_id': source_location.id,
            'location_dest_id': self.dest_location_id.id,
            'origin': self.origin or self.batch_id.name,
            'batch_id': False,  # Don't assign to any batch initially
            'source_batch_id': self.batch_id.id,  # Track the source batch
        }
        
        new_picking = self.env['stock.picking'].create(picking_vals)
        
        # Copy moves from the batch's pickings to the new picking
        product_qty_dict = {}
        
        # Aggregate quantities by product across all pickings in the batch
        for picking in self.batch_id.picking_ids:
            for move in picking.move_ids_without_package:
                product_id = move.product_id.id
                if product_id in product_qty_dict:
                    product_qty_dict[product_id] += move.product_uom_qty
                else:
                    product_qty_dict[product_id] = move.product_uom_qty
        
        # Create moves for the new picking based on aggregated quantities
        for product_id, qty in product_qty_dict.items():
            product = self.env['product.product'].browse(product_id)
            self.env['stock.move'].create({
                'name': product.name,
                'product_id': product_id,
                'product_uom_qty': qty,
                'product_uom': product.uom_id.id,
                'picking_id': new_picking.id,
                'location_id': source_location.id,
                'location_dest_id': self.dest_location_id.id,
                'state': 'draft',
            })
        
        # Show the new picking to the user
        return {
            'name': _('Internal Transfer'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'view_mode': 'form',
            'res_id': new_picking.id,
            'target': 'current',
        }
    
    def _get_internal_transfer_type(self):
        """Get the internal transfer picking type"""
        company_id = self.env.company.id
        picking_type = self.env['stock.picking.type'].search([
            ('code', '=', 'internal'),
            ('warehouse_id.company_id', '=', company_id)
        ], limit=1)
        
        if not picking_type:
            raise UserError(_('No internal transfer operation type found for your company.'))
        
        return picking_type