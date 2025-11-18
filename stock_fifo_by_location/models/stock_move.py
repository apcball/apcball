# -*- coding: utf-8 -*-
"""
Stock Move Model Extension

This module extends stock.move to ensure location_id is properly propagated
to valuation layers during inventory moves.
"""

from odoo import models, fields, api
from odoo.tools import float_round, float_compare


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
        
        Also handles landed cost allocation proportionally to receiving location.
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
                
                # After layers are set with correct locations, allocate landed costs
                self._allocate_landed_cost_on_transfer(move, existing_layers)
            else:
                # Layers don't exist - create them manually
                # Use FIFO service to calculate cost from source location
                fifo_service = self.env['fifo.service']
                
                try:
                    # Calculate FIFO cost with landed cost from source location
                    fifo_result = fifo_service.calculate_fifo_cost_with_landed_cost(
                        product_id=move.product_id.id,
                        location_id=move.location_id.id,
                        quantity=move.product_qty,
                        company_id=move.company_id.id
                    )
                    current_cost = fifo_result.get('unit_cost', 0.0)
                except Exception as e:
                    # Fallback to standard price if FIFO calculation fails
                    self.env['ir.logging'].create({
                        'name': 'stock_fifo_by_location',
                        'type': 'server',
                        'level': 'warning',
                        'message': f'FIFO calculation failed for move {move.reference}: {str(e)}',
                        'path': 'stock.move',
                        'line': '0',
                        'func': '_create_valuation_layers_for_internal_transfer',
                    })
                    current_cost = move.product_id.standard_price or 0.0
                
                # Create outgoing layer (negative, from source)
                outgoing_layer = None
                incoming_layer = None
                
                if move.location_id:
                    outgoing_layer = self.env['stock.valuation.layer'].create({
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
                    incoming_layer = self.env['stock.valuation.layer'].create({
                        'stock_move_id': move.id,
                        'product_id': move.product_id.id,
                        'location_id': move.location_dest_id.id,
                        'quantity': move.product_qty,
                        'unit_cost': current_cost,
                        'value': move.product_qty * current_cost,
                        'company_id': move.company_id.id,
                        'description': f'Internal transfer from {move.location_id.name} to {move.location_dest_id.name}',
                    })
                
                # Allocate landed costs for newly created layers
                if outgoing_layer and incoming_layer:
                    created_layers = outgoing_layer | incoming_layer
                    self._allocate_landed_cost_on_transfer(move, created_layers)
    
    def _allocate_landed_cost_on_transfer(self, move, layers):
        """
        Allocate landed costs proportionally during internal transfers.
        
        When transferring inventory between locations, the landed cost portion
        of the inventory value should be transferred proportionally to the
        receiving location.
        
        Args:
            move: stock.move record (the transfer)
            layers: stock.valuation.layer records created for this move
        """
        source_location = move.location_id
        dest_location = move.location_dest_id
        product = move.product_id
        company = move.company_id
        qty_transferred = move.product_qty
        
        if not (source_location and dest_location):
            return
        
        # Get landed costs at source location for this product
        source_lc_value = self.env['stock.valuation.layer'].get_landed_cost_at_location(
            product, source_location, company.id
        )
        
        if source_lc_value == 0:
            # No landed costs to transfer
            return
        
        # Get total quantity available at source location
        source_qty = self.env['stock.valuation.layer']._get_total_available_qty(
            product, source_location, company.id
        )
        
        # Calculate proportion of landed cost to transfer
        precision = self.env['decimal.precision'].precision_get('Product Price')
        if source_qty > 0:
            proportion = qty_transferred / source_qty
            lc_to_transfer = source_lc_value * proportion
            lc_to_transfer = float_round(lc_to_transfer, precision_digits=precision)
        else:
            lc_to_transfer = 0.0
        
        # Get or create valuation layers for landed cost tracking
        # The negative layer (source) and positive layer (destination)
        negative_layer = None
        positive_layer = None
        
        for layer in layers:
            if layer.quantity < 0 and layer.location_id.id == source_location.id:
                negative_layer = layer
            elif layer.quantity > 0 and layer.location_id.id == dest_location.id:
                positive_layer = layer
        
        if not (negative_layer and positive_layer):
            return
        
        # Create landed cost allocation records
        # For source: negative landed cost (reducing source location's landed cost)
        # For destination: positive landed cost (adding to destination location's landed cost)
        
        # We need to allocate from existing layers to the new locations
        self._transfer_landed_cost_between_locations(
            product, source_location, dest_location, company,
            qty_transferred, lc_to_transfer, negative_layer, positive_layer
        )
        
        # Record the allocation in history
        self.env['stock.landed.cost.allocation'].create({
            'move_id': move.id,
            'quantity_transferred': qty_transferred,
            'source_layer_landed_cost_before': source_lc_value,
            'source_layer_landed_cost_after': source_lc_value - lc_to_transfer,
            'destination_layer_landed_cost_before': self.env['stock.valuation.layer'].get_landed_cost_at_location(
                product, dest_location, company.id
            ),
            'destination_layer_landed_cost_after': self.env['stock.valuation.layer'].get_landed_cost_at_location(
                product, dest_location, company.id
            ) + lc_to_transfer,
            'landed_cost_transferred': lc_to_transfer,
            'notes': f'Automatic landed cost allocation during transfer: {qty_transferred} units of {product.name}',
        })
    
    def _transfer_landed_cost_between_locations(self, product, source_loc, dest_loc,
                                                company, qty_transferred, lc_amount,
                                                source_layer, dest_layer):
        """
        Transfer landed cost from source location to destination location.
        
        This method:
        1. Reduces landed cost from source location valuation layers
        2. Adds landed cost to destination location valuation layers
        3. Creates tracking records in stock.valuation.layer.landed.cost
        
        Args:
            product: stock.product.product
            source_loc: source stock.location
            dest_loc: destination stock.location
            company: res.company
            qty_transferred: quantity being transferred
            lc_amount: landed cost amount to transfer
            source_layer: negative stock.valuation.layer at source
            dest_layer: positive stock.valuation.layer at destination
        """
        lc_model = self.env['stock.valuation.layer.landed.cost']
        precision = self.env['decimal.precision'].precision_get('Product Price')
        
        # Get all landed cost records for the product at source location
        source_lc_records = lc_model.search([
            ('product_id', '=', product.id),
            ('location_id', '=', source_loc.id),
            ('company_id', '=', company.id),
        ], order='create_date asc')
        
        if not source_lc_records:
            # No landed costs to transfer - create a new one at destination
            lc_model.create({
                'valuation_layer_id': dest_layer.id,
                'location_id': dest_loc.id,
                'landed_cost_value': lc_amount,
                'quantity': dest_layer.quantity,
            })
            return
        
        # Calculate how much landed cost to take from each source layer (FIFO)
        remaining_lc = lc_amount
        
        for source_lc_record in source_lc_records:
            if float_compare(remaining_lc, 0, precision_digits=precision) <= 0:
                break
            
            # How much can we take from this record?
            lc_available = source_lc_record.landed_cost_value
            lc_to_take = min(remaining_lc, lc_available)
            
            # Update source location record (reduce by amount transferred)
            new_source_value = source_lc_record.landed_cost_value - lc_to_take
            if float_compare(new_source_value, 0, precision_digits=precision) > 0:
                source_lc_record.landed_cost_value = float_round(
                    new_source_value, precision_digits=precision
                )
            else:
                # Delete if nothing left
                source_lc_record.unlink()
            
            remaining_lc = float_round(
                remaining_lc - lc_to_take, precision_digits=precision
            )
        
        # Add landed cost to destination location
        # Create or update destination landed cost record
        existing_dest_lc = lc_model.search([
            ('valuation_layer_id', '=', dest_layer.id),
            ('location_id', '=', dest_loc.id),
        ], limit=1)
        
        if existing_dest_lc:
            existing_dest_lc.landed_cost_value = float_round(
                existing_dest_lc.landed_cost_value + lc_amount,
                precision_digits=precision
            )
        else:
            lc_model.create({
                'valuation_layer_id': dest_layer.id,
                'location_id': dest_loc.id,
                'landed_cost_value': lc_amount,
                'quantity': dest_layer.quantity,
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
