from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


class StockPicking(models.Model):
    _inherit = 'stock.picking'
    
    # Field to track if this transfer was created from a batch
    source_batch_id = fields.Many2one(
        'stock.picking.batch',
        string='Source Batch',
        readonly=True,
        help="The batch from which this transfer was created"
    )
    
    # Computed field for easier conditional logic
    is_from_batch = fields.Boolean(
        string='Created from Batch',
        compute='_compute_is_from_batch',
        store=True,
        help="True if this transfer was created from a batch"
    )
    
    @api.depends('source_batch_id')
    def _compute_is_from_batch(self):
        """Compute if the transfer was created from a batch"""
        for picking in self:
            picking.is_from_batch = bool(picking.source_batch_id)

    def action_select_all_products(self):
        """Add all products available in the source location to the transfer"""
        self.ensure_one()
        
        # Check if picking is in draft state
        if self.state != 'draft':
            raise UserError(_('You can only add products to draft transfers.'))
        
        # Get products from source location
        source_location = self.location_id
        if not source_location:
            raise UserError(_('Please select a source location first.'))
        
        # Get all quant records from the source location with available quantity (including reserved)
        # We use the _get_available_quantity function to get real available quantity
        quants = self.env['stock.quant'].search([
            ('location_id', '=', source_location.id),
            ('product_id.type', '=', 'product')  # Only stockable products
        ])
        
        # Create moves for quants that have available quantity after reservations
        existing_product_ids = set()
        for move in self.move_ids_without_package:
            existing_product_ids.add(move.product_id.id)
        
        for quant in quants:
            # Get the truly available quantity (on hand - reserved) at this location
            available_qty = self.env['stock.quant']._get_available_quantity(
                quant.product_id, 
                source_location
            )
            
            if available_qty > 0 and quant.product_id.id not in existing_product_ids:
                # Create a new stock move for the product
                stock_move = self.env['stock.move'].create({
                    'name': quant.product_id.display_name,
                    'product_id': quant.product_id.id,
                    'product_uom_qty': available_qty,
                    'product_uom': quant.product_id.uom_id.id,
                    'picking_id': self.id,
                    'location_id': source_location.id,
                    'location_dest_id': self.location_dest_id.id,
                    'picking_type_id': self.picking_type_id.id,
                    'state': 'draft',
                })
        
        return True

    def action_clear_lines(self):
        """Clear all move lines from the picking"""
        self.ensure_one()
        
        # Check if picking is in draft state
        if self.state != 'draft':
            raise UserError(_('You can only clear lines from draft transfers.'))
        
        # Delete all move lines
        for move_line in self.move_line_ids:
            move_line.unlink()
        
        # Also delete moves if they exist
        for move in self.move_ids_without_package:
            move.unlink()
        
        return True

    def action_transfer_now(self):
        """Confirm and validate the picking in one step"""
        self.ensure_one()
        
        # Confirm the picking if it's not confirmed yet
        if self.state == 'draft':
            self.action_confirm()
        
        # Check availability if needed
        if self.state in ['confirmed', 'waiting']:
            self.action_assign()
        
        # Validate the picking
        if self.state in ['assigned', 'confirmed', 'waiting']:
            # For each move line, set the quantity to match the move's demand if not already set
            for move_line in self.move_line_ids:
                # Set the quantity to match the move's demand quantity
                # Only update if quantity is 0 or not set (user has not specified a value)
                if float_compare(move_line.quantity, 0, precision_rounding=move_line.product_uom_id.rounding) == 0:
                    move_line.quantity = move_line.move_id.product_uom_qty
            
            # Validate the picking
            self.button_validate()
        
        return True

    def action_add_to_batch(self):
        """Open wizard to add the receipt to an existing batch or create a new one"""
        self.ensure_one()
        
        # Check if picking is already in a batch
        if self.batch_id:
            raise UserError(_('This receipt is already part of batch %s.') % self.batch_id.name)
        
        # Check if picking is in an appropriate state for batching
        if self.state in ['done', 'cancel']:
            raise UserError(_('You cannot add a receipt that is already done or cancelled to a batch.'))
        
        # Open the wizard to select batch option
        wizard_context = {
            'default_picking_id': self.id,
            'default_new_batch_name': _('Batch from %s') % self.name,
        }
        
        return {
            'name': _('Add to Batch Transfer'),
            'type': 'ir.actions.act_window',
            'res_model': 'add.to.batch.wizard',
            'view_mode': 'form',
            'view_type': 'form',
            'target': 'new',
            'context': wizard_context,
        }