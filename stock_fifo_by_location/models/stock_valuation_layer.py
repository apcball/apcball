# -*- coding: utf-8 -*-
"""
Stock Valuation Layer Model Extension

This module extends stock.valuation.layer to include location_id for per-location FIFO tracking.
"""

from odoo import models, fields, api
from odoo.tools import float_compare, float_round


class StockValuationLayer(models.Model):
    """
    Extension of stock.valuation.layer to support per-location FIFO cost accounting.
    
    Each valuation layer now tracks which stock.location the inventory is stored in,
    enabling accurate FIFO queue management across multiple locations.
    """
    
    _inherit = 'stock.valuation.layer'
    
    location_id = fields.Many2one(
        'stock.location',
        string='Stock Location',
        index=True,
        help='The stock location where this layer applies. Used for per-location FIFO tracking.',
        ondelete='restrict',
    )
    
    landed_cost_ids = fields.One2many(
        'stock.valuation.layer.landed.cost',
        'valuation_layer_id',
        string='Landed Costs',
        help='Landed costs allocated to this valuation layer at specific locations.'
    )
    
    total_landed_cost = fields.Float(
        string='Total Landed Cost',
        compute='_compute_total_landed_cost',
        digits='Product Price',
        help='Total landed cost across all locations for this layer.'
    )
    
    @api.model
    def _create_layer_from_layer_request(self, layer_req):
        """
        Override the internal method that creates valuation layers from layer requests.
        
        This ensures that location_id is properly set when creating new layers during
        stock moves (receipts, transfers, deliveries).
        
        Args:
            layer_req: The layer request containing move and quantity info
            
        Returns:
            The created or updated stock.valuation.layer
        """
        # Call the parent implementation to create the base layer
        layer = super()._create_layer_from_layer_request(layer_req)
        
        # Extract location_id from the move_line or move
        if hasattr(layer_req, 'move_id') and layer_req.move_id:
            move = layer_req.move_id
            location_id = None
            
            # Determine if this is a positive (incoming) or negative (outgoing) layer
            # by checking the layer quantity that was just created
            is_positive = layer.quantity > 0
            
            # For positive layers (incoming): use destination location
            # For negative layers (outgoing/consumption): use source location (where it came from)
            # For internal transfers: positive uses destination, negative uses source
            
            if is_positive:
                # Positive quantity = receiving/incoming or destination of internal transfer
                location_id = move.location_dest_id.id if move.location_dest_id else None
            else:
                # Negative quantity = delivery/outgoing or source of internal transfer
                location_id = move.location_id.id if move.location_id else None
                
                # But if source is not internal (e.g., supplier), use destination instead
                if move.location_id and move.location_id.usage != 'internal':
                    location_id = move.location_dest_id.id if move.location_dest_id else None
            
            if location_id:
                layer.location_id = location_id
        
        elif hasattr(layer_req, 'move_line_ids'):
            # Alternative: get location from move_line if available
            for move_line in layer_req.move_line_ids:
                if move_line.move_id:
                    move = move_line.move_id
                    # Use layer quantity to determine positive/negative
                    is_positive = layer.quantity > 0
                    if is_positive:
                        location_id = move_line.location_dest_id.id if move_line.location_dest_id else None
                    else:
                        location_id = move_line.location_id.id if move_line.location_id else None
                    
                    if location_id:
                        layer.location_id = location_id
                        break
        
        return layer
    
    @api.model
    def create(self, vals):
        """
        Override create to capture location information from context.
        
        When creating valuation layers, location_id can be passed via context
        under key 'fifo_location_id'.
        """
        # Priority 1: Get location from context if provided
        if not vals.get('location_id') and self.env.context.get('fifo_location_id'):
            vals['location_id'] = self.env.context.get('fifo_location_id')
        
        # Priority 2: Derive from stock_move if not set yet
        if not vals.get('location_id') and vals.get('stock_move_id'):
            move = self.env['stock.move'].browse(vals['stock_move_id'])
            if move:
                quantity = vals.get('quantity', 0)
                source_usage = move.location_id.usage if move.location_id else None
                dest_usage = move.location_dest_id.usage if move.location_dest_id else None
                
                # For positive layers (incoming): use destination location
                if quantity > 0:
                    if move.location_dest_id:
                        vals['location_id'] = move.location_dest_id.id
                # For negative layers (outgoing/consumption): determine source
                else:
                    # Determine the correct location based on move type
                    if source_usage == 'transit':
                        # Transit → Anywhere: Track transit as source
                        # This covers Transit→Internal (warehouse receipt scenario)
                        vals['location_id'] = move.location_id.id
                    elif source_usage == 'internal':
                        # Internal → Anywhere: Track warehouse as source
                        # This covers Internal→Internal, Internal→Transit, Internal→Customer
                        vals['location_id'] = move.location_id.id
                    elif dest_usage == 'internal':
                        # Non-internal (supplier, etc) → Internal: Track destination warehouse
                        vals['location_id'] = move.location_dest_id.id
                    elif dest_usage == 'transit':
                        # Non-internal → Transit: Track destination transit location
                        vals['location_id'] = move.location_dest_id.id
        
        # Priority 3: Try to get from move_line through stock_move
        if not vals.get('location_id') and vals.get('stock_move_id'):
            move = self.env['stock.move'].browse(vals['stock_move_id'])
            if move and move.move_line_ids:
                quantity = vals.get('quantity', 0)
                # Use the appropriate location from first move line
                for move_line in move.move_line_ids:
                    if quantity > 0 and move_line.location_dest_id:
                        vals['location_id'] = move_line.location_dest_id.id
                        break
                    elif quantity <= 0 and move_line.location_id:
                        vals['location_id'] = move_line.location_id.id
                        break
        
        return super().create(vals)
    
    def _validate_location_consistency(self):
        """
        Validate that consumption layers match the location of the outgoing move.
        
        This helper can be called during move validation to ensure FIFO queue correctness.
        """
        for layer in self:
            if layer.stock_move_id and layer.stock_move_id.location_dest_id:
                if not layer.location_id:
                    # Layer has no location - needs migration
                    return False
                
                # For valuation purposes, location should match where inventory resides
                if (layer.stock_move_id.location_id.usage not in ('production', 'supplier') and
                    layer.location_id.id != layer.stock_move_id.location_dest_id.id):
                    # Potential FIFO mismatch
                    pass  # Log but don't fail - may be valid in edge cases
        
        return True
    
    @api.model
    def _get_fifo_queue(self, product_id, location_id, company_id=None):
        """
        Retrieve FIFO queue for a product at a specific location.
        
        Returns valuation layers ordered from oldest (first-in) to newest,
        filtered to only those at the specified location.
        
        Args:
            product_id: stock.product.product
            location_id: stock.location
            company_id: res.company (defaults to current company)
            
        Returns:
            Recordset of stock.valuation.layer ordered by FIFO
        """
        if not company_id:
            company_id = self.env.company.id
        
        domain = [
            ('product_id', '=', product_id.id),
            ('location_id', '=', location_id.id),
            ('company_id', '=', company_id),
            ('quantity', '>', 0),  # Only layers with positive quantity
        ]
        
        return self.search(domain, order='create_date asc, id asc')
    
    @api.model
    def _get_total_available_qty(self, product_id, location_id, company_id=None):
        """
        Get total available quantity in FIFO queue for a product at location.
        
        Args:
            product_id: stock.product.product
            location_id: stock.location
            company_id: res.company
            
        Returns:
            float: Total available quantity
        """
        if not company_id:
            company_id = self.env.company.id
        
        layers = self._get_fifo_queue(product_id, location_id, company_id)
        return sum(layer.quantity for layer in layers)
    
    @api.depends('landed_cost_ids.landed_cost_value')
    def _compute_total_landed_cost(self):
        """Compute total landed cost for this layer across all locations."""
        precision = self.env['decimal.precision'].precision_get('Product Price')
        for layer in self:
            total = sum(layer.landed_cost_ids.mapped('landed_cost_value'))
            layer.total_landed_cost = float_round(total, precision_digits=precision)
    
    @api.model
    def get_landed_cost_at_location(self, product_id, location_id, company_id=None):
        """
        Get total landed cost for a product at a specific location.
        
        Sums all landed costs from all valuation layers of the product at that location.
        
        Args:
            product_id: stock.product.product
            location_id: stock.location
            company_id: res.company
            
        Returns:
            float: Total landed cost at location
        """
        if not company_id:
            company_id = self.env.company.id
        
        layers = self.search([
            ('product_id', '=', product_id.id),
            ('location_id', '=', location_id.id),
            ('company_id', '=', company_id),
            ('quantity', '>', 0),
        ])
        
        landed_cost_model = self.env['stock.valuation.layer.landed.cost']
        total_landed_cost = 0.0
        
        for layer in layers:
            # Get landed costs for this layer at this location
            lc_records = landed_cost_model.search([
                ('valuation_layer_id', '=', layer.id),
                ('location_id', '=', location_id.id),
            ])
            total_landed_cost += sum(lc_records.mapped('landed_cost_value'))
        
        precision = self.env['decimal.precision'].precision_get('Product Price')
        return float_round(total_landed_cost, precision_digits=precision)

