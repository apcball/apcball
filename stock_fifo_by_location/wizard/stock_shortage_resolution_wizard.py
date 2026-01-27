# -*- coding: utf-8 -*-
"""
Shortage Resolution Wizard

This wizard helps users resolve stock shortage issues by:
1. Showing available stock in other warehouses
2. Suggesting internal transfers
3. Auto-creating transfer orders
"""

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class StockShortageResolutionWizard(models.TransientModel):
    """
    Wizard to help resolve stock shortage by suggesting transfers from other warehouses.
    """
    
    _name = 'stock.shortage.resolution.wizard'
    _description = 'Stock Shortage Resolution Wizard'
    
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
        readonly=True
    )
    
    dest_warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Destination Warehouse',
        required=True,
        readonly=True,
        help='Warehouse where stock is needed'
    )
    
    quantity_needed = fields.Float(
        string='Quantity Needed',
        required=True,
        readonly=True,
        digits='Product Unit of Measure'
    )
    
    quantity_available = fields.Float(
        string='Available at Destination',
        readonly=True,
        digits='Product Unit of Measure'
    )
    
    shortage_qty = fields.Float(
        string='Shortage',
        compute='_compute_shortage',
        digits='Product Unit of Measure'
    )
    
    fallback_line_ids = fields.One2many(
        'stock.shortage.resolution.line',
        'wizard_id',
        string='Available in Other Warehouses'
    )
    
    resolution_type = fields.Selection([
        ('transfer', 'Create Internal Transfer'),
        ('purchase', 'Create Purchase Order'),
        ('adjust', 'Inventory Adjustment'),
        ('cancel', 'Cancel Operation'),
    ], string='Resolution', default='transfer')
    
    auto_confirm = fields.Boolean(
        string='Auto Confirm Transfer',
        default=False,
        help='Automatically confirm created transfer'
    )
    
    notes = fields.Text(string='Notes')
    
    @api.depends('quantity_needed', 'quantity_available')
    def _compute_shortage(self):
        for wizard in self:
            wizard.shortage_qty = max(0, wizard.quantity_needed - wizard.quantity_available)
    
    @api.model
    def default_get(self, fields_list):
        """Populate wizard with shortage information."""
        res = super().default_get(fields_list)
        
        # Get from context
        product_id = self.env.context.get('default_product_id')
        warehouse_id = self.env.context.get('default_dest_warehouse_id')
        quantity = self.env.context.get('default_quantity_needed', 0)
        
        if not product_id or not warehouse_id:
            return res
        
        product = self.env['product.product'].browse(product_id)
        warehouse = self.env['stock.warehouse'].browse(warehouse_id)
        fifo_service = self.env['fifo.service']
        
        # Get available quantity at destination
        available_qty = fifo_service.get_available_qty_at_warehouse(
            product, warehouse, self.env.company.id
        )
        
        res.update({
            'product_id': product_id,
            'dest_warehouse_id': warehouse_id,
            'quantity_needed': quantity,
            'quantity_available': available_qty,
        })
        
        return res
    
    @api.onchange('product_id', 'dest_warehouse_id')
    def _onchange_product_warehouse(self):
        """Load available stock from other warehouses."""
        if not self.product_id or not self.dest_warehouse_id:
            return
        
        fifo_service = self.env['fifo.service']
        
        # Find fallback warehouses
        shortage = self.quantity_needed - self.quantity_available
        if shortage <= 0:
            return
        
        fallback_whs = fifo_service._find_fallback_warehouses(
            self.product_id,
            self.dest_warehouse_id,
            shortage,
            self.env.company.id
        )
        
        # Create lines
        lines = []
        for fb in fallback_whs:
            lines.append((0, 0, {
                'source_warehouse_id': fb['warehouse_id'],
                'available_qty': fb['available_qty'],
                'transfer_qty': min(fb['available_qty'], shortage),
                'selected': fb['available_qty'] >= shortage,  # Auto-select if enough
            }))
        
        self.fallback_line_ids = lines
    
    def action_create_transfers(self):
        """Create internal transfers from selected warehouses."""
        self.ensure_one()
        
        if not self.fallback_line_ids:
            raise UserError(_('No source warehouses available.'))
        
        selected_lines = self.fallback_line_ids.filtered(lambda l: l.selected and l.transfer_qty > 0)
        
        if not selected_lines:
            raise UserError(_('Please select at least one warehouse and specify transfer quantity.'))
        
        pickings = self.env['stock.picking']
        
        for line in selected_lines:
            # Create transfer
            picking_type = self.env['stock.picking.type'].search([
                ('code', '=', 'internal'),
                ('warehouse_id', '=', self.dest_warehouse_id.id),
            ], limit=1)
            
            if not picking_type:
                picking_type = self.env['stock.picking.type'].search([
                    ('code', '=', 'internal'),
                ], limit=1)
            
            picking_vals = {
                'picking_type_id': picking_type.id,
                'location_id': line.source_warehouse_id.lot_stock_id.id,
                'location_dest_id': self.dest_warehouse_id.lot_stock_id.id,
                'origin': f'Shortage Resolution: {self.product_id.display_name}',
                'move_ids': [(0, 0, {
                    'name': self.product_id.display_name,
                    'product_id': self.product_id.id,
                    'product_uom_qty': line.transfer_qty,
                    'product_uom': self.product_id.uom_id.id,
                    'location_id': line.source_warehouse_id.lot_stock_id.id,
                    'location_dest_id': self.dest_warehouse_id.lot_stock_id.id,
                })],
            }
            
            picking = self.env['stock.picking'].create(picking_vals)
            pickings |= picking
            
            # Auto-confirm if requested
            if self.auto_confirm:
                picking.action_confirm()
        
        # Show created transfers
        action = self.env.ref('stock.action_picking_tree_all').read()[0]
        action['domain'] = [('id', 'in', pickings.ids)]
        action['context'] = {}
        
        return action
    
    def action_cancel(self):
        """Cancel and close wizard."""
        return {'type': 'ir.actions.act_window_close'}


class StockShortageResolutionLine(models.TransientModel):
    """Line item for shortage resolution wizard."""
    
    _name = 'stock.shortage.resolution.line'
    _description = 'Shortage Resolution Line'
    _order = 'available_qty desc'
    
    wizard_id = fields.Many2one(
        'stock.shortage.resolution.wizard',
        required=True,
        ondelete='cascade'
    )
    
    source_warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Source Warehouse',
        required=True
    )
    
    available_qty = fields.Float(
        string='Available',
        required=True,
        digits='Product Unit of Measure'
    )
    
    transfer_qty = fields.Float(
        string='Transfer Qty',
        digits='Product Unit of Measure'
    )
    
    selected = fields.Boolean(
        string='Select',
        default=False
    )
    
    @api.onchange('selected')
    def _onchange_selected(self):
        """Auto-fill transfer quantity when selected."""
        if self.selected and not self.transfer_qty:
            shortage = self.wizard_id.shortage_qty
            self.transfer_qty = min(self.available_qty, shortage)
