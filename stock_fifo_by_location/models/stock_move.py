# -*- coding: utf-8 -*-
"""
Stock Move Model Extension

This module extends stock.move to ensure warehouse_id is properly propagated
to valuation layers during inventory moves.
"""

from odoo import models, fields, api
from odoo.tools import float_round, float_compare
import logging

_logger = logging.getLogger(__name__)


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
        - RETURN MOVES (Cross-Warehouse): Use DESTINATION warehouse (where stock returns to)
          * Cost comes from original warehouse's FIFO layers
          * Layer created at destination warehouse for future FIFO consumption
          * This allows safe cross-warehouse returns
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
        
        # ✅ NEW: Cross-warehouse returns - use DESTINATION warehouse
        # Cost will be taken from original warehouse's FIFO, but layer created at destination
        if self.origin_returned_move_id:
            # For return moves, ALWAYS use destination warehouse (where stock is returning to)
            # This allows flexible cross-warehouse returns while maintaining cost accuracy
            if self.location_dest_id and self.location_dest_id.usage == 'internal':
                dest_warehouse = self.location_dest_id.warehouse_id
                if dest_warehouse:
                    return dest_warehouse
            
            # Fallback: try transit location for returns in transit
            if self.location_dest_id and self.location_dest_id.usage == 'transit':
                dest_warehouse = self.location_dest_id.warehouse_id
                if dest_warehouse:
                    return dest_warehouse
        
        source_usage = self.location_id.usage
        dest_usage = self.location_dest_id.usage
        source_wh = self.location_id.warehouse_id
        dest_wh = self.location_dest_id.warehouse_id
        
        # Supplier/Production → Internal/Transit (INCOMING NEW STOCK)
        if source_usage in ('supplier', 'production', 'inventory'):
            return dest_wh
        
        # Customer → Internal (RETURN) - use destination for non-origin returns
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
    
    def _create_out_svl(self, forced_quantity=None):
        """
        🔴 CRITICAL OVERRIDE: Set warehouse_id in context BEFORE creating negative layer.
        
        This ensures that when _run_fifo() is called during layer creation,
        the layer already has warehouse_id set, preventing cross-warehouse FIFO consumption.
        
        Problem: Standard Odoo creates layer first, then _run_fifo() runs, THEN we set warehouse_id.
        Solution: Pass warehouse_id in context so it's set BEFORE _run_fifo() runs.
        """
        import logging
        _logger = logging.getLogger(__name__)
        
        svl_vals_list = []
        for move in self:
            warehouse = move._get_fifo_valuation_layer_warehouse()
            source_wh = move.location_id.warehouse_id if move.location_id else None
            dest_wh = move.location_dest_id.warehouse_id if move.location_dest_id else None
            is_internal_transfer = bool(
                source_wh and dest_wh
                and source_wh.id != dest_wh.id
                and move.location_id.usage in ('internal', 'transit')
                and move.location_dest_id.usage in ('internal', 'transit')
                and not move.origin_returned_move_id
            )
            
            _logger.info(
                f"🏭 _create_out_svl for move {move.name}: "
                f"from {move.location_id.complete_name} → {move.location_dest_id.complete_name}, "
                f"warehouse={warehouse.name if warehouse else 'None'}"
            )
            
            if warehouse:
                # Set warehouse_id in context so layer gets it during creation
                move = move.with_context(fifo_warehouse_id=warehouse.id)
            
            if is_internal_transfer:
                # Transfer ≠ Consumption: create out SVL with origin layer link
                # _run_fifo will reduce remaining_qty but NOT origin_remaining_qty
                fifo_result = self.env['fifo.service'].calculate_fifo_cost_with_landed_cost(
                    move.product_id, source_wh, forced_quantity or move.product_qty, move.company_id.id
                )
                move_vals = []
                for layer_info in fifo_result.get('layers', []):
                    source_layer = self.env['stock.valuation.layer'].browse(layer_info['layer_id'])
                    origin_layer = source_layer.origin_valuation_layer_id or source_layer
                    qty_consumed = layer_info['qty_consumed']
                    layer_cost = layer_info['cost']
                    unit_cost = layer_cost / qty_consumed if qty_consumed else 0.0
                    move_vals.append({
                        'stock_move_id': move.id,
                        'product_id': move.product_id.id,
                        'company_id': move.company_id.id,
                        'description': f'Transfer OUT: {source_wh.name} → {dest_wh.name}',
                        'quantity': -qty_consumed,
                        'unit_cost': unit_cost,
                        'value': -layer_cost,
                        'remaining_qty': 0.0,
                        'remaining_value': 0.0,
                        'warehouse_id': source_wh.id,
                        'origin_valuation_layer_id': origin_layer.id,
                        'source_warehouse_id': source_wh.id,
                        'transfer_move_id': move.id,
                    })
                if not move_vals:
                    move_vals = move._get_out_svl_vals(forced_quantity)
            else:
                # Get standard vals
                move_vals = move._get_out_svl_vals(forced_quantity)
            
            # Add warehouse_id to each val dict
            if warehouse:
                for vals in move_vals:
                    vals['warehouse_id'] = warehouse.id
                    _logger.info(
                        f"  ✅ Added warehouse_id={warehouse.id} ({warehouse.name}) to SVL vals: "
                        f"qty={vals.get('quantity', 0):.2f}"
                    )
            else:
                _logger.warning(
                    f"  ⚠️ No warehouse found for move {move.name}, layer will have no warehouse_id!"
                )
            
            svl_vals_list.extend(move_vals)
        
        # Create layers with warehouse_id already set
        _logger.info(f"🔨 Creating {len(svl_vals_list)} valuation layers")
        return self.env['stock.valuation.layer'].sudo().create(svl_vals_list)
    
    def _create_in_svl(self, forced_quantity=None):
        """
        Override to use custom cost for inventory adjustment increases.
        
        When inventory is increased via adjustment, we use the cost rule
        selected by the user instead of standard FIFO logic.
        """
        svl_vals_list = []
        non_adjustment_moves = self.env['stock.move']
        
        # Check if this is an inventory adjustment with custom cost rules
        cost_rules = self.env.context.get('inventory_cost_rules', {})
        
        for move in self:
            # Check if this move is from inventory adjustment
            is_inventory_adjustment = (
                move.location_id.usage == 'inventory' and
                move.location_dest_id.usage == 'internal'
            )
            
            if is_inventory_adjustment and move.product_id.cost_method == 'fifo':
                # Get warehouse for this adjustment
                warehouse = move.location_dest_id.warehouse_id
                
                # Try to get cost from quant's cost rule
                quant = self.env['stock.quant'].search([
                    ('product_id', '=', move.product_id.id),
                    ('location_id', '=', move.location_dest_id.id),
                ], limit=1)
                
                if quant and (quant.inventory_cost_rule or quant.id in cost_rules):
                    # Calculate cost based on rule
                    unit_cost = quant._get_inventory_cost_for_increase(warehouse=warehouse)
                    
                    # Get standard SVL values
                    move_vals = move._get_in_svl_vals(forced_quantity=forced_quantity)
                    
                    # Override unit_cost with calculated cost
                    for vals in move_vals:
                        vals['unit_cost'] = unit_cost
                        vals['value'] = vals['quantity'] * unit_cost
                        
                        # Set warehouse_id
                        if warehouse:
                            vals['warehouse_id'] = warehouse.id
                        
                        _logger.info(
                            f"Inventory adjustment IN: {move.product_id.name} "
                            f"at {warehouse.name if warehouse else 'Unknown'}: "
                            f"{vals['quantity']} units @ {unit_cost}/unit = {vals['value']}"
                        )
                    
                    svl_vals_list.extend(move_vals)
                    continue
            
            # Track moves that don't match for standard processing
            non_adjustment_moves |= move
        
        # Process non-adjustment moves with standard logic
        if non_adjustment_moves:
            standard_svls = super(StockMove, non_adjustment_moves)._create_in_svl(
                forced_quantity=forced_quantity
            )
            if svl_vals_list:
                # Combine custom SVLs with standard ones
                custom_svls = self.env['stock.valuation.layer'].sudo().create(svl_vals_list)
                return custom_svls | standard_svls
            return standard_svls
        
        # All moves were inventory adjustments with custom cost
        if svl_vals_list:
            return self.env['stock.valuation.layer'].sudo().create(svl_vals_list)
        
        # Fallback: no moves matched at all
        return super()._create_in_svl(forced_quantity=forced_quantity)
    

    def _action_done(self, cancel_backorder=False):
        """
        Override move completion to ensure warehouse context is passed to layer operations.
        
        Core principle: Let Odoo create layers first, then enhance with warehouse_id.
        For inter-warehouse transfers, if Odoo doesn't create layers, we create them.
        
        ✅ Cross-warehouse returns are now ALLOWED:
        - Cost comes from original warehouse's FIFO layers
        - Layer created at destination warehouse (where stock returns)
        - Safe and deterministic cost flow
        """
        # Call parent implementation first - this creates the standard layers
        result = super()._action_done(cancel_backorder=cancel_backorder)
        
        # Check and create layers for inter-warehouse transfers if needed
        self._ensure_inter_warehouse_valuation_layers()
        
        # After standard layer creation, update them with correct warehouse_id
        self._update_created_layers_warehouse()
        
        # Transfer ≠ Consumption: reduce origin_remaining_qty on external out only
        self._reduce_origin_on_external_out()
        
        # Handle landed cost allocation for inter-warehouse transfers
        self._allocate_landed_cost_for_inter_warehouse()
        
        return result
    
    def _ensure_inter_warehouse_valuation_layers(self):
        """
        Transfer ≠ Consumption: Create position layers for internal transfers.
        
        For internal transfers (WH-A → WH-B):
        - Odoo standard already creates negative+positive SVLs and runs _run_fifo()
        - _run_fifo() already consumed remaining_qty at source (Odoo valuation)
        - _run_fifo() did NOT consume origin_remaining_qty (Transfer ≠ Consumption)
        - We just need to ensure the positive layer at dest has origin_valuation_layer_id
        
        For return moves (WH-B → WH-A):
        - Same principle: Odoo creates layers, _run_fifo runs
        - We ensure position layer links back to cost origin
        """
        import logging
        _logger = logging.getLogger(__name__)
        
        valuation_layer_model = self.env['stock.valuation.layer']
        
        for move in self:
            if move.state != 'done':
                continue
            
            product = move.product_id
            if product.type != 'product':
                continue
            if product.categ_id.property_cost_method != 'fifo':
                continue
            
            source_wh = move.location_id.warehouse_id if move.location_id else None
            dest_wh = move.location_dest_id.warehouse_id if move.location_dest_id else None
            
            if not (source_wh and dest_wh and source_wh.id != dest_wh.id):
                continue
            
            if move.location_id.usage not in ('internal', 'transit') or \
               move.location_dest_id.usage not in ('internal', 'transit'):
                continue
            
            is_return_move = bool(move.origin_returned_move_id)
            move_type = "RETURN" if is_return_move else "TRANSFER"
            
            existing_layers = valuation_layer_model.search([
                ('stock_move_id', '=', move.id),
            ])
            
            _logger.info(
                f"📦 Inter-warehouse {move_type} {move.name}: "
                f"{source_wh.name} → {dest_wh.name}, "
                f"Product: {product.name}, Qty: {move.product_qty}, "
                f"Existing layers: {len(existing_layers)}"
            )
            
            company = move.company_id
            
            # ── Determine unit cost from source FIFO or original move ──
            unit_cost = 0.0
            origin_layer = None
            
            if is_return_move and move.origin_returned_move_id:
                original_move = move.origin_returned_move_id
                original_neg_layers = valuation_layer_model.search([
                    ('stock_move_id', '=', original_move.id),
                    ('quantity', '<', 0),
                ], limit=1)
                if original_neg_layers:
                    unit_cost = abs(original_neg_layers[0].unit_cost)
                    origin_layer = original_neg_layers[0].origin_valuation_layer_id or original_neg_layers[0]
                
                if unit_cost <= 0:
                    original_pos_layers = valuation_layer_model.search([
                        ('stock_move_id', '=', original_move.id),
                        ('quantity', '>', 0),
                    ], limit=1)
                    if original_pos_layers:
                        unit_cost = abs(original_pos_layers[0].unit_cost)
                        origin_layer = original_pos_layers[0].origin_valuation_layer_id or original_pos_layers[0]
            
            if unit_cost <= 0:
                fifo_service = self.env['fifo.service']
                fifo_result = fifo_service.calculate_fifo_cost_with_landed_cost(
                    product, source_wh, move.product_qty, company.id
                )
                if isinstance(fifo_result, dict):
                    unit_cost = fifo_result.get('unit_cost', 0.0)
                else:
                    unit_cost = float(fifo_result) if fifo_result else 0.0
            
            if unit_cost <= 0:
                unit_cost = product.standard_price or 0.0
            
            total_cost = unit_cost * move.product_qty
            
            # ── Handle NEGATIVE layer at source warehouse ──
            negative_layers = existing_layers.filtered(lambda l: l.quantity < 0)
            has_negative_source = any(
                l.warehouse_id and l.warehouse_id.id == source_wh.id
                for l in negative_layers
            )
            
            if not has_negative_source:
                neg_layer = valuation_layer_model.sudo().create({
                    'stock_move_id': move.id,
                    'product_id': product.id,
                    'warehouse_id': source_wh.id,
                    'quantity': -move.product_qty,
                    'unit_cost': unit_cost,
                    'value': -total_cost,
                    'remaining_qty': 0.0,
                    'remaining_value': 0.0,
                    'company_id': company.id,
                    'description': f'{move_type} OUT: {source_wh.name} → {dest_wh.name}',
                })
                # _run_fifo will consume remaining_qty but NOT origin_remaining_qty
                neg_layer._run_fifo(-move.product_qty, company)
                negative_layers = neg_layer
                _logger.info(f"✅ Created negative layer at {source_wh.name}")
            else:
                for neg_layer in negative_layers:
                    if neg_layer.warehouse_id and neg_layer.warehouse_id.id != source_wh.id:
                        neg_layer.warehouse_id = source_wh.id
            
            # ── Resolve origin cost layer from the consumed candidates ──
            if not origin_layer:
                # Find which layer was consumed at source — get its origin
                if negative_layers:
                    if is_return_move:
                        # For returns: the consumed layers at source are position layers
                        # Their origin_valuation_layer_id points to the cost origin
                        pass
                    # Get the most recent consumed layer at source warehouse
                    consumed_at_source = valuation_layer_model.search([
                        ('product_id', '=', product.id),
                        ('warehouse_id', '=', source_wh.id),
                        ('quantity', '>', 0),
                        ('remaining_qty', '<', 1e-6),  # fully consumed or near-zero
                    ], order='write_date desc', limit=1)
                    if consumed_at_source and consumed_at_source.origin_valuation_layer_id:
                        origin_layer = consumed_at_source.origin_valuation_layer_id
                    elif consumed_at_source:
                        origin_layer = consumed_at_source
            
            # ── Handle POSITIVE layer at destination warehouse ──
            positive_layers = existing_layers.filtered(lambda l: l.quantity > 0)
            has_positive_dest = any(
                l.warehouse_id and l.warehouse_id.id == dest_wh.id
                for l in positive_layers
            )
            
            if not has_positive_dest:
                # Create position layer at dest linked to cost origin
                pos_vals = {
                    'stock_move_id': move.id,
                    'product_id': product.id,
                    'warehouse_id': dest_wh.id,
                    'quantity': move.product_qty,
                    'unit_cost': unit_cost,
                    'value': total_cost,
                    'remaining_qty': move.product_qty,
                    'remaining_value': total_cost,
                    'company_id': company.id,
                    'description': f'{move_type} IN: {source_wh.name} → {dest_wh.name}',
                    'source_warehouse_id': source_wh.id,
                    'transfer_move_id': move.id,
                    'is_position_layer': True,
                }
                if origin_layer:
                    pos_vals['origin_valuation_layer_id'] = origin_layer.id
                
                valuation_layer_model.sudo().create(pos_vals)
                _logger.info(
                    f"✅ Created POSITION layer at {dest_wh.name} "
                    f"(origin: {origin_layer.id if origin_layer else 'N/A'})"
                )
            else:
                # Ensure existing positive layer has correct warehouse and origin link
                for pos_layer in positive_layers:
                    if pos_layer.warehouse_id and pos_layer.warehouse_id.id != dest_wh.id:
                        pos_layer.warehouse_id = dest_wh.id
                    if origin_layer and not pos_layer.origin_valuation_layer_id:
                        pos_layer.origin_valuation_layer_id = origin_layer.id
                        pos_layer.is_position_layer = True
                        pos_layer.source_warehouse_id = source_wh.id
                        pos_layer.transfer_move_id = move.id
            
            _logger.info(
                f"🎉 Inter-warehouse {move_type} complete: "
                f"{move.product_qty} x {product.name} @ {unit_cost:.4f}/unit "
                f"from {source_wh.name} to {dest_wh.name}"
            )
    

    def _update_created_layers_warehouse(self):
        """
        Update valuation layers created by moves with proper warehouse_id.
        
        For inter-warehouse transfers:
        - Negative layers (outgoing) should have source warehouse
        - Positive layers (incoming) should have destination warehouse
        For intra-warehouse moves: layers exist but stay in same warehouse
        
        For RETURN MOVES:
        - CRITICAL: Use average unit cost from FIFO consumption (includes landed costs!)
        - NOT base cost only
        - This ensures balance = 0 when return full quantity
        """
        import logging
        _logger = logging.getLogger(__name__)
        
        valuation_layer_model = self.env['stock.valuation.layer']
        fifo_service = self.env['fifo.service']
        precision = self.env['decimal.precision'].precision_get('Product Price')
        
        for move in self:
            # Skip if not a product (only process storable products)
            if move.product_id.type != 'product':
                continue
                
            source_wh = move.location_id.warehouse_id if move.location_id else None
            dest_wh = move.location_dest_id.warehouse_id if move.location_dest_id else None
            
            # Find layers created by this move
            layers = valuation_layer_model.search([
                ('stock_move_id', '=', move.id),
            ])
            
            # For return moves, calculate unit cost from original delivery layer WITH landed costs
            # ✅ NEW: Support cross-warehouse returns - cost from original WH, layer at destination WH
            return_unit_cost = None
            return_total_cost = None
            original_wh = None  # Store original warehouse for cost calculation
            
            if move.origin_returned_move_id:
                original_move = move.origin_returned_move_id
                
                # Get original warehouse from original move's location (where it was sold/consumed from)
                if original_move.location_id and original_move.location_id.usage == 'internal':
                    original_wh = original_move.location_id.warehouse_id
                elif original_move.location_dest_id and original_move.location_dest_id.usage == 'internal':
                    original_wh = original_move.location_dest_id.warehouse_id
                
                # CRITICAL FIX v17.0.1.2.7: Get unit cost from the ACTUAL original layer
                # Supports BOTH:
                #   1. Sales returns (original = delivery → has NEGATIVE layer)
                #   2. Vendor returns (original = receipt → has POSITIVE layer only)
                # Also handles import ordering where return is processed before receipt
                if original_wh:
                    try:
                        # Step 1: Find the NEGATIVE delivery layer from original move
                        # This works for SALES RETURNS where original was a delivery/sale
                        original_delivery_layers = valuation_layer_model.search([
                            ('stock_move_id', '=', original_move.id),
                            ('quantity', '<', 0),  # NEGATIVE layer (outgoing/consumption)
                            ('warehouse_id', '=', original_wh.id),
                        ], limit=1)
                        
                        if original_delivery_layers:
                            # The delivery layer's unit_cost is the FIFO cost at consumption time
                            base_delivery_unit_cost = abs(original_delivery_layers[0].unit_cost)
                            
                            # Get any additional landed costs
                            lc_model = self.env['stock.valuation.layer.landed.cost']
                            delivery_lc_records = lc_model.search([
                                ('valuation_layer_id', '=', original_delivery_layers[0].id),
                                ('warehouse_id', '=', original_wh.id),
                            ])
                            
                            unit_lc = 0.0
                            if delivery_lc_records:
                                lc_value = sum(delivery_lc_records.mapped('landed_cost_value'))
                                lc_qty = delivery_lc_records[0].quantity or 1
                                unit_lc = lc_value / lc_qty if lc_qty > 0 else 0.0
                            
                            return_unit_cost = base_delivery_unit_cost + unit_lc
                            return_total_cost = return_unit_cost * move.product_qty
                            
                            _logger.info(
                                f"Return move {move.name}: "
                                f"Using NEGATIVE delivery layer unit cost: {base_delivery_unit_cost}/unit + "
                                f"LC: {unit_lc}/unit = {return_unit_cost}/unit total"
                            )
                        else:
                            # 🔴 FIX v17.0.1.2.7: Step 2 - Try POSITIVE receipt layer
                            # For VENDOR RETURNS: original move is a receipt (Vendor → Stock)
                            # which only has a POSITIVE layer, not negative
                            original_receipt_layers = valuation_layer_model.search([
                                ('stock_move_id', '=', original_move.id),
                                ('quantity', '>', 0),  # POSITIVE layer (receipt/incoming)
                            ], limit=1)
                            
                            if original_receipt_layers:
                                base_receipt_unit_cost = abs(original_receipt_layers[0].unit_cost)
                                
                                # Get any landed costs on the receipt layer
                                lc_model = self.env['stock.valuation.layer.landed.cost']
                                receipt_lc_records = lc_model.search([
                                    ('valuation_layer_id', '=', original_receipt_layers[0].id),
                                ])
                                
                                unit_lc = 0.0
                                if receipt_lc_records:
                                    lc_value = sum(receipt_lc_records.mapped('landed_cost_value'))
                                    lc_qty = abs(original_receipt_layers[0].quantity) or 1
                                    unit_lc = lc_value / lc_qty if lc_qty > 0 else 0.0
                                
                                return_unit_cost = base_receipt_unit_cost + unit_lc
                                return_total_cost = return_unit_cost * move.product_qty
                                
                                _logger.info(
                                    f"Return move {move.name}: "
                                    f"Using POSITIVE receipt layer unit cost: {base_receipt_unit_cost}/unit + "
                                    f"LC: {unit_lc}/unit = {return_unit_cost}/unit total "
                                    f"(original move was a receipt, not a delivery)"
                                )
                            else:
                                # Step 3: Try FIFO calculation
                                _logger.warning(
                                    f"Return move {move.name}: "
                                    f"No original layer found (neither negative nor positive), "
                                    f"trying FIFO calculation"
                                )
                                
                                fifo_result = fifo_service.calculate_fifo_cost_with_landed_cost(
                                    move.product_id,
                                    original_wh,
                                    move.product_qty,
                                    move.company_id.id
                                )
                                
                                if isinstance(fifo_result, dict) and fifo_result.get('cost', 0) > 0 and fifo_result.get('qty', 0) > 0:
                                    return_unit_cost = fifo_result['unit_cost']
                                    return_total_cost = fifo_result['cost']
                                    _logger.info(
                                        f"Return move {move.name}: "
                                        f"Using FIFO calculation: {return_unit_cost}/unit"
                                    )
                                else:
                                    # 🔴 FIX v17.0.1.2.7: Step 4 - Final fallback
                                    # Use original move's price_unit (from PO/SO)
                                    # This handles import ordering where return is processed
                                    # before receipt SVL exists
                                    original_price = abs(original_move.price_unit) if original_move.price_unit else 0.0
                                    if original_price > 0:
                                        return_unit_cost = original_price
                                        return_total_cost = return_unit_cost * move.product_qty
                                        _logger.info(
                                            f"Return move {move.name}: "
                                            f"Using original move price_unit fallback: {return_unit_cost}/unit"
                                        )
                                    else:
                                        _logger.warning(
                                            f"Return move {move.name}: "
                                            f"Could not determine return cost from any source. "
                                            f"Layer will keep its current unit_cost."
                                        )
                    except Exception as e:
                        _logger.warning(
                            f"Failed to calculate return unit cost for move {move.name}: {e}"
                        )
            
            for layer in layers:
                # Determine correct warehouse based on layer quantity and move type
                is_return = bool(move.origin_returned_move_id)
                
                # Detect internal transfer for position layer linking
                is_inter_wh = bool(
                    source_wh and dest_wh and source_wh.id != dest_wh.id
                    and move.location_id.usage in ('internal', 'transit')
                    and move.location_dest_id.usage in ('internal', 'transit')
                )
                
                if layer.quantity < 0:
                    # Negative layer (outgoing/consumption)
                    if is_return:
                        if source_wh and (not layer.warehouse_id or layer.warehouse_id.id != source_wh.id):
                            layer.warehouse_id = source_wh.id
                            _logger.info(
                                f"Return move: Set negative layer {layer.id} "
                                f"to source warehouse {source_wh.name}"
                            )
                    else:
                        if source_wh and (not layer.warehouse_id or layer.warehouse_id.id != source_wh.id):
                            layer.warehouse_id = source_wh.id
                    
                    # Fix unit_cost for return moves
                    if return_unit_cost is not None and return_unit_cost > 0:
                        layer.unit_cost = return_unit_cost
                        layer.value = layer.quantity * return_unit_cost
                        
                elif layer.quantity > 0:
                    # Positive layer (incoming) - ALWAYS use destination warehouse
                    if dest_wh and (not layer.warehouse_id or layer.warehouse_id.id != dest_wh.id):
                        layer.warehouse_id = dest_wh.id
                    
                    # Transfer ≠ Consumption: link position layers to cost origin
                    if is_inter_wh and not is_return:
                        if not layer.origin_valuation_layer_id:
                            # Find the origin layer from the negative layer of this move
                            neg_layers = layers.filtered(lambda l: l.quantity < 0 and l.origin_valuation_layer_id)
                            if neg_layers:
                                layer.origin_valuation_layer_id = neg_layers[0].origin_valuation_layer_id.id
                            else:
                                # Find origin from consumed source layers at source warehouse
                                consumed_at_source = valuation_layer_model.search([
                                    ('product_id', '=', move.product_id.id),
                                    ('warehouse_id', '=', source_wh.id),
                                    ('quantity', '>', 0),
                                ], order='write_date desc', limit=1)
                                if consumed_at_source:
                                    origin = consumed_at_source.origin_valuation_layer_id or consumed_at_source
                                    layer.origin_valuation_layer_id = origin.id
                            layer.is_position_layer = True
                            layer.source_warehouse_id = source_wh.id
                            layer.transfer_move_id = move.id
                            _logger.info(
                                f"Position layer {layer.id} linked to origin {layer.origin_valuation_layer_id.id}"
                            )
                    
                    # Fix unit_cost for return moves
                    if return_unit_cost is not None and return_unit_cost > 0:
                        layer.unit_cost = return_unit_cost
                        layer.value = layer.quantity * return_unit_cost
                    
                    # Copy landed cost allocations for returns
                    if is_return:
                        self._copy_landed_cost_to_return(
                            move.origin_returned_move_id, move, layer
                        )
    
    def _reduce_origin_on_external_out(self):
        """
        Transfer ≠ Consumption: reduce origin_remaining_qty on external out only.
        
        Odoo core's _run_fifo() only reduces remaining_qty/remaining_value.
        It doesn't know about origin_remaining_qty/origin_remaining_value.
        This method traces each consumed candidate back to its cost origin
        and reduces origin_remaining_qty by the external out quantity.
        
        Skips: internal transfers (handled in SVL._run_fifo), returns.
        """
        import logging
        _logger = logging.getLogger(__name__)
        
        svl_model = self.env['stock.valuation.layer']
        
        for move in self:
            if move.product_id.type != 'product':
                continue
            if move.product_id.categ_id.property_cost_method != 'fifo':
                continue
            
            source_wh = move.location_id.warehouse_id if move.location_id else None
            dest_wh = move.location_dest_id.warehouse_id if move.location_dest_id else None
            
            # Skip internal transfers — they are handled by SVL._run_fifo()
            is_internal_transfer = bool(
                source_wh and dest_wh and source_wh.id != dest_wh.id
                and move.location_id.usage in ('internal', 'transit')
                and move.location_dest_id.usage in ('internal', 'transit')
                and not move.origin_returned_move_id
            )
            # Also skip intra-warehouse moves (same warehouse)
            is_intra_wh = bool(
                source_wh and dest_wh and source_wh.id == dest_wh.id
                and move.location_id.usage in ('internal', 'transit')
                and move.location_dest_id.usage in ('internal', 'transit')
            )
            if is_internal_transfer or is_intra_wh:
                continue
            
            # Skip returns
            if move.origin_returned_move_id:
                continue
            
            # This is an external out (sale, scrap, production consume, etc.)
            # Find negative layers for this move
            neg_layers = svl_model.search([
                ('stock_move_id', '=', move.id),
                ('quantity', '<', 0),
            ])
            
            for neg_layer in neg_layers:
                qty_consumed = abs(neg_layer.quantity)
                warehouse = neg_layer.warehouse_id or source_wh
                if not warehouse:
                    continue
                
                # Find which layers were consumed by this sale at this warehouse
                # These are layers whose remaining_qty was reduced by _run_fifo()
                # We need to find candidates that still exist and trace to their origin
                candidates = svl_model.search([
                    ('product_id', '=', move.product_id.id),
                    ('warehouse_id', '=', warehouse.id),
                    ('quantity', '>', 0),
                    ('company_id', '=', move.company_id.id),
                ], order='create_date, id')
                
                # For each candidate, reduce its origin's origin_remaining_qty
                # proportional to how much was consumed
                # Since _run_fifo already reduced remaining_qty, we can infer
                # what was consumed by looking at candidates that had stock before
                # 
                # Simpler approach: reduce origin of ALL candidates that still have
                # stock at this warehouse, proportional to their remaining_qty
                # But that's not accurate...
                #
                # Best approach: use the same FIFO logic to determine what was consumed
                # and reduce those specific origins
                remaining_to_reduce = qty_consumed
                
                for candidate in candidates:
                    if remaining_to_reduce <= 0:
                        break
                    
                    taken = min(remaining_to_reduce, candidate.remaining_qty)
                    origin = candidate.origin_valuation_layer_id or candidate
                    
                    new_orem = origin.origin_remaining_qty - taken
                    if new_orem < 0:
                        new_orem = 0.0
                    
                    origin_unit_cost = (
                        origin.origin_remaining_value / origin.origin_remaining_qty
                        if origin.origin_remaining_qty > 0 else 0.0
                    )
                    new_orem_val = origin.origin_remaining_value - (taken * origin_unit_cost)
                    if new_orem_val < 0:
                        new_orem_val = 0.0
                    
                    origin.sudo().write({
                        'origin_remaining_qty': new_orem,
                        'origin_remaining_value': new_orem_val,
                    })
                    
                    # Also reduce origin_remaining_qty on the position layer itself
                    if candidate.origin_valuation_layer_id and candidate.id != origin.id:
                        pos_new_orem = candidate.origin_remaining_qty - taken
                        if pos_new_orem < 0:
                            pos_new_orem = 0.0
                        candidate.sudo().write({
                            'origin_remaining_qty': pos_new_orem,
                        })
                    
                    _logger.debug(
                        f"📉 External out: origin {origin.id} orem "
                        f"{origin.origin_remaining_qty + taken:.0f} → {new_orem:.0f}"
                    )
                    
                    remaining_to_reduce -= taken
    
    def _allocate_landed_cost_for_inter_warehouse(self):
        """
        Allocate landed costs for inter-warehouse transfers.
        Skip intra-warehouse moves and return moves.
        """
        for move in self:
            # Skip return moves - they handle landed costs via original_unit_cost
            if move.origin_returned_move_id:
                continue
            
            source_wh = move.location_id.warehouse_id if move.location_id else None
            dest_wh = move.location_dest_id.warehouse_id if move.location_dest_id else None
            
            # Only process inter-warehouse transfers (not returns)
            if not (source_wh and dest_wh and source_wh.id != dest_wh.id):
                continue
            
            # Skip if source is customer/supplier (this is a receipt/delivery, not transfer)
            if move.location_id.usage in ('customer', 'supplier'):
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
        
        precision = self.env['decimal.precision'].precision_get('Product Price')
        lc_model = self.env['stock.valuation.layer.landed.cost']

        positive_layers = layers.filtered(
            lambda l: l.quantity > 0 and l.warehouse_id and l.warehouse_id.id == dest_wh.id
        )
        total_transferred_lc = 0.0
        source_lc_before = self.env['stock.valuation.layer'].get_landed_cost_at_warehouse(
            product, source_wh, company.id
        )
        dest_lc_before = self.env['stock.valuation.layer'].get_landed_cost_at_warehouse(
            product, dest_wh, company.id
        )

        for positive_layer in positive_layers:
            origin_layer = positive_layer.origin_valuation_layer_id
            if not origin_layer:
                continue

            source_lc = lc_model.search([
                ('valuation_layer_id', '=', origin_layer.id),
                ('warehouse_id', '=', source_wh.id),
            ], limit=1)
            if not source_lc or source_lc.quantity <= 0:
                continue

            qty_for_layer = positive_layer.quantity
            lc_to_transfer = float_round(
                qty_for_layer * source_lc.unit_landed_cost,
                precision_digits=precision
            )
            if float_compare(lc_to_transfer, 0, precision_digits=precision) <= 0:
                continue

            source_lc.write({
                'landed_cost_value': float_round(
                    max(0.0, source_lc.landed_cost_value - lc_to_transfer),
                    precision_digits=precision
                ),
                'quantity': max(0.0, source_lc.quantity - qty_for_layer),
            })

            dest_lc = lc_model.search([
                ('valuation_layer_id', '=', positive_layer.id),
                ('warehouse_id', '=', dest_wh.id),
            ], limit=1)
            if dest_lc:
                dest_lc.write({
                    'landed_cost_value': float_round(
                        dest_lc.landed_cost_value + lc_to_transfer,
                        precision_digits=precision
                    ),
                    'quantity': dest_lc.quantity + qty_for_layer,
                })
            else:
                lc_model.create({
                    'valuation_layer_id': positive_layer.id,
                    'warehouse_id': dest_wh.id,
                    'landed_cost_value': lc_to_transfer,
                    'quantity': qty_for_layer,
                })
            total_transferred_lc += lc_to_transfer

        if float_compare(total_transferred_lc, 0, precision_digits=precision) <= 0:
            return

        self.env['stock.landed.cost.allocation'].create({
            'move_id': move.id,
            'quantity_transferred': qty_transferred,
            'source_layer_landed_cost_before': source_lc_before,
            'source_layer_landed_cost_after': source_lc_before - total_transferred_lc,
            'destination_layer_landed_cost_before': dest_lc_before,
            'destination_layer_landed_cost_after': dest_lc_before + total_transferred_lc,
            'landed_cost_transferred': total_transferred_lc,
            'notes': f'Automatic landed cost allocation during inter-warehouse transfer: {qty_transferred} units of {product.name}',
        })
    
    def _copy_landed_cost_to_return(self, original_move, return_move, return_layer):
        """
        Copy landed cost allocation from original move to return move.
        
        When a return move is created, we need to allocate the same landed costs
        that were in the original delivery/consumption so that the final balance = 0.
        
        This reverses the landed cost portion of the cost by creating records
        that effectively unwind the landed cost from the original transaction.
        
        Args:
            original_move: Original stock.move that was returned
            return_move: Return stock.move
            return_layer: The positive return layer
        """
        import logging
        _logger = logging.getLogger(__name__)
        
        lc_model = self.env['stock.valuation.layer.landed.cost']
        precision = self.env['decimal.precision'].precision_get('Product Price')
        
        # Get warehouse from original move
        original_wh = original_move.warehouse_id
        if not original_wh and original_move.location_id:
            original_wh = original_move.location_id.warehouse_id
        
        if not original_wh:
            _logger.warning(f"Return move {return_move.name}: Could not determine original warehouse")
            return
        
        # Find all landed cost allocations at the original warehouse
        # for the product we're returning
        all_lc_records = lc_model.search([
            ('valuation_layer_id.product_id', '=', return_move.product_id.id),
            ('warehouse_id', '=', original_wh.id),
            ('valuation_layer_id.company_id', '=', return_move.company_id.id),
        ])
        
        if not all_lc_records:
            _logger.info(f"Return move {return_move.name}: No landed costs to copy")
            return
        
        # Calculate total landed cost available at source warehouse
        total_lc_available = sum(all_lc_records.mapped('landed_cost_value'))
        
        # Calculate how much landed cost proportion to allocate to return
        # Based on quantity ratio
        try:
            fifo_service = self.env['fifo.service']
            total_qty_available = fifo_service.get_available_qty_at_warehouse(
                return_move.product_id, original_wh, return_move.company_id.id
            )
            
            if total_qty_available > 0:
                proportion = return_move.product_qty / total_qty_available
                lc_to_allocate = total_lc_available * proportion
                lc_to_allocate = float_round(lc_to_allocate, precision_digits=precision)
            else:
                lc_to_allocate = 0.0
        except Exception as e:
            _logger.warning(f"Failed to calculate landed cost proportion: {e}")
            lc_to_allocate = 0.0
        
        if float_compare(lc_to_allocate, 0, precision_digits=precision) > 0:
            # Create landed cost record for return layer
            lc_model.create({
                'valuation_layer_id': return_layer.id,
                'warehouse_id': original_wh.id,
                'landed_cost_value': lc_to_allocate,
                'quantity': return_layer.quantity,
            })
            
            _logger.info(
                f"Return move {return_move.name}: Allocated {lc_to_allocate} landed cost "
                f"to {return_layer.quantity} units at {original_wh.name}"
            )
    
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
            # No landed costs to transfer
            return
        
        # Calculate how much landed cost to take from each source layer (FIFO)
        remaining_lc = lc_amount
        
        for source_lc_record in source_lc_records:
            if float_compare(remaining_lc, 0, precision_digits=precision) <= 0:
                break
            
            # How much can we take from this record?
            lc_available = source_lc_record.landed_cost_value
            lc_to_take = min(remaining_lc, lc_available)
            
            # Validate that we're not taking more than available
            if float_compare(lc_to_take, lc_available, precision_digits=precision) > 0:
                lc_to_take = lc_available
            
            # Update source warehouse record (reduce by amount transferred)
            new_source_value = source_lc_record.landed_cost_value - lc_to_take
            # Ensure non-negative
            if float_compare(new_source_value, 0, precision_digits=precision) < 0:
                new_source_value = 0.0
            
            source_lc_record.write({
                'landed_cost_value': float_round(new_source_value, precision_digits=precision),
                'quantity': source_lc_record.quantity,  # Keep quantity consistent
            })
            
            remaining_lc = float_round(
                remaining_lc - lc_to_take, precision_digits=precision
            )
        
        # Add landed cost to destination warehouse
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
