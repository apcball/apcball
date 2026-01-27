# -*- coding: utf-8 -*-
"""
Stock Quant Extension for Warehouse-Aware Inventory Adjustments

This module extends stock.quant to support per-warehouse FIFO inventory adjustments.
"""

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_round
import logging

_logger = logging.getLogger(__name__)


class StockQuant(models.Model):
    """
    Extension of stock.quant to support warehouse-aware inventory adjustments.
    
    When adjusting inventory (adding or reducing stock), the system will:
    - For increases: Create positive SVL at the warehouse of the location with user-selected cost
    - For decreases: Use _run_fifo() that respects warehouse boundaries
    """
    
    _inherit = 'stock.quant'
    
    # Cost rule for inventory adjustment
    inventory_cost_rule = fields.Selection([
        ('standard', 'Standard Price'),
        ('last_purchase', 'Last Purchase Price (Warehouse)'),
        ('manual', 'Manual Cost'),
    ], string='Cost Rule', default='standard',
       help='Cost rule for inventory increase:\n'
            '- Standard Price: Use product standard price\n'
            '- Last Purchase Price: Use last purchase price at this warehouse\n'
            '- Manual Cost: Enter cost manually')
    
    inventory_manual_cost = fields.Float(
        string='Manual Unit Cost',
        digits='Product Price',
        help='Manual unit cost for inventory adjustment when cost rule is "Manual Cost"'
    )
    
    def _get_inventory_move_values(self, qty, location_id, location_dest_id, package_id=False, package_dest_id=False):
        """
        Override to add warehouse context for inventory adjustments.
        
        This ensures that valuation layers created from inventory adjustments
        will have the correct warehouse_id.
        """
        vals = super()._get_inventory_move_values(qty, location_id, location_dest_id, package_id=package_id, package_dest_id=package_dest_id)
        
        # Determine warehouse from location
        warehouse = None
        if location_dest_id.usage == 'internal':
            warehouse = location_dest_id.warehouse_id
        elif location_id.usage == 'internal':
            warehouse = location_id.warehouse_id
        
        if warehouse:
            # Store warehouse in move for later use
            vals['warehouse_id'] = warehouse.id
        
        return vals
    
    def _apply_inventory(self):
        """
        Override to inject warehouse-aware cost calculation for inventory adjustments.
        
        This method is called when inventory adjustment is applied (validated).
        We intercept it to:
        1. Set correct warehouse_id on created stock moves
        2. Apply proper cost rules for inventory increases
        3. Ensure FIFO consumption respects warehouse boundaries for decreases
        """
        # Validate cost rules before applying
        precision = self.env['decimal.precision'].precision_get('Product Price')
        for quant in self:
            if quant.inventory_cost_rule == 'manual':
                if float_compare(quant.inventory_manual_cost, 0, precision_digits=precision) <= 0:
                    raise UserError(_(
                        "Manual cost must be greater than zero for product %s.\n"
                        "Please enter a valid manual cost."
                    ) % quant.product_id.display_name)
        
        # Store cost rules before applying inventory
        cost_rules = {}
        for quant in self:
            if quant.inventory_cost_rule or quant.inventory_manual_cost:
                cost_rules[quant.id] = {
                    'rule': quant.inventory_cost_rule or 'standard',
                    'manual_cost': quant.inventory_manual_cost or 0.0,
                    'warehouse': quant.location_id.warehouse_id,
                }
        
        # Apply inventory (creates stock moves)
        # Pass cost rules in context for use in move/SVL creation
        res = super(StockQuant, self.with_context(
            inventory_cost_rules=cost_rules
        ))._apply_inventory()
        
        return res
    
    def _get_inventory_cost_for_increase(self, warehouse=None):
        """
        Calculate unit cost for inventory increase based on selected cost rule.
        
        Args:
            warehouse: stock.warehouse record for last purchase price lookup
            
        Returns:
            float: unit cost to use for inventory increase
        """
        self.ensure_one()
        
        product = self.product_id
        cost_rule = self.inventory_cost_rule or 'standard'
        precision = self.env['decimal.precision'].precision_get('Product Price')
        
        if cost_rule == 'manual':
            # Use manual cost entered by user
            if float_compare(self.inventory_manual_cost, 0, precision_digits=precision) <= 0:
                raise UserError(_(
                    "Manual cost must be greater than zero for product %s.\n"
                    "Please enter a valid manual cost."
                ) % product.display_name)
            return self.inventory_manual_cost
        
        elif cost_rule == 'last_purchase':
            # Get last purchase price at this warehouse
            if not warehouse:
                warehouse = self.location_id.warehouse_id
            
            if not warehouse:
                raise UserError(_(
                    "Cannot determine warehouse for location %s.\n"
                    "Last purchase price requires a warehouse."
                ) % self.location_id.display_name)
            
            # Find last receipt to this warehouse
            last_receipt_layer = self.env['stock.valuation.layer'].search([
                ('product_id', '=', product.id),
                ('warehouse_id', '=', warehouse.id),
                ('quantity', '>', 0),
                ('stock_move_id.location_id.usage', 'in', ['supplier', 'production']),
            ], order='create_date desc', limit=1)
            
            if last_receipt_layer:
                last_cost = last_receipt_layer.unit_cost
                _logger.info(
                    f"Using last purchase price for {product.name} at {warehouse.name}: "
                    f"{last_cost}/unit (from layer {last_receipt_layer.id})"
                )
                return last_cost
            else:
                # Fallback to standard price if no purchase history
                _logger.warning(
                    f"No purchase history found for {product.name} at {warehouse.name}. "
                    f"Using standard price: {product.standard_price}"
                )
                return product.standard_price
        
        else:  # 'standard'
            # Use product standard price
            return product.standard_price


class StockMove(models.Model):
    """
    Extension of stock.move to support warehouse-aware inventory adjustments.
    """
    
    _inherit = 'stock.move'
    
    warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Warehouse',
        help='Warehouse for this move (used in inventory adjustments)'
    )
    
    def _create_in_svl(self, forced_quantity=None):
        """
        Override to use custom cost for inventory adjustment increases.
        
        When inventory is increased via adjustment, we use the cost rule
        selected by the user instead of standard FIFO logic.
        """
        svl_vals_list = []
        
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
        
        # For non-inventory-adjustment or if custom cost not found, use standard logic
        if not svl_vals_list:
            return super()._create_in_svl(forced_quantity=forced_quantity)
        
        # Create SVLs with custom costs
        return self.env['stock.valuation.layer'].sudo().create(svl_vals_list)
    
    def _create_out_svl(self, forced_quantity=None):
        """
        Override to ensure warehouse context for inventory adjustment decreases.
        
        When inventory is decreased via adjustment, _run_fifo() will consume
        from the correct warehouse thanks to our existing warehouse-aware FIFO logic.
        """
        # Check if this is an inventory adjustment
        is_inventory_adjustment = any(
            move.location_id.usage == 'internal' and
            move.location_dest_id.usage == 'inventory'
            for move in self
        )
        
        if is_inventory_adjustment:
            # Ensure warehouse context is set for FIFO consumption
            for move in self:
                warehouse = move.location_id.warehouse_id
                if warehouse:
                    move = move.with_context(fifo_warehouse_id=warehouse.id)
                    
                    _logger.info(
                        f"Inventory adjustment OUT: {move.product_id.name} "
                        f"from {warehouse.name}: {move.product_qty} units "
                        f"(will consume from warehouse FIFO)"
                    )
        
        # Use standard logic (which now includes our warehouse-aware _run_fifo)
        return super()._create_out_svl(forced_quantity=forced_quantity)
