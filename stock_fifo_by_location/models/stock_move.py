# -*- coding: utf-8 -*-
"""
Stock Move Model Extension

This module extends stock.move to ensure warehouse_id is properly propagated
to valuation layers during inventory moves.
"""

from odoo import models, fields, api
from odoo.tools import float_round, float_compare


class StockMove(models.Model):
    """
    Extension of stock.move to support per-warehouse FIFO tracking.
    
    This override ensures that when moves are created and validated,
    the destination warehouse is properly captured in valuation layers.
    """
    
    _inherit = 'stock.move'
    
    @api.model
    def create(self, vals):
        """
        Create stock move and prepare context for valuation layer creation.
        
        Adds warehouse context to ensure valuation layers get the correct warehouse_id.
        """
        move = super().create(vals)
        
        # Prepare context with warehouse information for when layers are created
        if move.location_dest_id and move.location_dest_id.warehouse_id:
            # Set context for layer creation
            self = self.with_context(fifo_warehouse_id=move.location_dest_id.warehouse_id.id)
        
        return move
    
    def _get_fifo_valuation_layer_warehouse(self):
        """
        Determine the appropriate warehouse for FIFO valuation layer.
        
        Rules:
        - Supplier/Production → Internal/Transit: use destination warehouse (new stock)
        - Transit → Internal: use destination warehouse (warehouse receipt)
        - Internal → Transit: use source warehouse (warehouse shipment)
        - Internal → Internal (same warehouse): NO new layers (intra-warehouse move)
        - Internal → Internal (different warehouse): use dest warehouse (inter-warehouse)
        - Internal → Customer/Supplier: use source warehouse (outgoing)
        - Transit → Transit: use destination transit warehouse
        
        Returns:
            stock.warehouse record or None
        """
        self.ensure_one()
        
        if not self.location_id or not self.location_dest_id:
            return None
        
        source_usage = self.location_id.usage
        dest_usage = self.location_dest_id.usage
        source_wh = self.location_id.warehouse_id
        dest_wh = self.location_dest_id.warehouse_id
        
        # Supplier/Production → Internal/Transit (INCOMING NEW STOCK)
        if source_usage in ('supplier', 'production', 'inventory'):
            return dest_wh
        
        # Customer → Internal (RETURN)
        if source_usage == 'customer' and dest_usage == 'internal':
            return dest_wh
        
        # Transit → Internal (WAREHOUSE RECEIPT FROM INTER-WAREHOUSE TRANSFER)
        if source_usage == 'transit' and dest_usage == 'internal':
            return dest_wh
        
        # Transit → Transit (INTER-TRANSIT MOVE)
        if source_usage == 'transit' and dest_usage == 'transit':
            return dest_wh
        
        # Internal → Transit (WAREHOUSE SHIPMENT FOR INTER-WAREHOUSE TRANSFER)
        if source_usage == 'internal' and dest_usage == 'transit':
            return source_wh
        
        # Internal → Internal (TRANSFER)
        if source_usage == 'internal' and dest_usage == 'internal':
            # Check if same warehouse or different warehouse
            if source_wh and dest_wh and source_wh.id == dest_wh.id:
                # Same warehouse - intra-warehouse move, no new layers needed
                return None
            else:
                # Different warehouses - inter-warehouse transfer
                return dest_wh
        
        # Internal → Customer/Supplier/Other (OUTGOING)
        if source_usage == 'internal' and dest_usage != 'internal':
            return source_wh
        
        # Default: use destination warehouse for unknown cases
        return dest_wh
    
    def _get_valuation_layers_context(self):
        """
        Get context dict to pass when creating/updating valuation layers.
        
        Returns:
            dict with context including fifo_warehouse_id
        """
        warehouse = self._get_fifo_valuation_layer_warehouse()
        if warehouse:
            return {'fifo_warehouse_id': warehouse.id}
        return {}
    
    def _action_done(self, cancel_backorder=False):
        """
        Override move completion to ensure warehouse context is passed to layer operations.
        
        Core principle: Let Odoo create layers first, then enhance with warehouse_id.
        For inter-warehouse transfers, if Odoo doesn't create layers, we create them.
        """
        # Call parent implementation first - this creates the standard layers
        result = super()._action_done(cancel_backorder=cancel_backorder)
        
        # Check and create layers for inter-warehouse transfers if needed
        self._ensure_inter_warehouse_valuation_layers()
        
        # After standard layer creation, update them with correct warehouse_id
        self._update_created_layers_warehouse()
        
        # Handle landed cost allocation for inter-warehouse transfers
        self._allocate_landed_cost_for_inter_warehouse()
        
        return result
    
    def _ensure_inter_warehouse_valuation_layers(self):
        """
        Ensure valuation layers exist for inter-warehouse transfers.
        
        Odoo standard may not create layers for internal transfers.
        If no layers exist after parent _action_done, create them manually.
        """
        import logging
        _logger = logging.getLogger(__name__)
        
        valuation_layer_model = self.env['stock.valuation.layer']
        
        for move in self:
            # Only process done moves
            if move.state != 'done':
                continue
            
            product = move.product_id
            
            # Skip if product is not storable or not using real-time valuation
            if product.type != 'product' or product.valuation != 'real_time':
                continue
            
            source_wh = move.location_id.warehouse_id if move.location_id else None
            dest_wh = move.location_dest_id.warehouse_id if move.location_dest_id else None
            
            # Only for inter-warehouse transfers (different warehouses)
            if not (source_wh and dest_wh and source_wh.id != dest_wh.id):
                continue
            
            # Check if layers already exist for this move
            existing_layers = valuation_layer_model.search([
                ('stock_move_id', '=', move.id),
            ])
            
            if existing_layers:
                # Layers exist - Odoo created them, we'll just enhance with warehouse_id
                _logger.info(f"Inter-warehouse move {move.name}: {len(existing_layers)} layers exist")
                continue
            
            # No layers exist - need to create them manually
            _logger.info(f"Inter-warehouse move {move.name}: Creating valuation layers")
            
            company = move.company_id
            
            # Get cost from FIFO service with fallback to standard_price
            fifo_service = self.env['fifo.service']
            fifo_result = fifo_service.calculate_fifo_cost_with_landed_cost(
                product, source_wh, move.product_qty, company.id
            )
            
            # Extract unit cost
            if isinstance(fifo_result, dict):
                unit_cost = fifo_result.get('unit_cost', 0.0)
            else:
                unit_cost = float(fifo_result) if fifo_result else 0.0
            
            # Fallback to standard price if still zero
            if unit_cost <= 0:
                unit_cost = product.standard_price or 0.0
                _logger.info(f"Using standard_price fallback: {unit_cost}")
            
            # Create negative layer at source warehouse
            valuation_layer_model.sudo().create({
                'stock_move_id': move.id,
                'product_id': product.id,
                'warehouse_id': source_wh.id,
                'quantity': -move.product_qty,
                'unit_cost': unit_cost,
                'value': -move.product_qty * unit_cost,
                'company_id': company.id,
                'description': f'Inter-warehouse: {source_wh.name} → {dest_wh.name}',
            })
            
            # Create positive layer at destination warehouse
            valuation_layer_model.sudo().create({
                'stock_move_id': move.id,
                'product_id': product.id,
                'warehouse_id': dest_wh.id,
                'quantity': move.product_qty,
                'unit_cost': unit_cost,
                'value': move.product_qty * unit_cost,
                'company_id': company.id,
                'description': f'Inter-warehouse: {source_wh.name} → {dest_wh.name}',
            })
            
            _logger.info(f"Created 2 valuation layers for {move.name}: {move.product_qty} @ {unit_cost}")
    

    def _update_created_layers_warehouse(self):
        """
        Update valuation layers created by moves with proper warehouse_id.
        
        For inter-warehouse transfers:
        - Negative layers (outgoing) should have source warehouse
        - Positive layers (incoming) should have destination warehouse
        For intra-warehouse moves: layers exist but stay in same warehouse
        """
        valuation_layer_model = self.env['stock.valuation.layer']
        
        for move in self:
            # Skip if not a valued move
            if not move.product_id.valuation == 'real_time':
                continue
                
            source_wh = move.location_id.warehouse_id if move.location_id else None
            dest_wh = move.location_dest_id.warehouse_id if move.location_dest_id else None
            
            # Find layers created by this move
            layers = valuation_layer_model.search([
                ('stock_move_id', '=', move.id),
            ])
            
            for layer in layers:
                # Determine correct warehouse based on layer quantity
                if layer.quantity < 0:
                    # Negative layer (outgoing) - use source warehouse
                    if source_wh and (not layer.warehouse_id or layer.warehouse_id.id != source_wh.id):
                        layer.warehouse_id = source_wh.id
                elif layer.quantity > 0:
                    # Positive layer (incoming) - use destination warehouse
                    if dest_wh and (not layer.warehouse_id or layer.warehouse_id.id != dest_wh.id):
                        layer.warehouse_id = dest_wh.id
    
    def _allocate_landed_cost_for_inter_warehouse(self):
        """
        Allocate landed costs for inter-warehouse transfers only.
        Skip intra-warehouse moves.
        """
        for move in self:
            source_wh = move.location_id.warehouse_id if move.location_id else None
            dest_wh = move.location_dest_id.warehouse_id if move.location_dest_id else None
            
            # Only process inter-warehouse transfers
            if not (source_wh and dest_wh and source_wh.id != dest_wh.id):
                continue
            
            # Find layers for this move
            layers = self.env['stock.valuation.layer'].search([
                ('stock_move_id', '=', move.id),
            ])
            
            if layers:
                self._allocate_landed_cost_on_transfer(move, layers)
    
    def _allocate_landed_cost_on_transfer(self, move, layers):
        """
        Allocate landed costs proportionally during inter-warehouse transfers.
        
        When transferring inventory between warehouses, the landed cost portion
        of the inventory value should be transferred proportionally to the
        receiving warehouse.
        
        Args:
            move: stock.move record (the transfer)
            layers: stock.valuation.layer records created for this move
        """
        source_wh = move.location_id.warehouse_id if move.location_id else None
        dest_wh = move.location_dest_id.warehouse_id if move.location_dest_id else None
        product = move.product_id
        company = move.company_id
        qty_transferred = move.product_qty
        
        if not (source_wh and dest_wh):
            return
        
        # Skip if same warehouse (intra-warehouse move)
        if source_wh.id == dest_wh.id:
            return
        
        # Get landed costs at source warehouse for this product
        source_lc_value = self.env['stock.valuation.layer'].get_landed_cost_at_warehouse(
            product, source_wh, company.id
        )
        
        if source_lc_value == 0:
            # No landed costs to transfer
            return
        
        # Get total quantity available at source warehouse
        source_qty = self.env['stock.valuation.layer']._get_total_available_qty(
            product, source_wh, company.id
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
            if layer.quantity < 0 and layer.warehouse_id and layer.warehouse_id.id == source_wh.id:
                negative_layer = layer
            elif layer.quantity > 0 and layer.warehouse_id and layer.warehouse_id.id == dest_wh.id:
                positive_layer = layer
        
        if not (negative_layer and positive_layer):
            return
        
        # Create landed cost allocation records
        # For source: negative landed cost (reducing source warehouse's landed cost)
        # For destination: positive landed cost (adding to destination warehouse's landed cost)
        
        # We need to allocate from existing layers to the new warehouses
        self._transfer_landed_cost_between_warehouses(
            product, source_wh, dest_wh, company,
            qty_transferred, lc_to_transfer, negative_layer, positive_layer
        )
        
        # Record the allocation in history
        self.env['stock.landed.cost.allocation'].create({
            'move_id': move.id,
            'quantity_transferred': qty_transferred,
            'source_layer_landed_cost_before': source_lc_value,
            'source_layer_landed_cost_after': source_lc_value - lc_to_transfer,
            'destination_layer_landed_cost_before': self.env['stock.valuation.layer'].get_landed_cost_at_warehouse(
                product, dest_wh, company.id
            ),
            'destination_layer_landed_cost_after': self.env['stock.valuation.layer'].get_landed_cost_at_warehouse(
                product, dest_wh, company.id
            ) + lc_to_transfer,
            'landed_cost_transferred': lc_to_transfer,
            'notes': f'Automatic landed cost allocation during inter-warehouse transfer: {qty_transferred} units of {product.name}',
        })
    
    def _transfer_landed_cost_between_warehouses(self, product, source_wh, dest_wh,
                                                company, qty_transferred, lc_amount,
                                                source_layer, dest_layer):
        """
        Transfer landed cost from source warehouse to destination warehouse.
        
        This method:
        1. Reduces landed cost from source warehouse valuation layers
        2. Adds landed cost to destination warehouse valuation layers
        3. Creates tracking records in stock.valuation.layer.landed.cost
        
        Args:
            product: stock.product.product
            source_wh: source stock.warehouse
            dest_wh: destination stock.warehouse
            company: res.company
            qty_transferred: quantity being transferred
            lc_amount: landed cost amount to transfer
            source_layer: negative stock.valuation.layer at source
            dest_layer: positive stock.valuation.layer at destination
        """
        lc_model = self.env['stock.valuation.layer.landed.cost']
        precision = self.env['decimal.precision'].precision_get('Product Price')
        
        # Get all landed cost records for the product at source warehouse
        source_lc_records = lc_model.search([
            ('product_id', '=', product.id),
            ('warehouse_id', '=', source_wh.id),
            ('company_id', '=', company.id),
        ], order='create_date asc')
        
        if not source_lc_records:
            # No landed costs to transfer - create a new one at destination
            lc_model.create({
                'valuation_layer_id': dest_layer.id,
                'warehouse_id': dest_wh.id,
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
            
            # Update source warehouse record (reduce by amount transferred)
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
        
        # Add landed cost to destination warehouse
        # Create or update destination landed cost record
        existing_dest_lc = lc_model.search([
            ('valuation_layer_id', '=', dest_layer.id),
            ('warehouse_id', '=', dest_wh.id),
        ], limit=1)
        
        if existing_dest_lc:
            existing_dest_lc.landed_cost_value = float_round(
                existing_dest_lc.landed_cost_value + lc_amount,
                precision_digits=precision
            )
        else:
            lc_model.create({
                'valuation_layer_id': dest_layer.id,
                'warehouse_id': dest_wh.id,
                'landed_cost_value': lc_amount,
                'quantity': dest_layer.quantity,
            })

    def _create_account_move_line(self, debit_line_vals, credit_line_vals, writeoff_line_vals=None):
        """
        Override to ensure valuation layers get warehouse_id during accounting posting.
        
        For inter-warehouse transfers, we may need to ensure layers are created if not already.
        """
        # Call parent to create accounting entries
        result = super()._create_account_move_line(
            debit_line_vals, credit_line_vals, writeoff_line_vals
        )
        
        # For inter-warehouse transfers, ensure warehouse_id is set on created layers
        for move in self:
            source_wh = move.location_id.warehouse_id if move.location_id else None
            dest_wh = move.location_dest_id.warehouse_id if move.location_dest_id else None
            
            if source_wh and dest_wh and source_wh.id != dest_wh.id:
                # This is an inter-warehouse transfer
                ctx = move._get_valuation_layers_context()
                warehouse_id = ctx.get('fifo_warehouse_id') if ctx else None
                
                if warehouse_id:
                    layers = self.env['stock.valuation.layer'].search([
                        ('stock_move_id', '=', move.id),
                    ])
                    if layers:
                        layers.write({'warehouse_id': warehouse_id})
        
        return result
