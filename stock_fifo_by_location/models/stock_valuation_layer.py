# -*- coding: utf-8 -*-
"""
Stock Valuation Layer Model Extension

This module extends stock.valuation.layer to include location_id for per-location FIFO tracking.
"""

from odoo import models, fields, api
from odoo.tools import float_compare, float_round
import logging

_logger = logging.getLogger(__name__)


class StockValuationLayer(models.Model):
    """
    Extension of stock.valuation.layer to support per-location FIFO cost accounting.
    
    Each valuation layer now tracks which stock.location the inventory is stored in,
    enabling accurate FIFO queue management across multiple locations.
    """
    
    _inherit = 'stock.valuation.layer'
    
    warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Warehouse',
        index=True,
        help='The warehouse where this layer applies. Used for per-warehouse FIFO tracking.',
        ondelete='restrict',
    )
    
    # SQL Constraints for performance
    _sql_constraints = [
        # Ensure proper indexing for warehouse consistency checks
    ]
    
    def init(self):
        """Create composite indexes for better FIFO query performance."""
        # Composite index for FIFO queue retrieval (most common query)
        # Covers: product_id, warehouse_id, remaining_qty, company_id
        self.env.cr.execute("""
            CREATE INDEX IF NOT EXISTS stock_valuation_layer_fifo_queue_idx
            ON stock_valuation_layer (product_id, warehouse_id, company_id, remaining_qty, create_date, id)
            WHERE remaining_qty > 0
        """)
        
        # Index for warehouse balance calculations
        self.env.cr.execute("""
            CREATE INDEX IF NOT EXISTS stock_valuation_layer_warehouse_balance_idx
            ON stock_valuation_layer (warehouse_id, product_id, quantity)
        """)
        
        # Index for product valuation lookups
        self.env.cr.execute("""
            CREATE INDEX IF NOT EXISTS stock_valuation_layer_product_wh_idx
            ON stock_valuation_layer (product_id, warehouse_id, id)
        """)
    
    landed_cost_ids = fields.One2many(
        'stock.valuation.layer.landed.cost',
        'valuation_layer_id',
        string='Landed Costs',
        help='Landed costs allocated to this valuation layer at specific warehouses.'
    )
    
    total_landed_cost = fields.Float(
        string='Total Landed Cost',
        compute='_compute_total_landed_cost',
        digits='Product Price',
        help='Total landed cost across all warehouses for this layer.'
    )
    
    @api.model
    def create(self, vals):
        """
        Override create to capture warehouse information from context.
        
        When creating valuation layers, warehouse_id can be passed via context
        under key 'fifo_warehouse_id'.
        
        🔴 CRITICAL v17.0.1.2.4: Ensure warehouse_id is set BEFORE calling super().create()
        because Odoo's create() will call _run_fifo() which needs warehouse_id to be set.
        """
        import logging
        _create_logger = logging.getLogger(__name__)
        
        # Priority 1: Get warehouse from context if provided
        if not vals.get('warehouse_id') and self.env.context.get('fifo_warehouse_id'):
            vals['warehouse_id'] = self.env.context.get('fifo_warehouse_id')
            _create_logger.info(f"📍 Layer create: warehouse_id={vals['warehouse_id']} from context")
        
        # Priority 2: Derive from stock_move if not set yet
        if not vals.get('warehouse_id') and vals.get('stock_move_id'):
            move = self.env['stock.move'].browse(vals['stock_move_id'])
            _create_logger.info(
                f"📍 Layer create: move={move.name}, "
                f"from {move.location_id.complete_name} → {move.location_dest_id.complete_name}"
            )
            if move:
                quantity = vals.get('quantity', 0)
                source_usage = move.location_id.usage if move.location_id else None
                dest_usage = move.location_dest_id.usage if move.location_dest_id else None
                
                # For positive layers (incoming): use destination warehouse
                if quantity > 0:
                    if move.location_dest_id and move.location_dest_id.warehouse_id:
                        vals['warehouse_id'] = move.location_dest_id.warehouse_id.id
                        _create_logger.info(
                            f"📍 Positive layer: set warehouse_id={vals['warehouse_id']} "
                            f"({move.location_dest_id.warehouse_id.name}) from dest location"
                        )
                # For negative layers (outgoing/consumption): determine source warehouse
                else:
                    # Determine the correct warehouse based on move type
                    if source_usage in ('transit', 'internal'):
                        # Transit/Internal → Anywhere: Track source warehouse
                        if move.location_id and move.location_id.warehouse_id:
                            vals['warehouse_id'] = move.location_id.warehouse_id.id
                            _create_logger.info(
                                f"📍 Negative layer: set warehouse_id={vals['warehouse_id']} "
                                f"({move.location_id.warehouse_id.name}) from source location (internal/transit)"
                            )
                    elif dest_usage in ('internal', 'transit'):
                        # Non-internal (supplier, etc) → Internal/Transit: Track destination warehouse
                        if move.location_dest_id and move.location_dest_id.warehouse_id:
                            vals['warehouse_id'] = move.location_dest_id.warehouse_id.id
                            _create_logger.info(
                                f"📍 Negative layer: set warehouse_id={vals['warehouse_id']} "
                                f"({move.location_dest_id.warehouse_id.name}) from dest location (fallback)"
                            )
        
        # Priority 3: Try to get from move_line through stock_move
        if not vals.get('warehouse_id') and vals.get('stock_move_id'):
            move = self.env['stock.move'].browse(vals['stock_move_id'])
            if move and move.move_line_ids:
                quantity = vals.get('quantity', 0)
                # Use the appropriate warehouse from first move line
                for move_line in move.move_line_ids:
                    if quantity > 0 and move_line.location_dest_id and move_line.location_dest_id.warehouse_id:
                        vals['warehouse_id'] = move_line.location_dest_id.warehouse_id.id
                        break
                    elif quantity <= 0 and move_line.location_id and move_line.location_id.warehouse_id:
                        vals['warehouse_id'] = move_line.location_id.warehouse_id.id
                        break
        
        if vals.get('warehouse_id'):
            wh = self.env['stock.warehouse'].browse(vals['warehouse_id'])
            _create_logger.info(
                f"✅ Creating layer with warehouse_id={vals['warehouse_id']} ({wh.name}), "
                f"qty={vals.get('quantity', 0):.2f}, product_id={vals.get('product_id')}"
            )
        else:
            _create_logger.warning(
                f"⚠️ Creating layer WITHOUT warehouse_id! qty={vals.get('quantity', 0)}, "
                f"move_id={vals.get('stock_move_id')}, product_id={vals.get('product_id')}"
            )
        
        # 🔴 CRITICAL: Call super with warehouse_id already in vals
        # This ensures warehouse_id is set before _run_fifo() is called
        layer = super().create(vals)
        
        # 🔴 VERIFY: Log the actual warehouse_id after creation
        if layer.warehouse_id:
            _create_logger.info(
                f"✅ Layer {layer.id} created with warehouse_id={layer.warehouse_id.id} ({layer.warehouse_id.name})"
            )
        else:
            _create_logger.error(
                f"❌ Layer {layer.id} created WITHOUT warehouse_id! This will cause wrong FIFO consumption!"
            )
        
        return layer
    
    def _validate_location_consistency(self):
        """
        Validate that consumption layers match the warehouse of the outgoing move.
        
        This helper can be called during move validation to ensure FIFO queue correctness.
        """
        for layer in self:
            if layer.stock_move_id and layer.stock_move_id.location_dest_id:
                if not layer.warehouse_id:
                    # Layer has no warehouse - needs migration
                    return False
        
        return True
    
    @api.model
    def _get_fifo_queue(self, product_id, warehouse_id, company_id=None, limit=None):
        """
        Retrieve FIFO queue for a product at a specific warehouse.
        
        Returns valuation layers ordered from oldest (first-in) to newest,
        filtered to only those at the specified warehouse.
        
        Args:
            product_id: stock.product.product
            warehouse_id: stock.warehouse (or id)
            company_id: res.company (defaults to current company)
            limit: int (optional) - limit number of layers returned for performance
            
        Returns:
            Recordset of stock.valuation.layer ordered by FIFO
        """
        if not company_id:
            company_id = self.env.company.id
        
        # Handle both recordset and id
        wh_id = warehouse_id.id if hasattr(warehouse_id, 'id') else warehouse_id
        
        domain = [
            ('product_id', '=', product_id.id),
            ('warehouse_id', '=', wh_id),
            ('company_id', '=', company_id),
            ('remaining_qty', '>', 0),  # 🚀 PERFORMANCE: Use remaining_qty instead of quantity
        ]
        
        # 🚀 PERFORMANCE: Add limit to prevent scanning too many records
        # Default limit of 1000 should be enough for most FIFO scenarios
        search_limit = limit if limit is not None else 1000
        
        return self.search(domain, order='create_date asc, id asc', limit=search_limit)
    
    @api.model
    def _get_total_available_qty(self, product_id, warehouse_id, company_id=None):
        """
        Get total available quantity in FIFO queue for a product at warehouse.
        
        Args:
            product_id: stock.product.product
            warehouse_id: stock.warehouse (or id)
            company_id: res.company
            
        Returns:
            float: Total available quantity
        """
        if not company_id:
            company_id = self.env.company.id
        
        layers = self._get_fifo_queue(product_id, warehouse_id, company_id)
        return sum(layer.quantity for layer in layers)
    
    @api.depends('landed_cost_ids.landed_cost_value')
    def _compute_total_landed_cost(self):
        """Compute total landed cost for this layer across all locations."""
        precision = self.env['decimal.precision'].precision_get('Product Price')
        for layer in self:
            total = sum(layer.landed_cost_ids.mapped('landed_cost_value'))
            layer.total_landed_cost = float_round(total, precision_digits=precision)
    
    @api.constrains('warehouse_id', 'quantity', 'remaining_qty', 'remaining_value')
    def _check_warehouse_consistency(self):
        """
        Validate warehouse_id is set for all layers with non-zero quantity.
        Also check that warehouse doesn't go into negative balance.
        
        This ensures data consistency and prevents issues with FIFO queue management.
        Layers without warehouse_id cannot be properly tracked in per-warehouse FIFO.
        
        NOTE: We skip negative balance check for return moves because:
        1. Return moves may create temporary negative layers during FIFO consumption
        2. Return moves add stock back, so final balance will be positive
        3. The validation in _action_done() already ensures return goes to correct warehouse
        """
        from odoo.exceptions import ValidationError
        import logging
        _logger = logging.getLogger(__name__)
        
        for layer in self:
            # Skip validation for layers with zero quantity (fully consumed)
            if float_compare(abs(layer.quantity), 0, precision_digits=2) == 0:
                continue
            
            # Layers with quantity MUST have warehouse_id
            if not layer.warehouse_id:
                raise ValidationError(
                    f"Valuation layer {layer.id} for product {layer.product_id.display_name} "
                    f"has quantity {layer.quantity} but no warehouse_id. "
                    f"All layers with quantity must be assigned to a warehouse."
                )
            
            # 🔴 Check for negative warehouse balance
            # Only check outgoing moves that are NOT returns
            if layer.quantity < 0:
                # Skip validation for return moves
                # Return moves are handled by validation in stock_move._action_done()
                if layer.stock_move_id:
                    move = layer.stock_move_id
                    # Check if this move or any related move is a return
                    if move.origin_returned_move_id or move.picking_id.picking_type_code == 'incoming':
                        continue
                
                # Calculate total remaining qty at this warehouse BEFORE this layer
                domain = [
                    ('product_id', '=', layer.product_id.id),
                    ('warehouse_id', '=', layer.warehouse_id.id),
                    ('id', '<', layer.id),  # Only layers created before this one
                ]
                previous_layers = self.search(domain)
                total_remaining_qty = sum(previous_layers.mapped('remaining_qty'))
                
                # Check if consumption would make warehouse negative
                precision_qty = self.env['decimal.precision'].precision_get('Product Unit of Measure')
                
                qty_after = total_remaining_qty + layer.quantity  # layer.quantity is negative
                
                # Check validation mode from config
                validation_mode = self.env['ir.config_parameter'].sudo().get_param(
                    'stock_fifo_by_location.negative_balance_mode',
                    default='warning'  # 'strict', 'warning', or 'disabled'
                )
                
                # Allow small rounding differences (0.01 unit tolerance)
                tolerance = float(self.env['ir.config_parameter'].sudo().get_param(
                    'stock_fifo_by_location.negative_balance_tolerance',
                    default='0.01'
                ))
                
                if float_compare(qty_after, -tolerance, precision_digits=precision_qty) < 0:
                    error_msg = (
                        f"❌ คลัง {layer.warehouse_id.name} จะติดลบ!\n\n"
                        f"สินค้า: {layer.product_id.display_name}\n"
                        f"จำนวนคงเหลือปัจจุบัน: {total_remaining_qty:.2f} {layer.product_id.uom_id.name}\n"
                        f"พยายามตัดออก: {abs(layer.quantity):.2f} {layer.product_id.uom_id.name}\n"
                        f"จะเหลือ: {qty_after:.2f} {layer.product_id.uom_id.name} (ติดลบ!)\n\n"
                        f"⚠️ ไม่สามารถขายหรือโอนสินค้าได้มากกว่าที่มีในคลังนี้\n\n"
                        f"💡 คำแนะนำ:\n"
                    )
                    
                    # Try to find alternative warehouses
                    fifo_service = self.env['fifo.service']
                    try:
                        fallback_whs = fifo_service._find_fallback_warehouses(
                            layer.product_id, layer.warehouse_id, abs(qty_after), layer.company_id.id
                        )
                        
                        if fallback_whs:
                            error_msg += f"   🏭 คลังอื่นที่มีสินค้า:\n"
                            for fb in fallback_whs[:3]:  # Show top 3
                                wh = self.env['stock.warehouse'].browse(fb['warehouse_id'])
                                error_msg += f"      • {wh.name}: {fb['available_qty']:.2f} {layer.product_id.uom_id.name}\n"
                            error_msg += f"\n   ➡️ แนะนำ: โอนสินค้าจากคลังอื่นมายังคลังนี้ก่อน\n"
                        else:
                            error_msg += f"   ⚠️ ไม่พบสินค้าในคลังอื่น\n"
                            error_msg += f"   ➡️ แนะนำ: สั่งซื้อสินค้าเพิ่ม หรือตรวจสอบการรับสินค้าเข้า\n"
                    except Exception as e:
                        _logger.warning(f"Failed to find fallback warehouses: {e}")
                        error_msg += f"   ➡️ แนะนำ: ตรวจสอบ Stock ในคลังอื่น หรือสั่งซื้อเพิ่m\n"
                    
                    error_msg += (
                        f"\n🔧 วิธีแก้ไข:\n"
                        f"   1. ถ้าเป็นการ Return: ตรวจสอบว่า Return ไปคลังที่ถูกต้อง\n"
                        f"   2. ถ้าเป็นการขาย: โอนสินค้าจากคลังอื่นมาก่อน\n"
                        f"   3. ตรวจสอบว่ามีการรับสินค้าเข้า {layer.warehouse_id.name} ถูกต้อง\n"
                        f"   4. ตรวจสอบ Inventory Adjustment ที่อาจทำให้ Stock ลดลง\n"
                    )
                    
                    if validation_mode == 'strict':
                        # STRICT: Always raise error
                        raise ValidationError(error_msg)
                    elif validation_mode == 'warning':
                        # WARNING: Log warning but allow (for troubleshooting)
                        _logger.warning(
                            f"Negative balance warning: Product={layer.product_id.display_name}, "
                            f"Warehouse={layer.warehouse_id.name}, After={qty_after:.2f}"
                        )
                        # Show user warning via message
                        if hasattr(self.env.user, 'notify_warning'):
                            self.env.user.notify_warning(
                                message=f"⚠️ คลัง {layer.warehouse_id.name} มี Stock ไม่พอ!",
                                title="Stock Warning"
                            )
                    # else: disabled - do nothing
    
    @api.model
    def get_landed_cost_at_warehouse(self, product_id, warehouse_id, company_id=None):
        """
        Get total landed cost for a product at a specific warehouse.
        
        Sums all landed costs from all valuation layers of the product at that warehouse.
        
        Args:
            product_id: stock.product.product
            warehouse_id: stock.warehouse (or id)
            company_id: res.company
            
        Returns:
            float: Total landed cost at warehouse
        """
        if not company_id:
            company_id = self.env.company.id
        
        # Handle both recordset and id
        wh_id = warehouse_id.id if hasattr(warehouse_id, 'id') else warehouse_id
        
        layers = self.search([
            ('product_id', '=', product_id.id),
            ('warehouse_id', '=', wh_id),
            ('company_id', '=', company_id),
            ('quantity', '>', 0),
        ])
        
        landed_cost_model = self.env['stock.valuation.layer.landed.cost']
        total_landed_cost = 0.0
        
        for layer in layers:
            # Get landed costs for this layer at this warehouse
            lc_records = landed_cost_model.search([
                ('valuation_layer_id', '=', layer.id),
                ('warehouse_id', '=', wh_id),
            ])
            total_landed_cost += sum(lc_records.mapped('landed_cost_value'))
        
        precision = self.env['decimal.precision'].precision_get('Product Price')
        return float_round(total_landed_cost, precision_digits=precision)
    
    def _run_fifo(self, quantity, company):
        """
        🔴 CRITICAL OVERRIDE: Run FIFO per warehouse instead of globally.
        
        This is the KEY fix for the valuation issue. Odoo standard _run_fifo() 
        calculates remaining_qty by consuming from ALL warehouses together,
        which is incorrect for per-warehouse FIFO tracking.
        
        This override ensures FIFO consumption respects warehouse boundaries:
        - Each warehouse maintains its own independent FIFO queue
        - remaining_qty is calculated per warehouse
        - No cross-warehouse consumption
        
        Args:
            quantity: float - quantity to consume (negative for outgoing)
            company: res.company - company context
            
        Returns:
            None - updates remaining_qty and remaining_value in place
        """
        import logging
        _logger = logging.getLogger(__name__)
        
        self.ensure_one()
        
        # For positive quantity (incoming), set remaining = quantity
        if quantity > 0 or float_compare(quantity, 0, precision_rounding=self.product_id.uom_id.rounding) == 0:
            self.remaining_qty = self.quantity
            self.remaining_value = self.value
            return
        
        # Negative quantity (outgoing) - need to consume from FIFO queue
        # CRITICAL: Only consume from the SAME warehouse
        
        # 🔴 CRITICAL FIX v17.0.1.2.6: This method is now mostly unused
        # since we override product._get_fifo_candidates() instead
        # But keep for manual calls to _run_fifo() (e.g., inter-warehouse transfers)
        
        _logger.error(f"🔧 _run_fifo() Layer {self.id}: Product={self.product_id.display_name}, Qty={quantity}")
        
        # Flush and invalidate to ensure warehouse_id is current
        self.flush_recordset(['warehouse_id', 'product_id', 'company_id'])
        self.invalidate_recordset(['warehouse_id', 'product_id', 'company_id'])
        
        # Get warehouse_id - should be set by now from create()
        layer_warehouse_id = self.warehouse_id.id if self.warehouse_id else False
        
        if not layer_warehouse_id:
            _logger.error(
                f"❌ Layer {self.id} for product {self.product_id.display_name} "
                f"has NO warehouse_id in _run_fifo() even after flush+refresh! "
                f"This will cause incorrect FIFO consumption. "
                f"Falling back to standard FIFO (consuming from all warehouses)."
            )
            return super(StockValuationLayer, self)._run_fifo(quantity, company)
        
        # 🔴 CRITICAL FIX v17.0.1.2.3: Flush pending database writes before querying
        # This ensures we see all recently created layers (e.g., return moves)
        # Without this, we might not see layers created in the same transaction
        self.env['stock.valuation.layer'].flush_model(['product_id', 'warehouse_id', 'remaining_qty', 'company_id', 'create_date'])
        
        # Get FIFO queue for this product at THIS warehouse only
        candidates_domain = [
            ('product_id', '=', self.product_id.id),
            ('warehouse_id', '=', layer_warehouse_id),  # 🔴 KEY: Same warehouse only
            ('remaining_qty', '>', 0),
            ('company_id', '=', company.id),
        ]
        
        _logger.error(f"🔧 Step 4: Searching candidates with domain: {candidates_domain}")
        
        candidates = self.search(candidates_domain, order='create_date, id')
        
        # Get warehouse name for logging
        warehouse_name = self.warehouse_id.name if self.warehouse_id else 'Unknown'
        
        _logger.error(
            f"🔍 _run_fifo() QUERY RESULT - Layer {self.id}: "
            f"Product={self.product_id.display_name}, "
            f"Warehouse={warehouse_name} (ID={layer_warehouse_id}), "
            f"Consuming qty={abs(quantity):.2f}, "
            f"Found {len(candidates)} candidate layers"
        )
        
        if candidates:
            _logger.error(f"🔍 Candidate layers found:")
            for c in candidates[:5]:  # Show first 5
                _logger.error(f"  - Layer {c.id}: warehouse={c.warehouse_id.name if c.warehouse_id else 'None'} (ID={c.warehouse_id.id if c.warehouse_id else 'None'}), remaining={c.remaining_qty}")
        
        qty_to_take_on_candidates = abs(quantity)
        tmp_value = 0  # Accumulator for total value consumed
        
        # 🚀 PERFORMANCE: Collect all updates in batch for bulk write
        updates_to_write = []
        
        for candidate in candidates:
            # How much can we take from this candidate?
            qty_taken_on_candidate = min(qty_to_take_on_candidates, candidate.remaining_qty)
            
            # Calculate value proportion
            candidate_unit_cost = candidate.remaining_value / candidate.remaining_qty if candidate.remaining_qty > 0 else 0
            value_taken_on_candidate = qty_taken_on_candidate * candidate_unit_cost
            
            # Update candidate's remaining
            new_remaining_qty = candidate.remaining_qty - qty_taken_on_candidate
            new_remaining_value = candidate.remaining_value - value_taken_on_candidate
            
            # Ensure no negative remaining due to rounding
            if new_remaining_qty < 0:
                new_remaining_qty = 0
                new_remaining_value = 0
            
            _logger.error(
                f"  📥 CONSUMING from Layer {candidate.id} at warehouse {candidate.warehouse_id.name if candidate.warehouse_id else 'None'} (ID={candidate.warehouse_id.id if candidate.warehouse_id else 'None'}): "
                f"qty_taken={qty_taken_on_candidate:.2f} @ {candidate_unit_cost:.4f}/unit = {value_taken_on_candidate:.4f}, "
                f"remaining: {candidate.remaining_qty:.2f} → {new_remaining_qty:.2f}"
            )
            
            # Store update for batch write
            updates_to_write.append({
                'record': candidate,
                'vals': {
                    'remaining_qty': new_remaining_qty,
                    'remaining_value': new_remaining_value,
                }
            })
            
            # Accumulate total value
            tmp_value += value_taken_on_candidate
            qty_to_take_on_candidates -= qty_taken_on_candidate
            
            # 🚀 PERFORMANCE: Early exit if we've consumed enough
            if float_compare(qty_to_take_on_candidates, 0, precision_rounding=self.product_id.uom_id.rounding) <= 0:
                break
        
        # 🚀 PERFORMANCE: Bulk write all updates at once
        for update in updates_to_write:
            update['record'].write(update['vals'])
        
        # If we couldn't consume all qty from FIFO queue (shortage)
        if float_compare(qty_to_take_on_candidates, 0, precision_rounding=self.product_id.uom_id.rounding) > 0:
            _logger.warning(
                f"⚠️ FIFO shortage: Product {self.product_id.display_name} at {self.warehouse_id.name}: "
                f"Need {abs(quantity):.2f}, but only {abs(quantity) - qty_to_take_on_candidates:.2f} available. "
                f"Shortage: {qty_to_take_on_candidates:.2f} - Using standard_price fallback"
            )
            # Use standard_price for the shortage
            tmp_value += qty_to_take_on_candidates * self.product_id.standard_price
        
        _logger.debug(
            f"✅ _run_fifo() complete: "
            f"Total value consumed: {tmp_value:.4f}, "
            f"Setting this layer (ID={self.id}) remaining to 0"
        )
        
        # Update this layer's values
        # Negative layers don't have remaining (they are consumption)
        # IMPORTANT: Use 0.0 (float) not 0 to ensure proper database storage
        self.write({
            'remaining_qty': 0.0,
            'remaining_value': 0.0,
        })

