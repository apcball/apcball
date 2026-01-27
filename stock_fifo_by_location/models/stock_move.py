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
            
            _logger.info(
                f"🏭 _create_out_svl for move {move.name}: "
                f"from {move.location_id.complete_name} → {move.location_dest_id.complete_name}, "
                f"warehouse={warehouse.name if warehouse else 'None'}"
            )
            
            if warehouse:
                # Set warehouse_id in context so layer gets it during creation
                move = move.with_context(fifo_warehouse_id=warehouse.id)
            
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
        
        # Handle landed cost allocation for inter-warehouse transfers
        self._allocate_landed_cost_for_inter_warehouse()
        
        return result
    
    def _ensure_inter_warehouse_valuation_layers(self):
        """
        🔴 CRITICAL: Ensure BOTH negative (source) AND positive (dest) valuation layers
        exist for inter-warehouse transfers AND their return moves.
        
        แนวคิดที่ถูกต้องเวลา Transfer ข้ามคลัง A → B:
        
        1. คลังต้นทาง (WH-A) - ทำเหมือน "เบิกออก":
           - หา FIFO layer ของ WH-A ตาม quantity ที่ย้าย
           - remaining_qty ลดลง (ผ่าน _run_fifo)
           - สร้าง SVL out:
             * quantity = -qty
             * value = -cost_total (from FIFO)
             * warehouse_id = WH-A
        
        2. คลังปลายทาง (WH-B) - ต้องมี "in layer ใหม่" เสมอ:
           - quantity = +qty
           - value = +cost_total เดิมจาก WH-A
           - unit_cost = cost_total / qty
           - warehouse_id = WH-B
           - layer นี้คือแหล่ง FIFO ของ WH-B สำหรับการขาย/เบิกครั้งต่อไป
        
        🔄 Return Move ข้ามคลัง (B → A):
        
        1. คลังต้นทาง B (ที่รับคืน) - ทำเหมือน "เบิกออก":
           - หา FIFO layer ของ WH-B ตาม quantity ที่คืน
           - remaining_qty ลดลง (ผ่าน _run_fifo)
           - สร้าง SVL out:
             * quantity = -qty
             * value = -cost_total (from original transfer)
             * warehouse_id = WH-B
        
        2. คลังปลายทาง A (ที่คืนกลับไป) - ต้องมี "in layer ใหม่" เสมอ:
           - quantity = +qty
           - value = +cost_total เดิมจาก original transfer
           - unit_cost = cost_total / qty
           - warehouse_id = WH-A
           - remaining_qty = qty (เพิ่ม FIFO queue กลับมา)
        
        ⚠️ ถ้าข้อ 2 ไม่ทำ:
        - ที่คลัง A จะมี stock ปริมาณ แต่ไม่มี valuation layer
        - remaining_qty = 0 ตลอด
        - พอขายจาก WH-A ระบบจะหา layer ไม่เจอ
        - ไปหยิบ global layer / หรือ warehouse อื่น / หรือคำนวณผิด
        """
        import logging
        _logger = logging.getLogger(__name__)
        
        valuation_layer_model = self.env['stock.valuation.layer']
        
        for move in self:
            # Only process done moves
            if move.state != 'done':
                continue
            
            product = move.product_id
            
            # Skip if product is not storable or not using FIFO valuation
            if product.type != 'product':
                continue
            
            # Check if product uses FIFO costing
            if product.categ_id.property_cost_method != 'fifo':
                _logger.debug(f"Skip {move.name}: Product {product.name} not using FIFO")
                continue
            
            source_wh = move.location_id.warehouse_id if move.location_id else None
            dest_wh = move.location_dest_id.warehouse_id if move.location_dest_id else None
            
            # Only for inter-warehouse transfers (different warehouses)
            if not (source_wh and dest_wh and source_wh.id != dest_wh.id):
                continue
            
            # Skip if source/dest is not internal location
            if move.location_id.usage not in ('internal', 'transit') or \
               move.location_dest_id.usage not in ('internal', 'transit'):
                _logger.debug(f"Skip {move.name}: Not internal transfer (usage: {move.location_id.usage} -> {move.location_dest_id.usage})")
                continue
            
            # 🆕 Check if this is a return move
            is_return_move = bool(move.origin_returned_move_id)
            
            # Check what layers already exist for this move
            existing_layers = valuation_layer_model.search([
                ('stock_move_id', '=', move.id),
            ])
            
            has_negative_source = any(
                l.quantity < 0 and l.warehouse_id and l.warehouse_id.id == source_wh.id 
                for l in existing_layers
            )
            has_positive_dest = any(
                l.quantity > 0 and l.warehouse_id and l.warehouse_id.id == dest_wh.id 
                for l in existing_layers
            )
            
            move_type = "RETURN" if is_return_move else "TRANSFER"
            _logger.debug(
                f"📦 Inter-warehouse {move_type} {move.name}: "
                f"{source_wh.name} → {dest_wh.name}, "
                f"Product: {product.name}, Qty: {move.product_qty}, "
                f"Existing layers: {len(existing_layers)}, "
                f"Has negative@source: {has_negative_source}, "
                f"Has positive@dest: {has_positive_dest}"
            )
            
            company = move.company_id
            
            # 🔴 STEP 1: Determine unit cost
            # For return moves, use cost from original transfer
            # For regular transfers, get FIFO cost from source warehouse
            if is_return_move and move.origin_returned_move_id:
                # Get cost from original transfer's layers
                original_move = move.origin_returned_move_id
                original_layers = valuation_layer_model.search([
                    ('stock_move_id', '=', original_move.id),
                    ('quantity', '<', 0),  # Negative layer (outgoing from original source)
                ], limit=1)
                
                if original_layers:
                    unit_cost = abs(original_layers[0].unit_cost)
                    total_cost = unit_cost * move.product_qty
                    _logger.info(
                        f"🔄 Return move: Using original transfer cost: "
                        f"unit={unit_cost:.4f}, total={total_cost:.4f}"
                    )
                else:
                    # Fallback if no original layer found
                    _logger.warning(f"⚠️ Return move but no original layer found, using FIFO")
                    fifo_service = self.env['fifo.service']
                    fifo_result = fifo_service.calculate_fifo_cost_with_landed_cost(
                        product, source_wh, move.product_qty, company.id
                    )
                    if isinstance(fifo_result, dict):
                        unit_cost = fifo_result.get('unit_cost', 0.0)
                        total_cost = fifo_result.get('cost', 0.0)
                    else:
                        unit_cost = float(fifo_result) if fifo_result else 0.0
                        total_cost = unit_cost * move.product_qty
            else:
                # Regular transfer: Get FIFO cost from SOURCE warehouse
                fifo_service = self.env['fifo.service']
                fifo_result = fifo_service.calculate_fifo_cost_with_landed_cost(
                    product, source_wh, move.product_qty, company.id
                )
                
                # Extract unit cost
                if isinstance(fifo_result, dict):
                    unit_cost = fifo_result.get('unit_cost', 0.0)
                    total_cost = fifo_result.get('cost', 0.0)
                else:
                    unit_cost = float(fifo_result) if fifo_result else 0.0
                    total_cost = unit_cost * move.product_qty
            
            # Fallback to standard price if still zero
            if unit_cost <= 0:
                unit_cost = product.standard_price or 0.0
                total_cost = unit_cost * move.product_qty
                _logger.warning(f"⚠️ FIFO cost is 0, using standard_price fallback: {unit_cost}")
            
            _logger.info(f"💰 Cost for {move_type}: unit={unit_cost:.4f}, total={total_cost:.4f}")
            
            # 🔴 STEP 2: Create negative layer at source warehouse (if not exists)
            if not has_negative_source:
                neg_desc = f'Return OUT: {source_wh.name} → {dest_wh.name}' if is_return_move else f'Transfer OUT: {source_wh.name} → {dest_wh.name}'
                neg_layer = valuation_layer_model.sudo().create({
                    'stock_move_id': move.id,
                    'product_id': product.id,
                    'warehouse_id': source_wh.id,
                    'quantity': -move.product_qty,
                    'unit_cost': unit_cost,
                    'value': -total_cost,
                    'remaining_qty': 0.0,  # Negative layers don't have remaining
                    'remaining_value': 0.0,
                    'company_id': company.id,
                    'description': neg_desc,
                })
                _logger.info(f"✅ Created NEGATIVE layer at {source_wh.name}: qty={-move.product_qty}, value={-total_cost:.4f}")
                
                # 🔴 CRITICAL: Run FIFO to consume from source warehouse's FIFO queue
                # This will reduce remaining_qty of existing layers at source warehouse
                neg_layer._run_fifo(-move.product_qty, company)
                _logger.info(f"✅ Ran FIFO consumption at {source_wh.name}")
            else:
                _logger.info(f"ℹ️ Negative layer at {source_wh.name} already exists (created by Odoo)")
                # 🆕 FIX: Check if existing negative layer has correct warehouse_id
                neg_layers = [l for l in existing_layers if l.quantity < 0]
                for neg_layer in neg_layers:
                    if neg_layer.warehouse_id and neg_layer.warehouse_id.id != source_wh.id:
                        _logger.warning(
                            f"⚠️ Fixing negative layer {neg_layer.id}: "
                            f"Wrong warehouse {neg_layer.warehouse_id.name} → {source_wh.name}"
                        )
                        neg_layer.warehouse_id = source_wh.id
            
            # 🔴 STEP 3: Create positive layer at destination warehouse (if not exists)
            # 🆕 CRITICAL FIX: This is essential for BOTH transfers AND returns!
            if not has_positive_dest:
                pos_desc = f'Return IN: {source_wh.name} → {dest_wh.name}' if is_return_move else f'Transfer IN: {source_wh.name} → {dest_wh.name}'
                pos_layer = valuation_layer_model.sudo().create({
                    'stock_move_id': move.id,
                    'product_id': product.id,
                    'warehouse_id': dest_wh.id,
                    'quantity': move.product_qty,
                    'unit_cost': unit_cost,
                    'value': total_cost,
                    'remaining_qty': move.product_qty,  # ✅ This becomes FIFO source for dest warehouse
                    'remaining_value': total_cost,
                    'company_id': company.id,
                    'description': pos_desc,
                })
                action = "returned to" if is_return_move else "transferred to"
                _logger.info(
                    f"✅ Created POSITIVE layer at {dest_wh.name}: "
                    f"qty={move.product_qty}, value={total_cost:.4f}, "
                    f"remaining_qty={move.product_qty} (Stock {action} FIFO queue)"
                )
            else:
                _logger.info(f"ℹ️ Positive layer at {dest_wh.name} already exists (created by Odoo)")
                # 🆕 FIX: Check if existing positive layer has correct warehouse_id
                pos_layers = [l for l in existing_layers if l.quantity > 0]
                for pos_layer in pos_layers:
                    if pos_layer.warehouse_id and pos_layer.warehouse_id.id != dest_wh.id:
                        _logger.warning(
                            f"⚠️ Fixing positive layer {pos_layer.id}: "
                            f"Wrong warehouse {pos_layer.warehouse_id.name} → {dest_wh.name}"
                        )
                        pos_layer.warehouse_id = dest_wh.id
            
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
                
                # CRITICAL FIX: Get unit cost from the ACTUAL delivery layer
                # Do NOT try to consume from FIFO queue (it's empty after delivery)
                # Instead, use the unit_cost that was calculated during the original delivery
                if original_wh:
                    try:
                        # Step 1: Find the NEGATIVE delivery layer from original move
                        # This layer contains the actual unit_cost used when delivering
                        original_delivery_layers = valuation_layer_model.search([
                            ('stock_move_id', '=', original_move.id),
                            ('quantity', '<', 0),  # NEGATIVE layer (outgoing/consumption)
                            ('warehouse_id', '=', original_wh.id),
                        ], limit=1)
                        
                        if original_delivery_layers:
                            # The delivery layer's unit_cost is the FIFO cost at consumption time
                            # (which includes landed costs already applied)
                            base_delivery_unit_cost = abs(original_delivery_layers[0].unit_cost)
                            
                            # Step 2: Get any additional landed costs that should be included
                            lc_model = self.env['stock.valuation.layer.landed.cost']
                            delivery_lc_records = lc_model.search([
                                ('valuation_layer_id', '=', original_delivery_layers[0].id),
                                ('warehouse_id', '=', original_wh.id),
                            ])
                            
                            unit_lc = 0.0
                            if delivery_lc_records:
                                # Get unit landed cost (landed_cost_value / quantity)
                                lc_value = sum(delivery_lc_records.mapped('landed_cost_value'))
                                lc_qty = delivery_lc_records[0].quantity or 1
                                unit_lc = lc_value / lc_qty if lc_qty > 0 else 0.0
                            
                            # Total unit cost = base delivery cost + unit landed cost
                            return_unit_cost = base_delivery_unit_cost + unit_lc
                            return_total_cost = return_unit_cost * move.product_qty
                            
                            _logger.info(
                                f"Return move {move.name}: "
                                f"Using delivery layer unit cost: {base_delivery_unit_cost}/unit + "
                                f"LC: {unit_lc}/unit = {return_unit_cost}/unit total"
                            )
                        else:
                            # Fallback: Try FIFO calculation if no delivery layer found
                            _logger.warning(
                                f"Return move {move.name}: "
                                f"No delivery layer found, falling back to FIFO calculation"
                            )
                            
                            fifo_result = fifo_service.calculate_fifo_cost_with_landed_cost(
                                move.product_id,
                                original_wh,
                                move.product_qty,
                                move.company_id.id
                            )
                            
                            if fifo_result['cost'] > 0 and fifo_result['qty'] > 0:
                                return_unit_cost = fifo_result['unit_cost']
                                return_total_cost = fifo_result['cost']
                    except Exception as e:
                        _logger.warning(
                            f"Failed to calculate return unit cost for move {move.name}: {e}"
                        )
            
            for layer in layers:
                # Determine correct warehouse based on layer quantity and move type
                is_return = bool(move.origin_returned_move_id)
                
                if layer.quantity < 0:
                    # Negative layer (outgoing/consumption)
                    if is_return:
                        # 🔴 CRITICAL FIX: Return move negative layer at SOURCE warehouse
                        # Return move: A → B (returning stock from A back to B)
                        # - Negative layer at A (consume from A's FIFO queue)
                        # - Positive layer at B (add to B's FIFO queue)
                        if source_wh and (not layer.warehouse_id or layer.warehouse_id.id != source_wh.id):
                            layer.warehouse_id = source_wh.id
                            _logger.info(
                                f"Return move: Set negative layer {layer.id} "
                                f"to source warehouse {source_wh.name} (consuming from FIFO queue)"
                            )
                    else:
                        # Regular outgoing: use source warehouse
                        if source_wh and (not layer.warehouse_id or layer.warehouse_id.id != source_wh.id):
                            layer.warehouse_id = source_wh.id
                    
                    # Fix unit_cost for return moves using FIFO cost with landed costs from ORIGINAL warehouse
                    if return_unit_cost is not None and return_unit_cost > 0:
                        layer.unit_cost = return_unit_cost
                        layer.value = layer.quantity * return_unit_cost
                        _logger.info(
                            f"Return negative layer {layer.id}: "
                            f"Set unit_cost={return_unit_cost} (from original WH: {original_wh.name if original_wh else 'Unknown'}), "
                            f"value={layer.value}, warehouse={layer.warehouse_id.name if layer.warehouse_id else 'None'}"
                        )
                        
                elif layer.quantity > 0:
                    # Positive layer (incoming) - ALWAYS use destination warehouse
                    if dest_wh and (not layer.warehouse_id or layer.warehouse_id.id != dest_wh.id):
                        layer.warehouse_id = dest_wh.id
                        if is_return:
                            _logger.info(
                                f"Cross-warehouse return: Set positive layer {layer.id} "
                                f"to destination warehouse {dest_wh.name} "
                                f"(cost from original WH: {original_wh.name if original_wh else 'Unknown'})"
                            )
                    
                    # Fix unit_cost for return moves using FIFO cost with landed costs from ORIGINAL warehouse
                    if return_unit_cost is not None and return_unit_cost > 0:
                        layer.unit_cost = return_unit_cost
                        layer.value = layer.quantity * return_unit_cost
                        _logger.info(
                            f"Return positive layer {layer.id}: "
                            f"Set unit_cost={return_unit_cost} (from original WH: {original_wh.name if original_wh else 'Unknown'}), "
                            f"value={layer.value}, warehouse={layer.warehouse_id.name if layer.warehouse_id else 'None'}"
                        )
                    
                    # Copy landed cost allocations from original move to return move
                    # This ensures landed costs are properly tracked and reversed
                    if is_return:
                        self._copy_landed_cost_to_return(
                            move.origin_returned_move_id, move, layer
                        )
                    # Creating new LC records would double-count the costs
    
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
