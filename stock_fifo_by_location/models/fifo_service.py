# -*- coding: utf-8 -*-
"""
FIFO Service and Helper Classes

Provides helper methods for per-location FIFO queue management and cost calculations.
"""

from odoo import models, fields, api
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_round


class FifoService(models.AbstractModel):
    """
    Service model for FIFO-related operations on a per-location basis.
    
    Provides methods to:
    - Calculate COGS based on FIFO queue for a specific location
    - Validate availability in FIFO queue at a location
    - Process layer consumption respecting location constraints
    - Handle shortage scenarios with fallback policy
    """
    
    _name = 'fifo.service'
    _description = 'FIFO Service for Per-Warehouse Cost Calculation'
    
    @api.model
    def get_valuation_layer_queue(self, product_id, warehouse_id, company_id=None):
        """
        Get FIFO queue of valuation layers for product at specific warehouse.
        
        Args:
            product_id: stock.product.product record or id
            warehouse_id: stock.warehouse record or id
            company_id: res.company id (defaults to current company)
            
        Returns:
            Recordset of stock.valuation.layer ordered oldest-first (FIFO)
        """
        if isinstance(product_id, int):
            product_id = self.env['stock.product.product'].browse(product_id)
        
        if isinstance(warehouse_id, int):
            warehouse_id = self.env['stock.warehouse'].browse(warehouse_id)
        
        if not company_id:
            company_id = self.env.company.id
        
        return self.env['stock.valuation.layer']._get_fifo_queue(
            product_id, warehouse_id, company_id
        )
    
    @api.model
    def get_available_qty_at_warehouse(self, product_id, warehouse_id, company_id=None):
        """
        Get total available quantity at warehouse from FIFO queue.
        
        Args:
            product_id: stock.product.product
            warehouse_id: stock.warehouse
            company_id: res.company
            
        Returns:
            float: Available quantity
        """
        if isinstance(product_id, int):
            product_id = self.env['stock.product.product'].browse(product_id)
        
        if isinstance(warehouse_id, int):
            warehouse_id = self.env['stock.warehouse'].browse(warehouse_id)
        
        if not company_id:
            company_id = self.env.company.id
        
        return self.env['stock.valuation.layer']._get_total_available_qty(
            product_id, warehouse_id, company_id
        )
    
    @api.model
    def calculate_fifo_cost(self, product_id, warehouse_id, quantity, company_id=None):
        """
        Calculate COGS for consuming quantity from FIFO queue at warehouse.
        
        Consumes layers in FIFO order (oldest first) and calculates total cost
        and average unit cost for the consumed quantity.
        
        Args:
            product_id: stock.product.product
            warehouse_id: stock.warehouse
            quantity: float - quantity to consume
            company_id: res.company
            
        Returns:
            dict {
                'cost': float - total cost,
                'qty': float - quantity consumed,
                'unit_cost': float - average unit cost,
                'layers': [{
                    'layer_id': int,
                    'qty_consumed': float,
                    'layer_unit_cost': float,
                    'cost': float
                }]
            }
        """
        if isinstance(product_id, int):
            product_id = self.env['stock.product.product'].browse(product_id)
        
        if isinstance(warehouse_id, int):
            warehouse_id = self.env['stock.warehouse'].browse(warehouse_id)
        
        if not company_id:
            company_id = self.env.company.id
        
        queue = self.get_valuation_layer_queue(product_id, warehouse_id, company_id)
        
        if not queue:
            # No layers available - fallback to product standard price
            # This prevents 0.00 valuations in inter-warehouse transfers
            standard_price = product_id.standard_price or 0.0
            return {
                'cost': standard_price * quantity,
                'qty': quantity,
                'unit_cost': standard_price,
                'layers': []
            }
        
        precision = self.env['decimal.precision'].precision_get('Product Price')
        qty_remaining = float_round(quantity, precision_digits=precision)
        total_cost = 0.0
        layers_consumed = []
        
        for layer in queue:
            if float_compare(qty_remaining, 0, precision_digits=precision) <= 0:
                break
            
            # How much can we consume from this layer?
            qty_to_consume = min(
                qty_remaining,
                float_round(layer.quantity, precision_digits=precision)
            )
            
            # Calculate cost for this consumption
            layer_cost = qty_to_consume * layer.unit_cost
            total_cost += layer_cost
            
            layers_consumed.append({
                'layer_id': layer.id,
                'qty_consumed': qty_to_consume,
                'layer_unit_cost': layer.unit_cost,
                'cost': layer_cost,
            })
            
            qty_remaining = float_round(
                qty_remaining - qty_to_consume,
                precision_digits=precision
            )
        
        # Calculate average unit cost
        qty_consumed = float_round(quantity - qty_remaining, precision_digits=precision)
        avg_unit_cost = (
            float_round(total_cost / qty_consumed, precision_digits=precision)
            if qty_consumed > 0
            else 0.0
        )
        
        return {
            'cost': total_cost,
            'qty': qty_consumed,
            'unit_cost': avg_unit_cost,
            'layers': layers_consumed
        }
    
    @api.model
    def validate_warehouse_availability(self, product_id, warehouse_id, quantity, 
                                       allow_fallback=False, company_id=None):
        """
        Validate if warehouse has enough quantity in FIFO queue.
        
        Implements shortage handling policy:
        - If not allow_fallback: raise error if insufficient
        - If allow_fallback: log and optionally pull from other warehouses
        
        Args:
            product_id: stock.product.product
            warehouse_id: stock.warehouse
            quantity: float - quantity needed
            allow_fallback: bool - allow fallback to other warehouses
            company_id: res.company
            
        Returns:
            dict {
                'available': bool - sufficient quantity at warehouse,
                'available_qty': float - available at warehouse,
                'needed_qty': float - quantity needed,
                'shortage': float - shortfall amount,
                'fallback_warehouses': [] - alternative warehouses if available
            }
            
        Raises:
            UserError if allow_fallback=False and shortage exists
        """
        if isinstance(product_id, int):
            product_id = self.env['stock.product.product'].browse(product_id)
        
        if isinstance(warehouse_id, int):
            warehouse_id = self.env['stock.warehouse'].browse(warehouse_id)
        
        if not company_id:
            company_id = self.env.company.id
        
        available_qty = self.get_available_qty_at_warehouse(
            product_id, warehouse_id, company_id
        )
        
        precision = self.env['decimal.precision'].precision_get('Product Price')
        shortage = float_round(quantity - available_qty, precision_digits=precision)
        has_shortage = float_compare(shortage, 0, precision_digits=precision) > 0
        
        result = {
            'available': not has_shortage,
            'available_qty': available_qty,
            'needed_qty': quantity,
            'shortage': max(0, shortage),
            'fallback_warehouses': [],
        }
        
        if has_shortage and not allow_fallback:
            raise UserError(
                f'Insufficient quantity for product {product_id.display_name} '
                f'at warehouse {warehouse_id.display_name}. '
                f'Available: {available_qty}, Needed: {quantity}'
            )
        
        if has_shortage and allow_fallback:
            # Find other warehouses with available inventory
            fallback_whs = self._find_fallback_warehouses(
                product_id, warehouse_id, shortage, company_id
            )
            result['fallback_warehouses'] = fallback_whs
        
        return result
    
    @api.model
    def _find_fallback_warehouses(self, product_id, primary_warehouse, quantity_needed, 
                                  company_id=None):
        """
        Find alternative warehouses with available inventory for fallback.
        
        Args:
            product_id: stock.product.product
            primary_warehouse: stock.warehouse (to exclude)
            quantity_needed: float
            company_id: res.company
            
        Returns:
            list of dicts: [{'warehouse_id': id, 'available_qty': float}, ...]
        """
        if not company_id:
            company_id = self.env.company.id
        
        warehouse_model = self.env['stock.warehouse']
        
        # Find all warehouses in same company
        warehouses = warehouse_model.search([
            ('id', '!=', primary_warehouse.id),
            ('company_id', '=', company_id),
        ])
        
        fallback_results = []
        qty_found = 0
        
        for wh in warehouses:
            available = self.get_available_qty_at_warehouse(
                product_id, wh, company_id
            )
            
            if available > 0:
                fallback_results.append({
                    'warehouse_id': wh.id,
                    'warehouse_name': wh.display_name,
                    'available_qty': available,
                })
                qty_found += available
                
                if qty_found >= quantity_needed:
                    break
        
        return fallback_results
    
    @api.model
    def get_shortage_policy(self):
        """
        Get current shortage handling policy from module settings.
        
        Returns:
            str: 'error' (block) or 'fallback' (allow fallback)
        """
        policy = self.env['ir.config_parameter'].sudo().get_param(
            'stock_fifo_by_location.shortage_policy',
            default='error'
        )
        return policy
    
    @api.model
    def get_enable_location_validation(self):
        """
        Check if location validation is enabled.
        
        Returns:
            bool: True if validation is active
        """
        enabled = self.env['ir.config_parameter'].sudo().get_param(
            'stock_fifo_by_location.enable_validation',
            default='True'
        )
        return enabled.lower() == 'true'
    
    @api.model
    def get_landed_cost_at_warehouse(self, product_id, warehouse_id, company_id=None):
        """
        Get total landed cost for a product at a specific warehouse.
        
        Sums all landed costs from all valuation layers at that warehouse.
        
        Args:
            product_id: stock.product.product
            warehouse_id: stock.warehouse
            company_id: res.company
            
        Returns:
            float: Total landed cost at warehouse
        """
        if isinstance(product_id, int):
            product_id = self.env['stock.product.product'].browse(product_id)
        
        if isinstance(warehouse_id, int):
            warehouse_id = self.env['stock.warehouse'].browse(warehouse_id)
        
        if not company_id:
            company_id = self.env.company.id
        
        return self.env['stock.valuation.layer'].get_landed_cost_at_warehouse(
            product_id, warehouse_id, company_id
        )
    
    @api.model
    def get_unit_landed_cost_at_warehouse(self, product_id, warehouse_id, company_id=None):
        """
        Get average unit landed cost for a product at a warehouse.
        
        Args:
            product_id: stock.product.product
            warehouse_id: stock.warehouse
            company_id: res.company
            
        Returns:
            float: Unit landed cost (landed_cost_value / qty_available)
        """
        if isinstance(product_id, int):
            product_id = self.env['stock.product.product'].browse(product_id)
        
        if isinstance(warehouse_id, int):
            warehouse_id = self.env['stock.warehouse'].browse(warehouse_id)
        
        if not company_id:
            company_id = self.env.company.id
        
        total_lc = self.get_landed_cost_at_warehouse(product_id, warehouse_id, company_id)
        available_qty = self.get_available_qty_at_warehouse(product_id, warehouse_id, company_id)
        
        precision = self.env['decimal.precision'].precision_get('Product Price')
        
        if available_qty and float_compare(available_qty, 0, precision_digits=precision) > 0:
            return float_round(
                total_lc / available_qty,
                precision_digits=precision
            )
        return 0.0
    
    @api.model
    def calculate_fifo_cost_with_landed_cost(self, product_id, warehouse_id, quantity, 
                                             company_id=None):
        """
        Calculate COGS including landed costs for consuming quantity from FIFO queue.
        
        This method extends calculate_fifo_cost to include landed costs that were
        allocated to the consumed layers.
        
        Args:
            product_id: stock.product.product
            warehouse_id: stock.warehouse
            quantity: float - quantity to consume
            company_id: res.company
            
        Returns:
            dict {
                'cost': float - total cost including landed costs,
                'qty': float - quantity consumed,
                'unit_cost': float - average unit cost with landed costs,
                'landed_cost': float - total landed cost portion,
                'layers': [{
                    'layer_id': int,
                    'qty_consumed': float,
                    'layer_unit_cost': float,
                    'layer_landed_cost': float,
                    'cost': float (including landed cost)
                }]
            }
        """
        if isinstance(product_id, int):
            product_id = self.env['stock.product.product'].browse(product_id)
        
        if isinstance(warehouse_id, int):
            warehouse_id = self.env['stock.warehouse'].browse(warehouse_id)
        
        if not company_id:
            company_id = self.env.company.id
        
        # Get base FIFO cost
        base_cost_result = self.calculate_fifo_cost(
            product_id, warehouse_id, quantity, company_id
        )
        
        # If no cost was calculated (empty queue), use standard price as fallback
        if base_cost_result['cost'] == 0.0 and base_cost_result['qty'] > 0:
            standard_price = product_id.standard_price or 0.0
            return {
                'cost': standard_price * quantity,
                'qty': quantity,
                'unit_cost': standard_price,
                'landed_cost': 0.0,
                'layers': []
            }
        
        # Now add landed costs for consumed layers
        lc_model = self.env['stock.valuation.layer.landed.cost']
        precision = self.env['decimal.precision'].precision_get('Product Price')
        total_landed_cost = 0.0
        
        # Handle both recordset and id for warehouse_id
        wh_id = warehouse_id.id if hasattr(warehouse_id, 'id') else warehouse_id
        
        # Update each layer with its landed cost
        for layer_info in base_cost_result['layers']:
            layer_id = layer_info['layer_id']
            qty_consumed = layer_info['qty_consumed']
            
            # Get unit landed cost for this layer at this warehouse
            lc_records = lc_model.search([
                ('valuation_layer_id', '=', layer_id),
                ('warehouse_id', '=', wh_id),
            ])
            
            unit_lc = 0.0
            if lc_records:
                unit_lc = lc_records[0].unit_landed_cost
            
            # Calculate landed cost for consumed quantity from this layer
            layer_landed_cost = float_round(
                qty_consumed * unit_lc,
                precision_digits=precision
            )
            
            layer_info['layer_landed_cost'] = layer_landed_cost
            layer_info['cost'] = float_round(
                layer_info['cost'] + layer_landed_cost,
                precision_digits=precision
            )
            
            total_landed_cost += layer_landed_cost
        
        # Update totals
        total_cost_with_lc = float_round(
            base_cost_result['cost'] + total_landed_cost,
            precision_digits=precision
        )
        
        qty_consumed = base_cost_result['qty']
        avg_unit_cost = (
            float_round(total_cost_with_lc / qty_consumed, precision_digits=precision)
            if qty_consumed > 0
            else 0.0
        )
        
        return {
            'cost': total_cost_with_lc,
            'qty': qty_consumed,
            'unit_cost': avg_unit_cost,
            'landed_cost': total_landed_cost,
            'layers': base_cost_result['layers']
        }


class ConfigParameter(models.Model):
    """
    Configuration parameters for stock_fifo_by_location module.
    
    Provides settings for:
    - Shortage handling policy (error vs fallback)
    - Location validation enable/disable
    - Debug/logging options
    """
    
    _name = 'config.parameter'
    _inherit = 'ir.config_parameter'
    
    # These are just markers - actual params stored in ir.config_parameter
    # Examples:
    # stock_fifo_by_location.shortage_policy -> 'error' or 'fallback'
    # stock_fifo_by_location.enable_validation -> 'True' or 'False'
    # stock_fifo_by_location.debug_mode -> 'True' or 'False'
