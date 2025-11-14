from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)


class StockCurrentTransferWizard(models.TransientModel):
    _name = 'stock.current.transfer.wizard'
    _description = 'Stock Current Transfer Wizard'

    source_location_id = fields.Many2one(
        'stock.location', 
        string='Source Location',
        readonly=True
    )
    destination_location_id = fields.Many2one(
        'stock.location', 
        string='Destination Location', 
        required=True,
        domain="[('usage', '=', 'internal'), ('id', '!=', source_location_id)]"
    )
    picking_type_id = fields.Many2one(
        'stock.picking.type', 
        string='Operation Type',
        readonly=True
    )
    immediate_transfer = fields.Boolean(
        string='Immediate Transfer', 
        default=True
    )
    scheduled_date = fields.Datetime(
        string='Scheduled Date', 
        default=fields.Datetime.now
    )
    notes = fields.Text(string='Notes')
    line_ids = fields.One2many(
        'stock.current.transfer.wizard.line', 
        'wizard_id', 
        string='Products'
    )
    selected_products_data = fields.Text(
        string='Selected Products Data',
        help="JSON data of selected products from the stock report"
    )

    @api.model
    def default_get(self, fields_list):
        """Override to pre-populate with selected products"""
        res = super().default_get(fields_list)
        
        _logger.info(f"default_get called with fields: {fields_list}")
        
        # Get selected products from context
        selected_products = self.env.context.get('default_selected_products', [])
        _logger.info(f"Selected products from context: {selected_products}")
        
        if selected_products and isinstance(selected_products, list):
            lines = []
            source_locations = set()
            
            for idx, product_data in enumerate(selected_products):
                _logger.info(f"Processing product {idx}: {product_data}")
                
                # Ensure product_data is a dict
                if not isinstance(product_data, dict):
                    _logger.warning(f"Product data {idx} is not a dict: {type(product_data)}")
                    continue
                    
                product_id = product_data.get('productId') or product_data.get('product_id')
                location_id = product_data.get('locationId') or product_data.get('location_id')
                
                if not product_id or not location_id:
                    _logger.warning(f"Missing product_id or location_id in product {idx}")
                    continue
                
                source_locations.add(location_id)
                
                line_vals = {
                    'product_id': product_id,
                    'source_location_id': location_id,
                    'available_quantity': product_data.get('quantity', 0),
                    'quantity_to_transfer': product_data.get('quantity', 0),
                    'uom_id': product_data.get('uomId') or product_data.get('uom_id'),
                }
                _logger.info(f"Created line values: {line_vals}")
                lines.append((0, 0, line_vals))
            
            if lines:
                _logger.info(f"Adding {len(lines)} transfer lines")
                res['line_ids'] = lines
            else:
                _logger.warning("No valid lines created from selected products")
            
            # Set source location if all products are from same location
            if len(source_locations) == 1:
                source_loc = list(source_locations)[0]
                _logger.info(f"Setting source location to {source_loc}")
                res['source_location_id'] = source_loc
            elif len(source_locations) > 1:
                _logger.info(f"Multiple source locations found: {source_locations}, will let user choose")
            
            # Set default picking type
            picking_type = self._get_picking_type()
            if picking_type:
                _logger.info(f"Setting picking type to {picking_type.name}")
                res['picking_type_id'] = picking_type.id
            else:
                _logger.warning("Could not find picking type")
        else:
            _logger.info("No selected products in context")
        
        return res

    def _get_picking_type(self):
        """Get appropriate picking type for internal transfer"""
        picking_type = self.env['stock.picking.type'].search([
            ('code', '=', 'internal'),
            ('company_id', '=', self.env.company.id),
        ], limit=1)
        
        if not picking_type:
            # Create default internal transfer picking type if not exists
            warehouse = self.env['stock.warehouse'].search([('company_id', '=', self.env.company.id)], limit=1)
            if warehouse:
                picking_type = warehouse.int_type_id
        
        return picking_type

    @api.constrains('destination_location_id')
    def _check_destination_location(self):
        """Validate destination location is different from source"""
        for record in self:
            if record.destination_location_id and record.source_location_id:
                if record.destination_location_id == record.source_location_id:
                    raise ValidationError(_("Destination location must be different from source location."))

    def action_create_transfer(self):
        """Create stock transfer from wizard data as draft"""
        self.ensure_one()
        
        _logger.info(f"action_create_transfer called: source_location={self.source_location_id}, dest={self.destination_location_id}, lines={len(self.line_ids)}")
        
        if not self.line_ids:
            raise UserError(_("Please add at least one product to transfer."))
        
        if not self.destination_location_id:
            raise UserError(_("Please select a destination location."))
        
        # Validate all lines
        for line in self.line_ids:
            if line.quantity_to_transfer <= 0:
                raise UserError(_("Transfer quantity must be greater than 0 for product %s.") % line.product_id.name)
            if line.quantity_to_transfer > line.available_quantity:
                raise UserError(
                    _("Cannot transfer more than available quantity for product %s. "
                      "Available: %s, Requested: %s") % (
                        line.product_id.name,
                        line.available_quantity,
                        line.quantity_to_transfer
                    )
                )
        
        try:
            # Get source location (all must be same)
            source_location_id = self.source_location_id.id or self.line_ids[0].source_location_id.id
            picking_type_id = self.picking_type_id.id if self.picking_type_id else None
            
            # If no picking type set, try to find or use warehouse default
            if not picking_type_id:
                _logger.info("No picking type set, attempting to find default")
                picking_type = self._get_picking_type()
                if picking_type:
                    picking_type_id = picking_type.id
            
            if not picking_type_id:
                raise UserError(_("Cannot determine picking type for this transfer. Please contact your administrator."))
            
            _logger.info(f"Creating transfer: source={source_location_id}, dest={self.destination_location_id.id}, picking_type={picking_type_id}")
            
            # Create stock picking in draft state
            picking_vals = {
                'picking_type_id': picking_type_id,
                'location_id': source_location_id,
                'location_dest_id': self.destination_location_id.id,
                'scheduled_date': self.scheduled_date,
                'origin': _('Stock Current Transfer'),
                'note': self.notes,
            }
            
            picking = self.env['stock.picking'].create(picking_vals)
            _logger.info(f"Created picking {picking.name}")
            
            # Create stock moves for each line
            for line in self.line_ids:
                self.env['stock.move'].create({
                    'name': _('Transfer: %s') % line.product_id.name,
                    'product_id': line.product_id.id,
                    'product_uom_qty': line.quantity_to_transfer,
                    'product_uom': line.uom_id.id,
                    'location_id': line.source_location_id.id,
                    'location_dest_id': self.destination_location_id.id,
                    'picking_id': picking.id,
                    'picking_type_id': picking_type_id,
                    'origin': _('Stock Current Transfer'),
                })
            
            # Attempt to confirm and prepare if immediate transfer
            if self.immediate_transfer:
                try:
                    picking.action_confirm()
                    picking.action_assign()
                    
                    # Set quantities done and validate
                    for move in picking.move_ids:
                        if move.state in ['assigned', 'partially_available']:
                            for move_line in move.move_line_ids:
                                move_line.qty_done = move_line.product_uom_qty
                    
                    picking.button_validate()
                    _logger.info("Transfer %s automatically validated", picking.name)
                except Exception as e:
                    _logger.warning("Could not auto-validate transfer %s: %s", picking.name, str(e))
                    # Leave as confirmed but not validated
            
            _logger.info(f"Transfer completed successfully: {picking.name}")
            
            # Return action to view the created picking
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'stock.picking',
                'res_id': picking.id,
                'view_mode': 'form',
                'target': 'current',
            }
        except UserError:
            raise
        except Exception as e:
            _logger.error("Error creating transfer: %s", str(e))
            raise UserError(_("Failed to create transfer: %s") % str(e))


