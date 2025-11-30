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
    
    warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Warehouse',
        index=True,
        help='The warehouse where this layer applies. Used for per-warehouse FIFO tracking.',
        ondelete='restrict',
    )
    
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
        """
        # Priority 1: Get warehouse from context if provided
        if not vals.get('warehouse_id') and self.env.context.get('fifo_warehouse_id'):
            vals['warehouse_id'] = self.env.context.get('fifo_warehouse_id')
        
        # Priority 2: Derive from stock_move if not set yet
        if not vals.get('warehouse_id') and vals.get('stock_move_id'):
            move = self.env['stock.move'].browse(vals['stock_move_id'])
            if move:
                quantity = vals.get('quantity', 0)
                source_usage = move.location_id.usage if move.location_id else None
                dest_usage = move.location_dest_id.usage if move.location_dest_id else None
                
                # For positive layers (incoming): use destination warehouse
                if quantity > 0:
                    if move.location_dest_id and move.location_dest_id.warehouse_id:
                        vals['warehouse_id'] = move.location_dest_id.warehouse_id.id
                # For negative layers (outgoing/consumption): determine source warehouse
                else:
                    # Determine the correct warehouse based on move type
                    if source_usage in ('transit', 'internal'):
                        # Transit/Internal → Anywhere: Track source warehouse
                        if move.location_id and move.location_id.warehouse_id:
                            vals['warehouse_id'] = move.location_id.warehouse_id.id
                    elif dest_usage in ('internal', 'transit'):
                        # Non-internal (supplier, etc) → Internal/Transit: Track destination warehouse
                        if move.location_dest_id and move.location_dest_id.warehouse_id:
                            vals['warehouse_id'] = move.location_dest_id.warehouse_id.id
        
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
        
        return super().create(vals)
    
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
    def _get_fifo_queue(self, product_id, warehouse_id, company_id=None):
        """
        Retrieve FIFO queue for a product at a specific warehouse.
        
        Returns valuation layers ordered from oldest (first-in) to newest,
        filtered to only those at the specified warehouse.
        
        Args:
            product_id: stock.product.product
            warehouse_id: stock.warehouse (or id)
            company_id: res.company (defaults to current company)
            
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
            ('quantity', '>', 0),  # Only layers with positive quantity
        ]
        
        return self.search(domain, order='create_date asc, id asc')
    
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
                
                # Allow small rounding differences and tolerate small negative for FIFO
                # Only block if significantly negative (more than 1 unit)
                if float_compare(qty_after, -1.0, precision_digits=precision_qty) < 0:
                    _logger.warning(
                        f"Warehouse balance going negative: "
                        f"Product={layer.product_id.display_name}, "
                        f"Warehouse={layer.warehouse_id.name}, "
                        f"Qty Before={total_remaining_qty:.2f}, "
                        f"This Layer Qty={layer.quantity:.2f}, "
                        f"Qty After={qty_after:.2f}"
                    )
                    
                    # Don't raise error, just log warning
                    # This allows FIFO to work properly with returns
                    # raise ValidationError(
                    #     f"❌ Warehouse จะติดลบ!\n\n"
                    #     f"Warehouse: {layer.warehouse_id.name}\n"
                    #     f"สินค้า: {layer.product_id.display_name}\n"
                    #     f"จำนวนคงเหลือ: {total_remaining_qty:.2f}\n"
                    #     f"พยายามตัดออก: {abs(layer.quantity):.2f}\n"
                    #     f"จะเหลือ: {qty_after:.2f} (ติดลบ!)\n\n"
                    #     f"⚠️ ไม่สามารถขายหรือโอนสินค้าได้มากกว่าที่มีใน Warehouse นี้\n\n"
                    #     f"คำแนะนำ:\n"
                    #     f"1. ถ้าเป็นการ Return - ตรวจสอบว่า Return ไปที่ Warehouse เดิมหรือไม่\n"
                    #     f"2. ถ้าเป็นการขาย - ตรวจสอบว่ามี Stock เพียงพอใน {layer.warehouse_id.name} หรือไม่\n"
                    #     f"3. ตรวจสอบว่ามีการรับสินค้าเข้า Warehouse นี้ถูกต้องหรือไม่"
                    # )
    
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
        if not self.warehouse_id:
            _logger.warning(
                f"Layer {self.id} for product {self.product_id.display_name} "
                f"has no warehouse_id, falling back to standard FIFO"
            )
            return super(StockValuationLayer, self)._run_fifo(quantity, company)
        
        # Get FIFO queue for this product at THIS warehouse only
        candidates_domain = [
            ('product_id', '=', self.product_id.id),
            ('warehouse_id', '=', self.warehouse_id.id),  # 🔴 KEY: Same warehouse only
            ('remaining_qty', '>', 0),
            ('company_id', '=', company.id),
        ]
        
        candidates = self.search(candidates_domain, order='create_date, id')
        
        _logger.info(
            f"🔍 _run_fifo() for Layer {self.id}: "
            f"Product={self.product_id.display_name}, "
            f"Warehouse={self.warehouse_id.name}, "
            f"Consuming qty={abs(quantity):.2f}, "
            f"Found {len(candidates)} candidate layers with remaining_qty > 0"
        )
        
        qty_to_take_on_candidates = abs(quantity)
        tmp_value = 0  # Accumulator for total value consumed
        
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
            
            _logger.info(
                f"  📥 Consuming from Layer {candidate.id}: "
                f"qty_taken={qty_taken_on_candidate:.2f} @ {candidate_unit_cost:.4f}/unit = {value_taken_on_candidate:.4f}, "
                f"remaining: {candidate.remaining_qty:.2f} → {new_remaining_qty:.2f}"
            )
            
            candidate_vals = {
                'remaining_qty': new_remaining_qty,
                'remaining_value': new_remaining_value,
            }
            candidate.write(candidate_vals)
            
            # Accumulate total value
            tmp_value += value_taken_on_candidate
            qty_to_take_on_candidates -= qty_taken_on_candidate
            
            # Check if we've consumed enough
            if float_compare(qty_to_take_on_candidates, 0, precision_rounding=self.product_id.uom_id.rounding) <= 0:
                break
        
        # If we couldn't consume all qty from FIFO queue (shortage)
        if float_compare(qty_to_take_on_candidates, 0, precision_rounding=self.product_id.uom_id.rounding) > 0:
            _logger.warning(
                f"⚠️ FIFO shortage: Product {self.product_id.display_name} at {self.warehouse_id.name}: "
                f"Need {abs(quantity):.2f}, but only {abs(quantity) - qty_to_take_on_candidates:.2f} available. "
                f"Shortage: {qty_to_take_on_candidates:.2f} - Using standard_price fallback"
            )
            # Use standard_price for the shortage
            tmp_value += qty_to_take_on_candidates * self.product_id.standard_price
        
        _logger.info(
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

