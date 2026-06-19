# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class InternalConsumeRequestLine(models.Model):
    _name = 'internal.consume.request.line'
    _description = 'Internal Consumable Request Line'
    _order = 'sequence, id'

    sequence = fields.Integer(string='Sequence', default=10)
    
    line_number = fields.Integer(
        string='No.',
        compute='_compute_line_number',
        store=True,
        help='Line number in the request'
    )
    
    request_id = fields.Many2one(
        'internal.consume.request',
        string='Request',
        required=True,
        ondelete='cascade',
        index=True
    )
    
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
        domain="[('type', 'in', ['consu', 'product'])]"
    )
    
    description = fields.Text(
        string='Description',
        compute='_compute_description',
        store=True,
        readonly=False
    )
    
    product_uom_id = fields.Many2one(
        'uom.uom',
        string='Unit of Measure',
        required=True,
        domain="[('category_id', '=', product_uom_category_id)]"
    )
    
    product_uom_category_id = fields.Many2one(
        related='product_id.uom_id.category_id',
        readonly=True
    )
    
    qty_requested = fields.Float(
        string='Quantity Requested',
        required=True,
        default=1.0,
        digits='Product Unit of Measure'
    )
    
    qty_done = fields.Float(
        string='Quantity Done',
        compute='_compute_qty_done',
        digits='Product Unit of Measure'
    )
    
    available_qty = fields.Float(
        string='Available Quantity',
        compute='_compute_available_qty',
        digits='Product Unit of Measure',
        help='Available quantity in the source location'
    )
    
    location_id = fields.Many2one(
        related='request_id.location_id',
        string='Source Location',
        readonly=True
    )
    
    state = fields.Selection(
        related='request_id.state',
        string='Status',
        store=True,
        readonly=True
    )
    
    analytic_distribution = fields.Json(
        string='Analytic Distribution',
        copy=True,
        store=True,
        default={}
    )
    
    analytic_precision = fields.Integer(
        string="Analytic Precision",
        default=lambda self: self.env['decimal.precision'].precision_get('Percentage Analytic')
    )

    @api.depends('request_id', 'sequence')
    def _compute_line_number(self):
        """Compute line number based on sequence order"""
        for line in self:
            if line.request_id:
                # Get all lines sorted by sequence
                sorted_lines = line.request_id.line_ids.sorted('sequence')
                # Find the position of current line
                for index, sorted_line in enumerate(sorted_lines, 1):
                    if sorted_line.id == line.id:
                        line.line_number = index
                        break
            else:
                line.line_number = 0

    @api.depends('product_id')
    def _compute_description(self):
        for line in self:
            if line.product_id:
                line.description = line.product_id.display_name
            else:
                line.description = ''

    @api.depends('request_id.picking_id', 'request_id.picking_id.move_ids', 
                 'request_id.picking_id.move_ids.quantity', 'product_id')
    def _compute_qty_done(self):
        for line in self:
            qty_done = 0.0
            if line.request_id.picking_id:
                for move in line.request_id.picking_id.move_ids:
                    if move.product_id == line.product_id:
                        qty_done += move.quantity
            line.qty_done = qty_done

    @api.depends('product_id', 'location_id', 'product_uom_id', 'request_id.warehouse_id')
    def _compute_available_qty(self):
        """Compute available quantity from warehouse's stock location and child locations"""
        for line in self:
            if line.product_id and line.location_id:
                # Get available quantity from stock.quant
                # Search in location and all child locations
                quants = self.env['stock.quant'].search([
                    ('product_id', '=', line.product_id.id),
                    ('location_id', 'child_of', line.location_id.id),
                    ('location_id.usage', '=', 'internal'),  # Only internal locations
                ])
                
                # Calculate available = on_hand - reserved
                available_qty = 0.0
                for quant in quants:
                    available_qty += (quant.quantity - quant.reserved_quantity)
                
                # Convert to line UOM if different
                if line.product_uom_id and line.product_uom_id != line.product_id.uom_id:
                    available_qty = line.product_id.uom_id._compute_quantity(
                        available_qty,
                        line.product_uom_id
                    )
                
                line.available_qty = max(0.0, available_qty)  # Never negative
            else:
                line.available_qty = 0.0

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.product_uom_id = self.product_id.uom_id
            self.description = self.product_id.display_name

    @api.constrains('qty_requested')
    def _check_qty_requested(self):
        for line in self:
            if line.qty_requested <= 0:
                raise ValidationError(_('Quantity requested must be greater than zero.'))

    @api.constrains('product_id')
    def _check_product_type(self):
        for line in self:
            if line.product_id and line.product_id.type not in ('consu', 'product'):
                raise ValidationError(
                    _('Product %s is not a consumable or stockable product.') % line.product_id.display_name
                )

    @api.constrains('analytic_distribution')
    def _check_analytic_distribution(self):
        """Ensure analytic distribution is not empty (for visibility, real check is in action_submit)"""
        # Constraint disabled here - real validation happens in action_submit() on the parent model
        # This allows users to create/duplicate lines and fill analytics incrementally
        pass

    @api.onchange('qty_requested', 'available_qty')
    def _onchange_qty_check_availability(self):
        """Warning if requested qty > available qty"""
        for line in self:
            if line.qty_requested > 0 and line.available_qty > 0:
                if line.qty_requested > line.available_qty:
                    return {
                        'warning': {
                            'title': _('Insufficient Stock'),
                            'message': _(
                                'Requested quantity (%.2f) exceeds available quantity (%.2f) '
                                'for product %s in location %s'
                            ) % (
                                line.qty_requested,
                                line.available_qty,
                                line.product_id.display_name,
                                line.location_id.complete_name if line.location_id else ''
                            )
                        }
                    }

    def copy(self, default=None):
        """Override copy method to ensure all fields are properly duplicated"""
        if default is None:
            default = {}
        
        # IMPORTANT: Preserve the request_id (parent relationship)
        if 'request_id' not in default and self.request_id:
            default['request_id'] = self.request_id.id
        
        # Copy key fields explicitly
        if 'product_id' not in default and self.product_id:
            default['product_id'] = self.product_id.id
        
        if 'qty_requested' not in default:
            default['qty_requested'] = self.qty_requested
        
        if 'product_uom_id' not in default and self.product_uom_id:
            default['product_uom_id'] = self.product_uom_id.id
        
        if 'description' not in default and self.description:
            default['description'] = self.description
        
        # Ensure analytic_distribution is copied
        if 'analytic_distribution' not in default:
            if self.analytic_distribution:
                default['analytic_distribution'] = self.analytic_distribution
            else:
                default['analytic_distribution'] = {}
        
        # Ensure sequence doesn't duplicate
        if 'sequence' not in default:
            default['sequence'] = self.sequence + 10
        
        return super().copy(default)

    def action_duplicate_line(self):
        """Action to duplicate the current line"""
        self.ensure_one()
        
        # Ensure the current line is saved before duplication
        if not self.id:
            # If line not saved yet, save it first
            self.flush()
        
        # Create a copy of this line
        copied_line = self.copy()
        
        # Refresh the parent form to show the new line
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