class StockCurrentTransferWizardLine(models.TransientModel):
    _name = 'stock.current.transfer.wizard.line'
    _description = 'Stock Current Transfer Wizard Line'

    wizard_id = fields.Many2one(
        'stock.current.transfer.wizard', 
        required=True, 
        ondelete='cascade'
    )
    product_id = fields.Many2one(
        'product.product', 
        string='Product', 
        required=True
    )
    source_location_id = fields.Many2one(
        'stock.location', 
        string='Source Location', 
        required=True
    )
    available_quantity = fields.Float(
        string='Available Quantity', 
        readonly=True,
        digits='Product Unit of Measure'
    )
    quantity_to_transfer = fields.Float(
        string='Quantity to Transfer', 
        required=True,
        digits='Product Unit of Measure'
    )
    uom_id = fields.Many2one(
        'uom.uom', 
        string='Unit of Measure', 
        readonly=True
    )

    @api.constrains('quantity_to_transfer')
    def _check_quantity(self):
        """Validate transfer quantity against available quantity"""
        for line in self:
            if line.quantity_to_transfer < 0:
                raise ValidationError(_("Transfer quantity cannot be negative."))
            if line.quantity_to_transfer > line.available_quantity:
                raise ValidationError(
                    _("Cannot transfer more than available quantity for product %s. "
                      "Available: %s, Requested: %s") % (
                        line.product_id.name,
                        line.available_quantity,
                        line.quantity_to_transfer
                    )
                )

    @api.onchange('product_id', 'source_location_id')
    def _onchange_product_location(self):
        """Update available quantity when product or location changes"""
        # Only update if we don't already have a valid available_quantity
        # (e.g., from default_get context)
        if self.product_id and self.source_location_id:
            # If available_quantity is already set (from context), don't override
            if self.available_quantity > 0:
                return
            
            # Get current stock for this product/location
            stock_report = self.env['stock.current.report'].search([
                ('product_id', '=', self.product_id.id),
                ('location_id', '=', self.source_location_id.id)
            ], limit=1)
            
            if stock_report:
                self.available_quantity = stock_report.quantity
                if self.quantity_to_transfer == 0:
                    self.quantity_to_transfer = stock_report.quantity
            else:
                # Only set to 0 if available_quantity was 0
                if self.available_quantity == 0:
                    self.quantity_to_transfer = 0

    @api.model
    def create(self, vals):
        """Set default UOM from product"""
        if vals.get('product_id') and not vals.get('uom_id'):
            product = self.env['product.product'].browse(vals['product_id'])
            vals['uom_id'] = product.uom_id.id
        return super().create(vals)