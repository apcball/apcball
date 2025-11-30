# -*- coding: utf-8 -*-
"""
FIFO Base Mixin

Common functionality for FIFO operations to reduce code duplication.
"""

from odoo import models, api
from odoo.tools import float_round, float_compare


class FifoBaseMixin(models.AbstractModel):
    """
    Base mixin for FIFO operations.
    
    Provides common methods used across stock.move, stock.valuation.layer, etc.
    """
    
    _name = 'fifo.base.mixin'
    _description = 'FIFO Base Mixin'
    
    @api.model
    def _get_warehouse_from_location(self, location):
        """
        Get warehouse from location.
        
        Args:
            location: stock.location record
            
        Returns:
            stock.warehouse or None
        """
        if not location:
            return None
        return location.warehouse_id if hasattr(location, 'warehouse_id') else None
    
    @api.model
    def _get_product_uom_name(self, product):
        """
        Get product UOM name safely.
        
        Args:
            product: product.product record
            
        Returns:
            str: UOM name or 'Unit'
        """
        try:
            return product.uom_id.name if product and product.uom_id else 'Unit'
        except Exception:
            return 'Unit'
    
    @api.model
    def _is_fifo_product(self, product):
        """
        Check if product uses FIFO costing.
        
        Args:
            product: product.product record
            
        Returns:
            bool
        """
        if not product or product.type != 'product':
            return False
        return product.categ_id.property_cost_method == 'fifo'
    
    @api.model
    def _get_precision(self, precision_type='Product Price'):
        """
        Get decimal precision.
        
        Args:
            precision_type: Type of precision
            
        Returns:
            int: Number of decimal places
        """
        return self.env['decimal.precision'].precision_get(precision_type)
    
    @api.model
    def _round_value(self, value, precision_type='Product Price'):
        """
        Round value to precision.
        
        Args:
            value: Value to round
            precision_type: Precision type
            
        Returns:
            float: Rounded value
        """
        precision = self._get_precision(precision_type)
        return float_round(value, precision_digits=precision)
    
    @api.model
    def _compare_floats(self, value1, value2, precision_type='Product Unit of Measure'):
        """
        Compare two float values with precision.
        
        Args:
            value1: First value
            value2: Second value
            precision_type: Precision type
            
        Returns:
            int: -1 (less), 0 (equal), 1 (greater)
        """
        precision = self._get_precision(precision_type)
        return float_compare(value1, value2, precision_digits=precision)
    
    @api.model
    def _is_inter_warehouse_move(self, source_wh, dest_wh):
        """
        Check if move is inter-warehouse.
        
        Args:
            source_wh: Source warehouse
            dest_wh: Destination warehouse
            
        Returns:
            bool
        """
        if not (source_wh and dest_wh):
            return False
        
        source_id = source_wh.id if hasattr(source_wh, 'id') else source_wh
        dest_id = dest_wh.id if hasattr(dest_wh, 'id') else dest_wh
        
        return source_id != dest_id
    
    @api.model
    def _get_config_param(self, key, default=None):
        """
        Get configuration parameter safely.
        
        Args:
            key: Parameter key
            default: Default value
            
        Returns:
            Value or default
        """
        try:
            return self.env['ir.config_parameter'].sudo().get_param(key, default=default)
        except Exception:
            return default
    
    @api.model
    def _get_config_bool(self, key, default=False):
        """
        Get boolean configuration parameter.
        
        Args:
            key: Parameter key
            default: Default boolean value
            
        Returns:
            bool
        """
        value = self._get_config_param(key, default=str(default))
        return str(value).lower() in ('true', '1', 'yes')
    
    @api.model
    def _get_config_float(self, key, default=0.0):
        """
        Get float configuration parameter.
        
        Args:
            key: Parameter key
            default: Default float value
            
        Returns:
            float
        """
        try:
            value = self._get_config_param(key, default=str(default))
            return float(value)
        except (ValueError, TypeError):
            return default
    
    @api.model
    def _get_config_int(self, key, default=0):
        """
        Get integer configuration parameter.
        
        Args:
            key: Parameter key
            default: Default integer value
            
        Returns:
            int
        """
        try:
            value = self._get_config_param(key, default=str(default))
            return int(value)
        except (ValueError, TypeError):
            return default
    
    @api.model
    def _format_quantity(self, quantity, product=None):
        """
        Format quantity for display.
        
        Args:
            quantity: Quantity value
            product: Optional product for UOM
            
        Returns:
            str: Formatted quantity
        """
        if product:
            uom = self._get_product_uom_name(product)
            return f"{quantity:.2f} {uom}"
        return f"{quantity:.2f}"
    
    @api.model
    def _format_cost(self, cost):
        """
        Format cost for display.
        
        Args:
            cost: Cost value
            
        Returns:
            str: Formatted cost
        """
        return f"{cost:.4f}"
    
    @api.model
    def _safe_divide(self, numerator, denominator, default=0.0):
        """
        Safe division with default value.
        
        Args:
            numerator: Numerator
            denominator: Denominator
            default: Default value if division fails
            
        Returns:
            float: Result or default
        """
        precision = self._get_precision('Product Price')
        if float_compare(denominator, 0, precision_digits=precision) == 0:
            return default
        return numerator / denominator
    
    @api.model
    def _ensure_positive(self, value):
        """
        Ensure value is not negative.
        
        Args:
            value: Value to check
            
        Returns:
            float: Max(0, value)
        """
        return max(0.0, value)
    
    def _get_logger(self):
        """
        Get logger instance for this model.
        
        Returns:
            FifoLogger instance
        """
        from .fifo_logger import FifoLogger
        return FifoLogger.get_logger(self.env, self._name)
