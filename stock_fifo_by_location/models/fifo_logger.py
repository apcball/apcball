# -*- coding: utf-8 -*-
"""
Logging Utilities for FIFO by Location Module

Centralized logging with configurable levels and formatting.
"""

import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


class FifoLogger:
    """
    Centralized logger for FIFO operations with configurable verbosity.
    
    Usage:
        logger = FifoLogger.get_logger(env, 'stock.move')
        logger.fifo_operation('Transfer', product, warehouse, quantity)
    """
    
    # Emoji mapping for consistent visual feedback
    EMOJI = {
        'success': '✅',
        'info': 'ℹ️',
        'warning': '⚠️',
        'error': '❌',
        'debug': '🔍',
        'money': '💰',
        'warehouse': '🏭',
        'product': '📦',
        'transfer': '🔄',
    }
    
    def __init__(self, env, model_name):
        """
        Initialize logger for a specific model.
        
        Args:
            env: Odoo environment
            model_name: Name of the model (e.g., 'stock.move')
        """
        self.env = env
        self.model_name = model_name
        self._logger = logging.getLogger(f'odoo.addons.stock_fifo_by_location.{model_name}')
        self._load_config()
    
    def _load_config(self):
        """Load logging configuration from system parameters."""
        try:
            params = self.env['ir.config_parameter'].sudo()
            self.verbose = params.get_param(
                'stock_fifo_by_location.verbose_logging',
                default='False'
            ).lower() == 'true'
            
            self.log_fifo_operations = params.get_param(
                'stock_fifo_by_location.log_fifo_operations',
                default='True'
            ).lower() == 'true'
            
            self.log_warehouse_operations = params.get_param(
                'stock_fifo_by_location.log_warehouse_operations',
                default='True'
            ).lower() == 'true'
        except Exception:
            # Fallback if config not available (e.g., during module install)
            self.verbose = False
            self.log_fifo_operations = True
            self.log_warehouse_operations = True
    
    @classmethod
    def get_logger(cls, env, model_name):
        """
        Factory method to get logger instance.
        
        Args:
            env: Odoo environment
            model_name: Model name
            
        Returns:
            FifoLogger instance
        """
        return cls(env, model_name)
    
    def _format_message(self, emoji_key, message, **kwargs):
        """Format log message with emoji and context."""
        emoji = self.EMOJI.get(emoji_key, '')
        context_str = ' '.join(f'{k}={v}' for k, v in kwargs.items())
        
        if context_str:
            return f"{emoji} [{self.model_name}] {message} ({context_str})"
        return f"{emoji} [{self.model_name}] {message}"
    
    def fifo_operation(self, operation, product, warehouse, quantity, **kwargs):
        """
        Log FIFO operation.
        
        Args:
            operation: Operation type (e.g., 'Consume', 'Create', 'Transfer')
            product: Product name or record
            warehouse: Warehouse name or record
            quantity: Quantity
            **kwargs: Additional context (cost, unit_cost, etc.)
        """
        if not self.log_fifo_operations:
            return
        
        product_name = product.display_name if hasattr(product, 'display_name') else str(product)
        warehouse_name = warehouse.name if hasattr(warehouse, 'name') else str(warehouse)
        
        msg = f"FIFO {operation}: {product_name} @ {warehouse_name}, qty={quantity:.2f}"
        
        if self.verbose or kwargs:
            self._logger.debug(self._format_message('debug', msg, **kwargs))
        else:
            self._logger.debug(msg)
    
    def warehouse_operation(self, operation, source_wh, dest_wh, product, quantity, **kwargs):
        """
        Log warehouse operation (transfer, receipt, delivery).
        
        Args:
            operation: Operation type
            source_wh: Source warehouse
            dest_wh: Destination warehouse
            product: Product
            quantity: Quantity
            **kwargs: Additional context
        """
        if not self.log_warehouse_operations:
            return
        
        product_name = product.display_name if hasattr(product, 'display_name') else str(product)
        source_name = source_wh.name if source_wh and hasattr(source_wh, 'name') else 'None'
        dest_name = dest_wh.name if dest_wh and hasattr(dest_wh, 'name') else 'None'
        
        msg = f"{operation}: {product_name}, {source_name} → {dest_name}, qty={quantity:.2f}"
        
        if self.verbose:
            self._logger.info(self._format_message('transfer', msg, **kwargs))
        else:
            self._logger.debug(msg)
    
    def cost_calculation(self, product, warehouse, cost_type, amount, **kwargs):
        """
        Log cost calculation.
        
        Args:
            product: Product
            warehouse: Warehouse
            cost_type: Type of cost (FIFO, Standard, Landed)
            amount: Cost amount
            **kwargs: Additional context
        """
        product_name = product.display_name if hasattr(product, 'display_name') else str(product)
        warehouse_name = warehouse.name if hasattr(warehouse, 'name') else str(warehouse)
        
        msg = f"{cost_type} Cost: {product_name} @ {warehouse_name} = {amount:.4f}"
        
        if self.verbose:
            self._logger.debug(self._format_message('money', msg, **kwargs))
    
    def layer_created(self, layer_type, warehouse, product, quantity, value, **kwargs):
        """
        Log valuation layer creation.
        
        Args:
            layer_type: 'positive' or 'negative'
            warehouse: Warehouse
            product: Product
            quantity: Quantity
            value: Value
            **kwargs: Additional context
        """
        if not self.log_fifo_operations:
            return
        
        warehouse_name = warehouse.name if hasattr(warehouse, 'name') else str(warehouse)
        product_name = product.display_name if hasattr(product, 'display_name') else str(product)
        
        emoji = 'success' if layer_type == 'positive' else 'info'
        msg = f"Created {layer_type.upper()} layer: {product_name} @ {warehouse_name}, qty={quantity:.2f}, value={value:.4f}"
        
        if self.verbose:
            self._logger.info(self._format_message(emoji, msg, **kwargs))
        else:
            self._logger.debug(msg)
    
    def shortage(self, product, warehouse, needed, available, **kwargs):
        """
        Log shortage situation.
        
        Args:
            product: Product
            warehouse: Warehouse
            needed: Quantity needed
            available: Quantity available
            **kwargs: Additional context
        """
        product_name = product.display_name if hasattr(product, 'display_name') else str(product)
        warehouse_name = warehouse.name if hasattr(warehouse, 'name') else str(warehouse)
        
        shortage = needed - available
        msg = f"Shortage: {product_name} @ {warehouse_name}, needed={needed:.2f}, available={available:.2f}, shortage={shortage:.2f}"
        
        self._logger.warning(self._format_message('warning', msg, **kwargs))
    
    def error(self, operation, error_msg, **kwargs):
        """
        Log error.
        
        Args:
            operation: Operation that failed
            error_msg: Error message
            **kwargs: Additional context
        """
        msg = f"Error in {operation}: {error_msg}"
        self._logger.error(self._format_message('error', msg, **kwargs))
    
    def debug(self, message, **kwargs):
        """Log debug message."""
        if self.verbose:
            self._logger.debug(self._format_message('debug', message, **kwargs))
    
    def info(self, message, **kwargs):
        """Log info message."""
        self._logger.info(self._format_message('info', message, **kwargs))
    
    def warning(self, message, **kwargs):
        """Log warning message."""
        self._logger.warning(self._format_message('warning', message, **kwargs))


def log_performance(func):
    """
    Decorator to log function performance.
    
    Usage:
        @log_performance
        def my_function(self):
            ...
    """
    import time
    from functools import wraps
    
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        duration = time.time() - start
        
        # Only log if takes more than 1 second
        if duration > 1.0:
            _logger.info(f"⏱️ Performance: {func.__name__} took {duration:.2f}s")
        elif duration > 0.5:
            _logger.debug(f"⏱️ Performance: {func.__name__} took {duration:.2f}s")
        
        return result
    
    return wrapper
