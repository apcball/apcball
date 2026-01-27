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
    main_product_already_rma = fields.Boolean(
        string='Main Product Already in RMA',
        readonly=True,
        help='Indicates if the main product is already in an existing RMA picking'
    )

    def _check_main_product_in_existing_rma(self, claim):
        """Check if the main product is already in existing RMA pickings"""
        if not claim.product_id:
            return False
        
        # Check all RMA IN pickings for this claim
        for picking in claim.rma_in_picking_ids:
            for move in picking.move_ids:
                if move.product_id == claim.product_id:
                    return True
        return False

    def _get_existing_rma_info(self, claim):
        """Get information about existing RMA pickings for the main product"""
        if not claim.product_id:
            return []
        
        existing_rmas = []
        for picking in claim.rma_in_picking_ids:
            for move in picking.move_ids:
                if move.product_id == claim.product_id:
                    existing_rmas.append({
                        'picking_name': picking.name,
                        'state': picking.state,
                        'qty': move.product_uom_qty,
                    })
        return existing_rmas

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
        
        # Handle claim and check main product status
        if 'claim_id' in self._context:
            claim = self.env['warranty.claim'].browse(self._context['claim_id'])
            
            # Check if main product is already in existing RMA
            main_product_in_rma = self._check_main_product_in_existing_rma(claim)
            res['main_product_already_rma'] = main_product_in_rma
        
        return res

    def action_fetch_claim_products(self):
        """Fetch the main product from the warranty claim (the product customer is returning)"""
        self.ensure_one()
        
        if not self.claim_id:
            raise UserError(_('No warranty claim selected.'))
        
        # Get existing product IDs to avoid duplicates
        existing_product_ids = self.line_ids.mapped('product_id').ids
        lines_to_add = []
        added_count = 0
        skipped_count = 0
        
        # Add main product if not already in RMA and not already in lines
        if self.claim_id.product_id and not self.main_product_already_rma:
            if self.claim_id.product_id.id not in existing_product_ids:
                # Ensure product is active and available
                if self.claim_id.product_id.active:
                    line_data = {
                        'product_id': self.claim_id.product_id.id,
                        'qty': 1.0,
                        'is_auto_populated': True,
                        'reason': 'Main product from warranty claim',
                    }
                    # Only add lot_id if it exists and is valid for this product
                    if self.claim_id.lot_id and self.claim_id.lot_id.product_id == self.claim_id.product_id:
                        line_data['lot_id'] = self.claim_id.lot_id.id
                    
                    lines_to_add.append((0, 0, line_data))
                    added_count += 1
                else:
                    skipped_count += 1
            else:
                skipped_count += 1
        elif self.main_product_already_rma:
            skipped_count += 1
        
        # Add all lines at once
        if lines_to_add:
            self.line_ids = lines_to_add
        
        # Show appropriate message
        if added_count > 0:
            message = _('Successfully added the main product from the warranty claim.')
            if skipped_count > 0:
                message += _(' %d product(s) were skipped (already in RMA or duplicate).') % skipped_count
            self.env['bus.bus']._sendone(
                self.env.user.partner_id,
                'simple_notification',
                {
                    'title': _('Product Fetched'),
                    'message': message,
                    'type': 'info',
                    'sticky': False,
                }
            )
        elif self.main_product_already_rma:
            self.env['bus.bus']._sendone(
                self.env.user.partner_id,
                'simple_notification',
                {
                    'title': _('Product Not Added'),
                    'message': _('The main product is already in an existing RMA picking.'),
                    'type': 'warning',
                    'sticky': False,
                }
            )
        else:
            raise UserError(_('No main product found in this warranty claim.'))
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'warranty.rma.receive.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
            'context': self.env.context,
        }

    def action_create_rma_picking(self):
        self.ensure_one()
        
        if not self.picking_type_id:
            raise UserError(_('Please configure RMA IN Picking Type in Warranty settings.'))
        
        if not self.location_dest_id:
            raise UserError(_('Please configure Repair Location in Warranty settings.'))
        
        if not self.line_ids:
            raise UserError(_('Please add at least one return line.'))
        
        # Validate all lines before creating picking
        for line in self.line_ids:
            if not line.product_id:
                raise UserError(_('All return lines must have a product selected.'))
            if line.qty <= 0:
                raise UserError(_('Quantity must be greater than 0 for all return lines.'))
            # Validate lot/serial number if product requires tracking
            if line.product_id.tracking != 'none' and not line.lot_id:
                raise UserError(_('Product %s requires a lot/serial number.') % line.product_id.name)
        
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
    is_auto_populated = fields.Boolean(
        string='Auto Populated',
        readonly=True,
        help='Indicates if this line was automatically populated from the claim'
    )
