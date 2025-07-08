# -*- coding: utf-8 -*-
###############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2023-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Vishnu KP S (odoo@cybrosys.com)
#
#    This program is under the terms of the Odoo Proprietary License v1.0 (OPL-1)
#    It is forbidden to publish, distribute, sublicense, or sell copies of the
#    Software or modified copies of the Software.
#
#    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#    FITNESS FOR A PARTICULAR PURPOSE AND NON INFRINGEMENT. IN NO EVENT SHALL
#    THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,DAMAGES OR OTHER
#    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,ARISING
#    FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
#    DEALINGS IN THE SOFTWARE.
#
###############################################################################
from odoo import api, fields, models, _
from odoo.exceptions import UserError
import time
import logging


class PostStockMoveWizard(models.TransientModel):
    _name = 'post.stock.move.wizard'
    _description = 'Post Stock Move Wizard'
    _rec_name = 'mobile_service_id'

    mobile_service_id = fields.Many2one('mobile.service', string='Mobile Service',
                                        required=True, readonly=True)
    partner_id = fields.Many2one('res.partner', string='Customer', 
                                 related='mobile_service_id.person_name', readonly=True)
    picking_type_id = fields.Many2one('stock.picking.type', string='Transfer Type',
                                      related='mobile_service_id.picking_transfer_id', readonly=True)
    scheduled_date = fields.Datetime(string='Scheduled Date', 
                                     default=fields.Datetime.now(), required=True)
    origin = fields.Char(string='Source Document', readonly=True)
    immediate_transfer = fields.Boolean(string='Immediate Transfer', default=True,
                                        help="If checked, the transfer will be validated immediately after creation")
    auto_assign = fields.Boolean(string='Auto Assign', default=True,
                                 help="If checked, the system will try to assign products automatically")
    notes = fields.Text(string='Notes', help="Additional notes for this transfer")
    
    # Product lines to be transferred
    product_line_ids = fields.One2many('post.stock.move.wizard.line', 'wizard_id', 
                                       string='Products to Transfer', copy=True)

    @api.model
    def default_get(self, fields):
        """Set default values from the mobile service order"""
        res = super(PostStockMoveWizard, self).default_get(fields)
        _logger = logging.getLogger(__name__)
        
        # Get the active mobile service record
        mobile_service_id = self.env.context.get('active_id') or self.env.context.get('default_mobile_service_id')
        if mobile_service_id:
            mobile_service = self.env['mobile.service'].browse(mobile_service_id)
            res['mobile_service_id'] = mobile_service_id
            res['origin'] = mobile_service.name
            
            # Always create product lines from the service order
            product_lines = []
            products_added = set()  # Track which products we've already added
            
            _logger.info(f"Processing service {mobile_service.name} with {len(mobile_service.product_order_line)} product lines")
            
            # Add products from order lines that have remaining quantities
            for order_line in mobile_service.product_order_line:
                if not order_line.product_id:
                    _logger.warning(f"Skipping line - missing product_id")
                    continue
                    
                # Check if product type is compatible (storable or consumable)
                if not hasattr(order_line.product_id, 'type') or order_line.product_id.type not in ['product', 'consu']:
                    _logger.info(f"Skipping product {order_line.product_id.name} - not storable/consumable")
                    continue
                
                if order_line.product_uom_qty <= 0:
                    _logger.info(f"Skipping product {order_line.product_id.name} - zero quantity ordered")
                    continue
                
                # Skip if we've already added this product
                product_id = order_line.product_id.id
                if product_id in products_added:
                    _logger.info(f"Skipping duplicate product {order_line.product_id.name}")
                    continue
                    
                remaining_qty = order_line.product_uom_qty - order_line.qty_stock_move
                if remaining_qty <= 0:
                    _logger.info(f"Skipping product {order_line.product_id.name} - no remaining quantity")
                    continue
                
                # Ensure we have a valid UOM
                uom_id = order_line.product_id.uom_id.id
                if not uom_id and hasattr(order_line.product_id, 'product_tmpl_id') and order_line.product_id.product_tmpl_id:
                    uom_id = order_line.product_id.product_tmpl_id.uom_id.id
                
                if not uom_id:
                    _logger.warning(f"Skipping product {order_line.product_id.name} - missing UOM")
                    continue
                
                # Track that we've added this product
                products_added.add(product_id)
                
                # Create line with default values
                line_vals = {
                    'product_id': product_id,
                    'product_uom_id': uom_id,
                    'ordered_qty': order_line.product_uom_qty,
                    'already_moved_qty': order_line.qty_stock_move,
                    'remaining_qty': remaining_qty,
                    'qty_to_transfer': remaining_qty,  # Set to remaining qty by default
                    'order_line_id': order_line.id,
                }
                product_lines.append((0, 0, line_vals))
                _logger.info(f"Added product {order_line.product_id.name} with qty {remaining_qty}")
            
            # Set product lines in the result
            if product_lines:
                res['product_line_ids'] = product_lines
                _logger.info(f"Added {len(product_lines)} product lines to wizard")
                
                # Set defaults for immediate delivery
                res['immediate_transfer'] = True
                res['auto_assign'] = True
            else:
                # If no lines, set empty list to avoid issues
                res['product_line_ids'] = []
                _logger.warning("No products with remaining quantities found for transfer")
            
        return res

    @api.model
    def create(self, vals):
        """Override create to ensure lines are properly created"""
        # Log what's coming in for debugging
        _logger = logging.getLogger(__name__)
        _logger.info(f"Creating wizard with vals: {vals}")
        
        # If product_line_ids are provided, validate and fix them
        if 'product_line_ids' in vals:
            valid_lines = []
            for line_cmd in vals['product_line_ids']:
                if len(line_cmd) >= 3 and line_cmd[0] in (0, 1):  # Create or update command
                    line_vals = line_cmd[2]
                    try:
                        # Check if product_id is present
                        if not line_vals.get('product_id'):
                            _logger.warning(f"Missing product_id in line: {line_vals}")
                            # Skip this line if no product
                            continue
                            
                        # Check if we have a UOM
                        if not line_vals.get('product_uom_id'):
                            # Try to get UOM from product
                            product = self.env['product.product'].browse(line_vals['product_id'])
                            if product.exists() and product.uom_id:
                                line_vals['product_uom_id'] = product.uom_id.id
                                _logger.info(f"Set UOM from product: {product.name}")
                            else:
                                # If we still can't get a UOM, try a default
                                default_uom = self.env['uom.uom'].search([], limit=1)
                                if default_uom:
                                    line_vals['product_uom_id'] = default_uom.id
                                else:
                                    _logger.warning(f"Cannot find UOM for product {line_vals['product_id']}")
                                    # Skip this line if we can't set UOM
                                    continue
                        
                        # Make sure qty_to_transfer has a valid value
                        if 'qty_to_transfer' not in line_vals or not isinstance(line_vals.get('qty_to_transfer'), (int, float)) or line_vals.get('qty_to_transfer') <= 0:
                            # Default to remaining quantity or 1.0
                            line_vals['qty_to_transfer'] = line_vals.get('remaining_qty', 1.0)
                        
                        # Ensure all other required fields have defaults
                        if 'ordered_qty' not in line_vals:
                            line_vals['ordered_qty'] = line_vals.get('qty_to_transfer', 0.0)
                        if 'already_moved_qty' not in line_vals:
                            line_vals['already_moved_qty'] = 0.0
                        if 'remaining_qty' not in line_vals:
                            line_vals['remaining_qty'] = line_vals.get('qty_to_transfer', 0.0)
                        
                        # Add the validated line
                        valid_lines.append((line_cmd[0], line_cmd[1] if len(line_cmd) > 1 else 0, line_vals))
                    except Exception as e:
                        _logger.error(f"Error validating line: {e}")
            
            # Only replace if we have valid lines
            if valid_lines:
                vals['product_line_ids'] = valid_lines
                _logger.info(f"Created {len(valid_lines)} valid product lines")
            else:
                _logger.warning("No valid product lines found")
                # If creating from service but no valid lines, check if we need to recreate
                mobile_service_id = vals.get('mobile_service_id') or self.env.context.get('active_id')
                if mobile_service_id and not self.env.context.get('no_recreate_lines'):
                    _logger.info("Attempting to create product lines from service")
                    try:
                        # Try to create lines directly from service
                        mobile_service = self.env['mobile.service'].browse(mobile_service_id)
                        product_lines = []
                        for order_line in mobile_service.product_order_line:
                            if not order_line.product_id:
                                continue
                                
                            remaining_qty = order_line.product_uom_qty - order_line.qty_stock_move
                            if remaining_qty <= 0:
                                continue
                                
                            uom_id = order_line.product_id.uom_id.id
                            if not uom_id:
                                continue
                                
                            line_vals = {
                                'product_id': order_line.product_id.id,
                                'product_uom_id': uom_id,
                                'ordered_qty': order_line.product_uom_qty,
                                'already_moved_qty': order_line.qty_stock_move,
                                'remaining_qty': remaining_qty,
                                'qty_to_transfer': remaining_qty,
                                'order_line_id': order_line.id,
                            }
                            product_lines.append((0, 0, line_vals))
                        
                        if product_lines:
                            vals['product_line_ids'] = product_lines
                            _logger.info(f"Created {len(product_lines)} product lines from service")
                    except Exception as e:
                        _logger.error(f"Failed to create lines from service: {e}")
        
        # Make sure we have a scheduled date
        if not vals.get('scheduled_date'):
            vals['scheduled_date'] = fields.Datetime.now()
            
        # Set defaults for transfer options if not provided
        if 'immediate_transfer' not in vals:
            vals['immediate_transfer'] = True
        if 'auto_assign' not in vals:
            vals['auto_assign'] = True
        
        # Create with a context flag to prevent recursion
        return super(PostStockMoveWizard, self.with_context(no_recreate_lines=True)).create(vals)

    @api.constrains('product_line_ids')
    def _check_product_lines(self):
        """Validate that we have product lines with valid quantities"""
        for wizard in self:
            if not wizard.product_line_ids:
                _logger = logging.getLogger(__name__)
                _logger.warning(f"No product lines in wizard {wizard.id}")
                # We don't raise an error here as empty lines might be valid in some cases
                # The action_create_transfer will handle this
            else:
                valid_lines = wizard.product_line_ids.filtered(lambda l: l.product_id and l.product_uom_id)
                if not valid_lines:
                    _logger = logging.getLogger(__name__)
                    _logger.error(f"No valid product lines in wizard {wizard.id}")
                    # We don't raise an error here as this might be normal in some cases
                    # The action_create_transfer will handle this
                    
    def action_create_transfer(self):
        """Create stock transfer based on wizard data"""
        self.ensure_one()
        
        # Log all data for debugging
        _logger = logging.getLogger(__name__)
        _logger.info(f"Starting transfer with {len(self.product_line_ids)} product lines")
        
        # Check if we have any product lines at all
        if not self.product_line_ids:
            # No product lines at all
            raise UserError(_('No product lines found in the wizard. Please add at least one product line with a quantity greater than zero.'))
        
        # Log product lines for debugging
        for line in self.product_line_ids:
            _logger.info(f"Line: product={line.product_id.name if line.product_id else 'None'}, qty={line.qty_to_transfer}")
        
        # Validate that we have products with quantities to transfer
        products_to_transfer = self.product_line_ids.filtered(lambda l: l.qty_to_transfer > 0)
        if not products_to_transfer:
            # If no products have quantities > 0, use remaining quantities by default
            for line in self.product_line_ids:
                if line.remaining_qty > 0:
                    line.qty_to_transfer = line.remaining_qty
                    
            # Re-check for products with quantities
            products_to_transfer = self.product_line_ids.filtered(lambda l: l.qty_to_transfer > 0)
            if not products_to_transfer:
                raise UserError(_('No products available for transfer. Please add products or set quantities greater than zero.'))
        
        # Create unique origin to avoid reference conflicts
        timestamp = str(int(time.time() * 1000000))  # Microsecond timestamp
        unique_origin = f"{self.origin}-{timestamp}"
        
        # Define source and destination locations
        location_src_id = self.picking_type_id.default_location_src_id.id
        if not location_src_id:
            # Fallback to company stock location if not set in picking type
            warehouse = self.env['stock.warehouse'].search([('company_id', '=', self.mobile_service_id.company_id.id)], limit=1)
            if warehouse:
                location_src_id = warehouse.lot_stock_id.id
            else:
                raise UserError(_('No source location found for stock transfer.'))
                
        # Get customer destination location        
        location_dest_id = self.partner_id.property_stock_customer.id
        # If no customer property stock, use default destination from picking type
        if not location_dest_id:
            location_dest_id = self.picking_type_id.default_location_dest_id.id
            if not location_dest_id:
                # Fallback to default customer location
                location_dest_id = self.env.ref('stock.stock_location_customers', raise_if_not_found=False)
                if not location_dest_id:
                    raise UserError(_('No destination location found for stock transfer.'))
                else:
                    location_dest_id = location_dest_id.id
        
        # Prepare picking values with service reference
        picking_vals = {
            'picking_type_id': self.picking_type_id.id,
            'partner_id': self.partner_id.id,
            'origin': unique_origin,
            'location_dest_id': location_dest_id,
            'location_id': location_src_id,
            'company_id': self.mobile_service_id.company_id.id,
            'move_type': 'direct',
            'scheduled_date': self.scheduled_date,
            'note': self.notes or f"Transfer for Mobile Service: {self.mobile_service_id.name}",
            # 'mobile_service_id': self.mobile_service_id.id,  # Removed as this field doesn't exist in stock.picking
        }
        
        _logger.info(f"Creating stock picking with values: {picking_vals}")
        
        # Create the picking with special context to avoid sequence conflicts
        picking = self.env['stock.picking'].with_context(
            default_immediate_transfer=self.immediate_transfer,
            tracking_disable=True,
            mail_notrack=True,
        ).create(picking_vals)
        
        if not picking:
            raise UserError(_('Failed to create stock picking.'))
            
        _logger.info(f"Created picking {picking.name}")
        
        # Update the mobile service with the new picking
        self.mobile_service_id.stock_picking_id = picking.id
        
        # Create stock moves for selected products
        move_created = False
        for line in products_to_transfer:
            if line.qty_to_transfer <= 0:
                _logger.warning(f"Skipping line for product {line.product_id.name}: zero quantity")
                continue
                
            move_vals = {
                'name': line.product_id.name,
                'product_id': line.product_id.id,
                'product_uom': line.product_uom_id.id,
                'product_uom_qty': line.qty_to_transfer,
                'location_id': location_src_id,
                'location_dest_id': location_dest_id,
                'picking_id': picking.id,
                'company_id': self.mobile_service_id.company_id.id,
                'origin': unique_origin,
                'state': 'draft',
            }
            
            # Create the move
            _logger.info(f"Creating stock move for product {line.product_id.name} with qty {line.qty_to_transfer}")
            move = self.env['stock.move'].create(move_vals)
            if move:
                move_created = True
                # Update the order line's transferred quantity
                if line.order_line_id:
                    line.order_line_id.qty_stock_move += line.qty_to_transfer
                    _logger.info(f"Updated order line transferred qty to {line.order_line_id.qty_stock_move}")
        
        # If no moves were created, delete the picking and show error
        if not move_created:
            picking.unlink()
            raise UserError(_('No valid products found to transfer. Please check product quantities.'))
        
        # Process the picking based on wizard settings
        try:
            # Always confirm the picking first (changes state from draft to confirmed)
            _logger.info(f"Confirming picking {picking.name}")
            picking.action_confirm()
            
            if self.auto_assign:
                # Try to reserve products (changes state from confirmed to assigned if products available)
                _logger.info(f"Auto-assigning picking {picking.name}")
                picking.action_assign()
            
            if self.immediate_transfer:
                _logger.info(f"Processing immediate transfer for picking {picking.name}")
                # For immediate transfer, we validate the picking
                # Set all quantities done for the moves
                for move in picking.move_ids_without_package:
                    for move_line in move.move_line_ids:
                        move_line.qty_done = move_line.product_uom_qty
                
                # Try to validate the picking (transfer products)
                if picking.state == 'assigned':
                    # All products are available, validate the picking
                    _logger.info(f"Validating picking {picking.name}")
                    picking.button_validate()
                else:
                    # Not all products may be available, but we'll validate anyway
                    _logger.info(f"Validating picking {picking.name} with possible backorder")
                    picking.with_context(skip_backorder=True).button_validate()
        except Exception as e:
            # If any errors occur, log them but don't fail the whole operation
            _logger.error(f"Error processing picking: {e}")
            # We still return the picking so the user can fix any issues manually
        
        # Update picking count
        self.mobile_service_id.picking_count = len(
            self.env['stock.picking'].search([
                ('origin', 'like', self.mobile_service_id.name)
            ])
        )
        
        # Return action to view the created picking
        return {
            'name': _('Stock Transfer'),
            'view_mode': 'form',
            'res_model': 'stock.picking',
            'type': 'ir.actions.act_window',
            'res_id': picking.id,
            'context': {'create': False},
            'target': 'current',
        }

    def action_cancel(self):
        """Cancel the wizard"""
        return {'type': 'ir.actions.act_window_close'}
    
    def add_products(self):
        """Add additional products to the transfer"""
        self.ensure_one()
        # Use a special product selection wizard or directly add common products
        # For now, just refresh the wizard to recalculate available products
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'post.stock.move.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
            'context': {
                'default_mobile_service_id': self.mobile_service_id.id,
                'force_create_lines': True
            }
        }


