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
        
        # Get selected products from context
        selected_products = self.env.context.get('default_selected_products', [])
        if selected_products:
            lines = []
            for product_data in selected_products:
                line_vals = {
                    'product_id': product_data.get('productId'),
                    'source_location_id': product_data.get('locationId'),
                    'available_quantity': product_data.get('quantity', 0),
                    'quantity_to_transfer': product_data.get('quantity', 0),
                    'uom_id': product_data.get('uomId'),
                }
                lines.append((0, 0, line_vals))
            
            res['line_ids'] = lines
            
            # Set source location if all products are from same location
            if len(selected_products) == 1:
                res['source_location_id'] = selected_products[0].get('locationId')
            elif selected_products:
                # Check if all products are from same location
                first_location = selected_products[0].get('locationId')
                if all(p.get('locationId') == first_location for p in selected_products):
                    res['source_location_id'] = first_location
            
            # Set default picking type
            res['picking_type_id'] = self._get_picking_type().id if self._get_picking_type() else False
            
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
        """Create stock transfer from wizard data"""
        self.ensure_one()
        
        if not self.line_ids:
            raise UserError(_("Please add at least one product to transfer."))
        
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
        
        # Create stock picking
        picking_vals = {
            'picking_type_id': self.picking_type_id.id,
            'location_id': self.source_location_id.id or self.line_ids[0].source_location_id.id,
            'location_dest_id': self.destination_location_id.id,
            'scheduled_date': self.scheduled_date,
            'origin': _('Stock Current Transfer'),
            'note': self.notes,
            'move_ids': [],
        }
        
        # Create stock moves
        move_vals_list = []
        for line in self.line_ids:
            move_vals = {
                'name': _('Transfer: %s') % line.product_id.name,
                'product_id': line.product_id.id,
                'product_uom_qty': line.quantity_to_transfer,
                'product_uom': line.uom_id.id,
                'location_id': line.source_location_id.id,
                'location_dest_id': self.destination_location_id.id,
                'picking_type_id': self.picking_type_id.id,
                'origin': _('Stock Current Transfer'),
            }
            move_vals_list.append((0, 0, move_vals))
        
        picking_vals['move_ids'] = move_vals_list
        
        # Create the picking
        picking = self.env['stock.picking'].create(picking_vals)
        
        # Validate the transfer if immediate
        if self.immediate_transfer:
            try:
                picking.action_confirm()
                picking.action_assign()
                
                # Create stock move lines and validate
                for move in picking.move_ids:
                    if move.state == 'assigned':
                        for move_line in move.move_line_ids:
                            move_line.qty_done = move_line.product_uom_qty
                
                picking.button_validate()
            except Exception as e:
                _logger.error("Error validating transfer: %s", str(e))
                raise UserError(_("Transfer created but validation failed: %s") % str(e))
        
        # Return action to view the created picking
        return {
            'name': _('Stock Transfer'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'res_id': picking.id,
            'view_mode': 'form',
            'target': 'current',
            'context': self.env.context,
        }


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
        if self.product_id and self.source_location_id:
            # Get current stock for this product/location
            stock_report = self.env['stock.current.report'].search([
                ('product_id', '=', self.product_id.id),
                ('location_id', '=', self.source_location_id.id)
            ], limit=1)
            
            if stock_report:
                self.available_quantity = stock_report.quantity
                self.quantity_to_transfer = min(stock_report.quantity, self.quantity_to_transfer)
            else:
                self.available_quantity = 0
                self.quantity_to_transfer = 0
        else:
            self.available_quantity = 0
            self.quantity_to_transfer = 0

    @api.model
    def create(self, vals):
        """Set default UOM from product"""
        if vals.get('product_id') and not vals.get('uom_id'):
            product = self.env['product.product'].browse(vals['product_id'])
            vals['uom_id'] = product.uom_id.id
        return super().create(vals)