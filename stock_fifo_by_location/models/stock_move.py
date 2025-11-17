# -*- coding: utf-8 -*-
"""
Stock Move Model Extension

This module extends stock.move to ensure location_id is properly propagated
to valuation layers during inventory moves.
"""

from odoo import models, fields, api


class StockMove(models.Model):
    """
    Extension of stock.move to support per-location FIFO tracking.
    
    This override ensures that when moves are created and validated,
    the destination location is properly captured in valuation layers.
    """
    
    _inherit = 'stock.move'
    
    @api.model
    def create(self, vals):
        """
        Create stock move and prepare context for valuation layer creation.
        
        Adds location context to ensure valuation layers get the correct location_id.
        """
        move = super().create(vals)
        
        # Prepare context with location information for when layers are created
        if move.location_dest_id:
            # Set context for layer creation
            self = self.with_context(fifo_location_id=move.location_dest_id.id)
        
        return move
    
    def _get_fifo_valuation_layer_location(self):
        """
        Determine the appropriate location for FIFO valuation layer.
        
        Rules:
        - Supplier/Production → Internal/Transit: use destination location (new stock)
        - Transit → Internal: use destination location (warehouse receipt)
        - Internal → Transit: use source location (warehouse shipment)
        - Internal → Internal: use destination location (transfer)
        - Internal → Customer/Supplier: use source location (outgoing)
        - Transit → Transit: use destination location
        
        Handles multi-warehouse scenarios with transit locations for inter-warehouse transfers.
        
        Returns:
            stock.location record or None
        """
        self.ensure_one()
        
        if not self.location_id or not self.location_dest_id:
            return None
        
        source_usage = self.location_id.usage
        dest_usage = self.location_dest_id.usage
        
        # Supplier/Production → Internal/Transit (INCOMING NEW STOCK)
        if source_usage in ('supplier', 'production', 'inventory'):
            return self.location_dest_id
        
        # Customer → Internal (RETURN)
        if source_usage == 'customer' and dest_usage == 'internal':
            return self.location_dest_id
        
        # Transit → Internal (WAREHOUSE RECEIPT FROM INTER-WAREHOUSE TRANSFER)
        if source_usage == 'transit' and dest_usage == 'internal':
            return self.location_dest_id
        
        # Transit → Transit (INTER-TRANSIT MOVE)
        if source_usage == 'transit' and dest_usage == 'transit':
            return self.location_dest_id
        
        # Internal → Transit (WAREHOUSE SHIPMENT FOR INTER-WAREHOUSE TRANSFER)
        if source_usage == 'internal' and dest_usage == 'transit':
            return self.location_id
        
        # Internal → Internal (INTERNAL WAREHOUSE TRANSFER)
        if source_usage == 'internal' and dest_usage == 'internal':
            return self.location_dest_id
        
        # Internal → Customer/Supplier/Other (OUTGOING)
        if source_usage == 'internal' and dest_usage != 'internal':
            return self.location_id
        
        # Default: use destination location for unknown cases
        return self.location_dest_id
    
    def _get_valuation_layers_context(self):
        """
        Get context dict to pass when creating/updating valuation layers.
        
        Returns:
            dict with context including fifo_location_id
        """
        location = self._get_fifo_valuation_layer_location()
        if location:
            return {'fifo_location_id': location.id}
        return {}
    
    def _action_done(self, cancel_backorder=False):
        """
        Override move completion to ensure location context is passed to layer operations.
        """
        # Call parent implementation first
        result = super()._action_done(cancel_backorder=cancel_backorder)
        
        # Handle internal transfers - ensure valuation layers are created
        self._create_valuation_layers_for_internal_transfer()
        
        # Update created layers with correct location
        self._update_created_layers_location()
        
        return result
    
    def _update_created_layers_location(self):
        """
        Update valuation layers created by moves with proper location_id.
        
        For internal transfers:
        - Negative layers (outgoing) should have source location
        - Positive layers (incoming) should have destination location
        """
        valuation_layer_model = self.env['stock.valuation.layer']
        
        for move in self:
            # Find layers created by this move
            layers = valuation_layer_model.search([
                ('stock_move_id', '=', move.id),
            ])
            
            for layer in layers:
                # Determine correct location based on layer quantity
                if layer.quantity < 0:
                    # Negative layer (outgoing) - use source location
                    correct_location_id = move.location_id.id if move.location_id else None
                elif layer.quantity > 0:
                    # Positive layer (incoming) - use destination location
                    correct_location_id = move.location_dest_id.id if move.location_dest_id else None
                else:
                    # Zero quantity - skip
                    continue
                
                # Update if location is not correct
                if correct_location_id and layer.location_id.id != correct_location_id:
                    layer.location_id = correct_location_id
    
    def _create_valuation_layers_for_internal_transfer(self):
        """
        Explicitly create valuation layers for internal and transit-related transfers.
        
        Creates layers for:
        - Internal → Internal transfers
        - Transit → Internal transfers (warehouse receipts)
        - Internal → Transit transfers (warehouse shipments)
        
        Transit locations are used in multi-warehouse scenarios for inter-warehouse transfers.
        This ensures proper valuation tracking across all warehouse movements.
        """
        for move in self:
            if move.state != 'done':
                continue
            
            source_usage = move.location_id.usage if move.location_id else None
            dest_usage = move.location_dest_id.usage if move.location_dest_id else None
            
            # Check if this is a transfer (internal-internal, transit-internal, or internal-transit)
            is_transfer = (
                (source_usage == 'internal' and dest_usage == 'internal') or
                (source_usage == 'transit' and dest_usage == 'internal') or
                (source_usage == 'internal' and dest_usage == 'transit')
            )
            
            if not is_transfer:
                continue
            
            # Check if layers already exist
            existing_layers = self.env['stock.valuation.layer'].search([
                ('stock_move_id', '=', move.id),
            ])
            
            if existing_layers:
                # Layers already created, just ensure location_id is set correctly
                for layer in existing_layers:
                    if layer.quantity < 0:
                        # Negative layer (outgoing)
                        # For Internal→Transit: track source warehouse
                        # For Transit→Internal: track source transit
                        # For Internal→Internal: track source warehouse
                        if layer.location_id.id != move.location_id.id:
                            layer.location_id = move.location_id.id
                    elif layer.quantity > 0:
                        # Positive layer (incoming)
                        # Always track destination (transit or warehouse)
                        if layer.location_id.id != move.location_dest_id.id:
                            layer.location_id = move.location_dest_id.id
            else:
                # Layers don't exist - create them manually
                # Get current cost from existing layers of this product
                current_cost = 0.0
                existing_product_layers = self.env['stock.valuation.layer'].search([
                    ('product_id', '=', move.product_id.id),
                    ('stock_move_id', '!=', move.id),
                    ('id', '<', move.id),
                ], order='id desc', limit=1)
                
                if existing_product_layers:
                    current_cost = existing_product_layers[0].unit_cost
                else:
                    # Use product's standard price as fallback
                    current_cost = move.product_id.standard_price or 0.0
                
                # Create outgoing layer (negative, from source)
                if move.location_id:
                    self.env['stock.valuation.layer'].create({
                        'stock_move_id': move.id,
                        'product_id': move.product_id.id,
                        'location_id': move.location_id.id,
                        'quantity': -move.product_qty,
                        'unit_cost': current_cost,
                        'value': -move.product_qty * current_cost,
                        'company_id': move.company_id.id,
                        'description': f'Internal transfer from {move.location_id.name} to {move.location_dest_id.name}',
                    })
                
                # Create incoming layer (positive, to destination)
                if move.location_dest_id:
                    self.env['stock.valuation.layer'].create({
                        'stock_move_id': move.id,
                        'product_id': move.product_id.id,
                        'location_id': move.location_dest_id.id,
                        'quantity': move.product_qty,
                        'unit_cost': current_cost,
                        'value': move.product_qty * current_cost,
                        'company_id': move.company_id.id,
                        'description': f'Internal transfer from {move.location_id.name} to {move.location_dest_id.name}',
                    })
    
    def _create_account_move_line(self, debit_line_vals, credit_line_vals, writeoff_line_vals=None):
        """
        Override to ensure valuation layers get location_id during accounting posting.
        
        For internal transfers, we may need to ensure layers are created if not already.
        """
        # Call parent to create accounting entries
        result = super()._create_account_move_line(
            debit_line_vals, credit_line_vals, writeoff_line_vals
        )
        
        # For internal transfers, ensure location_id is set on created layers
        for move in self:
            if move.location_id.usage == 'internal' and move.location_dest_id.usage == 'internal':
                # This is an internal transfer
                ctx = move._get_valuation_layers_context()
                location_id = ctx.get('fifo_location_id') if ctx else None
                
                if location_id:
                    layers = self.env['stock.valuation.layer'].search([
                        ('stock_move_id', '=', move.id),
                    ])
                    if layers:
                        layers.write({'location_id': location_id})
        
        return result