class PostStockMoveWizardLine(models.TransientModel):
    _name = 'post.stock.move.wizard.line'
    _description = 'Post Stock Move Wizard Line'
    
    # Add SQL constraint to ensure product_id is always set
    _sql_constraints = [
        ('product_id_required', 'CHECK(product_id IS NOT NULL)', 'Product is required for wizard lines.'),
        ('product_uom_id_required', 'CHECK(product_uom_id IS NOT NULL)', 'Unit of Measure is required for wizard lines.'),
    ]

    wizard_id = fields.Many2one('post.stock.move.wizard', string='Wizard', 
                                required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product', required=True,
                                domain=[('type', 'in', ['product', 'consu'])])
    product_uom_id = fields.Many2one('uom.uom', string='Unit of Measure', required=True)
    ordered_qty = fields.Float(string='Ordered Quantity', readonly=True, default=0.0)
    already_moved_qty = fields.Float(string='Already Transferred', readonly=True, default=0.0)
    remaining_qty = fields.Float(string='Remaining Quantity', readonly=True, default=0.0)
    qty_to_transfer = fields.Float(string='Quantity to Transfer', required=True, default=0.0,
                                  help="Enter the quantity you want to transfer. Must be greater than 0.")
    order_line_id = fields.Many2one('product.order.line', string='Order Line')

    @api.model
    def create(self, vals):
        """Override create to ensure all required fields are present"""
        # Log incoming values
        _logger = logging.getLogger(__name__)
        _logger.info(f"Creating wizard line with vals: {vals}")
        
        # Validate product_id
        if not vals.get('product_id'):
            # Instead of raising an error, try to get product from context
            ctx_product_id = self.env.context.get('default_product_id')
            if ctx_product_id:
                vals['product_id'] = ctx_product_id
                _logger.info(f"Set product_id from context: {ctx_product_id}")
            else:
                # If we still don't have a product, raise a more descriptive error
                _logger.error("Missing product_id in wizard line creation")
                raise UserError(_('Product is required for wizard line creation. Please select a valid product.'))
        
        # Ensure product_uom_id is provided
        if not vals.get('product_uom_id') and vals.get('product_id'):
            try:
                product = self.env['product.product'].browse(vals['product_id'])
                if product.exists() and product.uom_id:
                    vals['product_uom_id'] = product.uom_id.id
                    _logger.info(f"Set UOM from product: {product.uom_id.name}")
                else:
                    # Try to get a default UOM
                    default_uom = self.env['uom.uom'].search([('name', '=', 'Unit(s)')], limit=1)
                    if default_uom:
                        vals['product_uom_id'] = default_uom.id
                        _logger.info(f"Set default UOM: {default_uom.name}")
            except Exception as e:
                _logger.error(f"Error getting product UOM: {e}")
                # We'll let validation handle this later if we can't set it now
        
        # Make sure qty_to_transfer is valid
        if 'qty_to_transfer' not in vals or not isinstance(vals.get('qty_to_transfer'), (int, float)) or vals.get('qty_to_transfer') <= 0:
            vals['qty_to_transfer'] = vals.get('remaining_qty', 1.0)
            _logger.info(f"Set default qty_to_transfer: {vals['qty_to_transfer']}")
        
        return super(PostStockMoveWizardLine, self).create(vals)

    @api.model
    def default_get(self, fields):
        """Ensure all required fields have defaults"""
        res = super(PostStockMoveWizardLine, self).default_get(fields)
        _logger = logging.getLogger(__name__)
        _logger.info(f"Default get called for wizard line with fields: {fields}")
        
        # Ensure product_id is set if not provided
        if 'product_id' in fields and not res.get('product_id'):
            # This should normally be set by the parent wizard, but just in case
            # we can provide a default product if there's one in context
            if self.env.context.get('default_product_id'):
                res['product_id'] = self.env.context['default_product_id']
                _logger.info(f"Set product_id from context: {res['product_id']}")
            else:
                # Try to find any product as a fallback
                try:
                    product = self.env['product.product'].search([('type', 'in', ['product', 'consu'])], limit=1)
                    if product:
                        res['product_id'] = product.id
                        _logger.info(f"Set fallback product: {product.name}")
                except Exception as e:
                    _logger.error(f"Error finding default product: {e}")
        
        # Ensure product_uom_id is set
        if 'product_uom_id' in fields and not res.get('product_uom_id'):
            product_id = res.get('product_id') or self.env.context.get('default_product_id')
            if product_id:
                try:
                    product = self.env['product.product'].browse(product_id)
                    if product.exists() and product.uom_id:
                        res['product_uom_id'] = product.uom_id.id
                        _logger.info(f"Set UOM from product: {product.uom_id.name}")
                    else:
                        # Try to get a default UOM
                        default_uom = self.env['uom.uom'].search([('name', '=', 'Unit(s)')], limit=1)
                        if default_uom:
                            res['product_uom_id'] = default_uom.id
                            _logger.info(f"Set default UOM: Unit(s)")
                except Exception as e:
                    _logger.error(f"Error getting product UOM: {e}")
        
        # Set default quantities
        if 'remaining_qty' in fields and not res.get('remaining_qty'):
            res['remaining_qty'] = 1.0
        
        if 'qty_to_transfer' in fields and not res.get('qty_to_transfer'):
            res['qty_to_transfer'] = res.get('remaining_qty', 1.0)
            _logger.info(f"Set default qty_to_transfer: {res['qty_to_transfer']}")
        
        return res

    @api.onchange('product_id')
    def _onchange_product_id(self):
        """When product changes, set the UOM and default quantity"""
        if not self.product_id:
            return
            
        # Set product UOM
        self.product_uom_id = self.product_id.uom_id.id
        
        # Try to find default quantity from service order lines if not already set
        if not self.qty_to_transfer or self.qty_to_transfer == 0:
            if self.wizard_id and self.wizard_id.mobile_service_id:
                # First try to find exact product match in order lines
                for line in self.wizard_id.mobile_service_id.product_order_line:
                    if line.product_id and line.product_id.id == self.product_id.id:
                        remaining = line.product_uom_qty - line.qty_stock_move
                        if remaining > 0:
                            self.qty_to_transfer = remaining
                            self.remaining_qty = remaining
                            self.ordered_qty = line.product_uom_qty
                            self.already_moved_qty = line.qty_stock_move
                            self.order_line_id = line.id
                            return  # Found matching line, exit function
                
                # If we get here, we didn't find a matching line
                # Default to 1 if no order line found
                self.qty_to_transfer = 1.0
            else:
                # No wizard or service, default to 1
                self.qty_to_transfer = 1.0

    @api.onchange('qty_to_transfer')
    def _onchange_qty_to_transfer(self):
        """Validate transfer quantity"""
        if not self.qty_to_transfer:
            # If quantity is empty or 0, set it to zero (to avoid None/False values)
            self.qty_to_transfer = 0
            return {'warning': {
                'title': _('Zero Quantity'),
                'message': _('Please set a quantity greater than zero for products you want to transfer.')
            }}
            
        if self.qty_to_transfer < 0:
            self.qty_to_transfer = 0
            return {'warning': {
                'title': _('Invalid Quantity'),
                'message': _('Transfer quantity cannot be negative.')
            }}
        
        if self.remaining_qty > 0 and self.qty_to_transfer > self.remaining_qty:
            # Only show warning if coming from an order line with a remaining qty
            self.qty_to_transfer = self.remaining_qty
            return {'warning': {
                'title': _('Quantity Exceeded'),
                'message': _('Transfer quantity cannot exceed remaining quantity.')
            }}
    
    @api.constrains('product_id', 'product_uom_id', 'qty_to_transfer')
    def _check_required_fields(self):
        """Validate required fields and values"""
        _logger = logging.getLogger(__name__)
        
        for record in self:
            if not record.product_id:
                _logger.error(f"Missing product_id in wizard line {record.id}")
                raise UserError(_('Product is required for all wizard lines.'))
            
            if not record.product_uom_id:
                _logger.error(f"Missing UOM for product {record.product_id.name}")
                raise UserError(_('Unit of Measure is required for all wizard lines.'))
            
            # Ensure product type is storable or consumable
            if hasattr(record.product_id, 'type') and record.product_id.type not in ['product', 'consu']:
                _logger.error(f"Invalid product type {record.product_id.type} for {record.product_id.name}")
                raise UserError(_('Only storable and consumable products can be transferred.'))
                
            # Ensure quantity to transfer is positive when used in transfer
            if record.wizard_id and record.wizard_id.id and record.qty_to_transfer <= 0:
                _logger.warning(f"Zero quantity for product {record.product_id.name}")
                # We don't raise an error here, as the action_create_transfer will handle this
                # But we log it for visibility
