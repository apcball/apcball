# -*- coding: utf-8 -*-
"""
FIFO Concurrency Control Utilities

Provides decorators and utilities for handling race conditions in FIFO operations.
Critical operations like FIFO queue consumption, remaining_qty updates, and layer
creation require proper locking to prevent data inconsistencies in concurrent scenarios.
"""

from odoo import models, api
from odoo.exceptions import UserError
from odoo.tools import float_compare
import logging
import functools
import time
from psycopg2 import OperationalError, errorcodes

_logger = logging.getLogger(__name__)


class FifoConcurrencyMixin(models.AbstractModel):
    """
    Mixin providing concurrency control utilities for FIFO operations.
    
    Key Features:
    - Database-level row locking (SELECT FOR UPDATE)
    - Deadlock retry logic with exponential backoff
    - Transaction isolation management
    - Concurrent modification detection
    """
    
    _name = 'fifo.concurrency.mixin'
    _description = 'FIFO Concurrency Control Mixin'
    
    
    # ========== DECORATORS ==========
    
    @staticmethod
    def with_fifo_lock(lock_timeout=10000):
        """
        Decorator to execute method with PostgreSQL row-level locks.
        
        Acquires SELECT FOR UPDATE NOWAIT locks on FIFO queue records
        to prevent concurrent modifications during FIFO consumption.
        
        Args:
            lock_timeout: Timeout in milliseconds (default 10 seconds)
        
        Usage:
            @with_fifo_lock(lock_timeout=5000)
            def consume_fifo_layers(self, product, warehouse, quantity):
                # Critical FIFO consumption logic
                pass
        """
        def decorator(func):
            @functools.wraps(func)
            def wrapper(self, *args, **kwargs):
                # Set PostgreSQL lock timeout for this transaction
                old_timeout = None
                try:
                    # Store old timeout
                    self.env.cr.execute("SHOW lock_timeout")
                    old_timeout = self.env.cr.fetchone()[0]
                    
                    # Set new timeout
                    self.env.cr.execute(f"SET LOCAL lock_timeout = '{lock_timeout}ms'")
                    
                    _logger.debug(f"🔒 Acquired FIFO lock for {func.__name__}, timeout={lock_timeout}ms")
                    
                    # Execute the wrapped function
                    result = func(self, *args, **kwargs)
                    
                    return result
                    
                except OperationalError as e:
                    if e.pgcode == errorcodes.LOCK_NOT_AVAILABLE:
                        _logger.warning(
                            f"⚠️ Lock timeout in {func.__name__}: Another process is modifying FIFO queue. "
                            f"Timeout: {lock_timeout}ms"
                        )
                        raise UserError(
                            "ระบบกำลังประมวลผล FIFO อยู่\n"
                            "กรุณารอสักครู่แล้วลองใหม่อีกครั้ง\n\n"
                            "หากปัญหายังคงเกิดขึ้น ติดต่อผู้ดูแลระบบ"
                        )
                    raise
                finally:
                    # Restore old timeout
                    if old_timeout:
                        self.env.cr.execute(f"SET LOCAL lock_timeout = '{old_timeout}'")
            
            return wrapper
        return decorator
    
    
    @staticmethod
    def with_retry_on_deadlock(max_retries=3, base_delay=0.1):
        """
        Decorator to retry method on deadlock with exponential backoff.
        
        PostgreSQL deadlocks can occur when multiple transactions try to
        update the same records in different orders. This decorator automatically
        retries with increasing delays.
        
        Args:
            max_retries: Maximum number of retry attempts (default 3)
            base_delay: Base delay in seconds, doubles each retry (default 0.1s)
        
        Usage:
            @with_retry_on_deadlock(max_retries=5, base_delay=0.2)
            def update_fifo_layers(self, layers, values):
                # Update logic that might deadlock
                pass
        """
        def decorator(func):
            @functools.wraps(func)
            def wrapper(self, *args, **kwargs):
                attempt = 0
                last_error = None
                
                while attempt < max_retries:
                    try:
                        # Execute the wrapped function
                        return func(self, *args, **kwargs)
                        
                    except OperationalError as e:
                        last_error = e
                        
                        # Check if it's a deadlock
                        if e.pgcode == errorcodes.DEADLOCK_DETECTED:
                            attempt += 1
                            
                            if attempt >= max_retries:
                                _logger.error(
                                    f"❌ Deadlock in {func.__name__} after {max_retries} retries"
                                )
                                raise UserError(
                                    "ระบบไม่สามารถประมวลผล FIFO ได้\n"
                                    "มีการใช้งานพร้อมกันมากเกินไป\n\n"
                                    "กรุณาลองใหม่อีกครั้งในภายหลัง"
                                )
                            
                            # Calculate exponential backoff delay
                            delay = base_delay * (2 ** (attempt - 1))
                            
                            _logger.warning(
                                f"⚠️ Deadlock detected in {func.__name__}, "
                                f"retry {attempt}/{max_retries} after {delay:.2f}s"
                            )
                            
                            # Rollback the transaction
                            self.env.cr.rollback()
                            
                            # Wait before retry
                            time.sleep(delay)
                        else:
                            # Not a deadlock, re-raise immediately
                            raise
                
                # Should never reach here, but just in case
                if last_error:
                    raise last_error
            
            return wrapper
        return decorator
    
    
    @staticmethod
    def with_serializable_transaction():
        """
        Decorator to execute method in SERIALIZABLE isolation level.
        
        SERIALIZABLE is the strictest isolation level, preventing all
        concurrency anomalies but may cause more serialization failures.
        Use for critical operations where data consistency is paramount.
        
        Usage:
            @with_serializable_transaction()
            def critical_fifo_operation(self):
                # Critical logic requiring serializable isolation
                pass
        """
        def decorator(func):
            @functools.wraps(func)
            def wrapper(self, *args, **kwargs):
                # Get current isolation level
                self.env.cr.execute("SHOW transaction_isolation")
                old_isolation = self.env.cr.fetchone()[0]
                
                try:
                    # Set SERIALIZABLE isolation
                    self.env.cr.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
                    
                    _logger.debug(f"🔐 Using SERIALIZABLE isolation for {func.__name__}")
                    
                    # Execute the wrapped function
                    result = func(self, *args, **kwargs)
                    
                    return result
                    
                except OperationalError as e:
                    if e.pgcode == errorcodes.SERIALIZATION_FAILURE:
                        _logger.warning(
                            f"⚠️ Serialization failure in {func.__name__}: "
                            "Concurrent modification detected"
                        )
                        # Rollback and let retry decorator handle it
                        self.env.cr.rollback()
                        raise
                    raise
            
            return wrapper
        return decorator
    
    
    # ========== LOCKING METHODS ==========
    
    @api.model
    def _lock_fifo_queue(self, product_id, warehouse_id, company_id, nowait=True):
        """
        Acquire row-level locks on FIFO queue for product at warehouse.
        
        Locks all valuation layers with remaining_qty > 0 to prevent
        concurrent modifications during FIFO consumption.
        
        Args:
            product_id: stock.product.product or id
            warehouse_id: stock.warehouse or id
            company_id: res.company id
            nowait: If True, fail immediately if lock unavailable (default True)
                   If False, wait for lock (may block)
        
        Returns:
            Recordset of locked stock.valuation.layer records
        
        Raises:
            UserError: If lock cannot be acquired (when nowait=True)
        """
        # Handle both recordset and id
        prod_id = product_id.id if hasattr(product_id, 'id') else product_id
        wh_id = warehouse_id.id if hasattr(warehouse_id, 'id') else warehouse_id
        
        # Build query with FOR UPDATE
        nowait_clause = "NOWAIT" if nowait else ""
        
        query = f"""
            SELECT id FROM stock_valuation_layer
            WHERE product_id = %s
              AND warehouse_id = %s
              AND company_id = %s
              AND remaining_qty > 0
            ORDER BY create_date ASC, id ASC
            FOR UPDATE {nowait_clause}
        """
        
        try:
            self.env.cr.execute(query, (prod_id, wh_id, company_id))
            layer_ids = [row[0] for row in self.env.cr.fetchall()]
            
            if layer_ids:
                _logger.debug(
                    f"🔒 Locked {len(layer_ids)} FIFO layers for "
                    f"product_id={prod_id}, warehouse_id={wh_id}"
                )
            
            return self.env['stock.valuation.layer'].browse(layer_ids)
            
        except OperationalError as e:
            if e.pgcode == errorcodes.LOCK_NOT_AVAILABLE:
                _logger.warning(
                    f"⚠️ Cannot lock FIFO queue: product_id={prod_id}, warehouse_id={wh_id}"
                )
                raise UserError(
                    "ไม่สามารถล็อก FIFO queue ได้\n"
                    "มีผู้ใช้อื่นกำลังประมวลผลสินค้านี้อยู่\n\n"
                    "กรุณารอสักครู่แล้วลองใหม่อีกครั้ง"
                )
            raise
    
    
    @api.model
    def _lock_valuation_layer(self, layer_id, nowait=True):
        """
        Acquire row-level lock on specific valuation layer.
        
        Args:
            layer_id: stock.valuation.layer or id
            nowait: If True, fail immediately if lock unavailable
        
        Returns:
            stock.valuation.layer record (locked)
        """
        # Handle both recordset and id
        l_id = layer_id.id if hasattr(layer_id, 'id') else layer_id
        
        nowait_clause = "NOWAIT" if nowait else ""
        
        query = f"""
            SELECT id FROM stock_valuation_layer
            WHERE id = %s
            FOR UPDATE {nowait_clause}
        """
        
        try:
            self.env.cr.execute(query, (l_id,))
            result = self.env.cr.fetchone()
            
            if result:
                _logger.debug(f"🔒 Locked valuation layer {l_id}")
                return self.env['stock.valuation.layer'].browse(result[0])
            else:
                raise UserError(f"Valuation layer {l_id} not found")
                
        except OperationalError as e:
            if e.pgcode == errorcodes.LOCK_NOT_AVAILABLE:
                _logger.warning(f"⚠️ Cannot lock valuation layer {l_id}")
                raise UserError(
                    "ไม่สามารถล็อก Valuation Layer ได้\n"
                    "มีผู้ใช้อื่นกำลังประมวลผลอยู่"
                )
            raise
    
    
    # ========== CONCURRENCY VALIDATION ==========
    
    @api.model
    def _validate_no_concurrent_modification(self, layer, expected_remaining_qty):
        """
        Validate that layer hasn't been modified by concurrent transaction.
        
        Checks if remaining_qty matches expected value. If not, another
        transaction has modified the layer and current transaction should abort.
        
        Args:
            layer: stock.valuation.layer record
            expected_remaining_qty: Expected remaining_qty value
        
        Raises:
            UserError: If concurrent modification detected
        """
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        
        # Refresh from database to get latest value
        layer.invalidate_recordset(['remaining_qty', 'remaining_value'])
        
        if float_compare(layer.remaining_qty, expected_remaining_qty, precision_digits=precision) != 0:
            _logger.warning(
                f"⚠️ Concurrent modification detected on layer {layer.id}: "
                f"expected remaining_qty={expected_remaining_qty:.4f}, "
                f"actual={layer.remaining_qty:.4f}"
            )
            raise UserError(
                "ตรวจพบการแก้ไขพร้อมกัน!\n"
                "ข้อมูล FIFO ถูกเปลี่ยนแปลงโดยผู้ใช้อื่น\n\n"
                "กรุณาลองทำรายการใหม่อีกครั้ง"
            )
    
    
    @api.model
    def _check_for_race_condition(self, product_id, warehouse_id, company_id):
        """
        Check if there's potential race condition in FIFO queue.
        
        Returns True if there are pending uncommitted transactions
        that might affect the FIFO queue.
        
        Args:
            product_id: stock.product.product or id
            warehouse_id: stock.warehouse or id  
            company_id: res.company id
        
        Returns:
            bool: True if race condition possible, False otherwise
        """
        # Handle both recordset and id
        prod_id = product_id.id if hasattr(product_id, 'id') else product_id
        wh_id = warehouse_id.id if hasattr(warehouse_id, 'id') else warehouse_id
        
        # Check for locks on FIFO queue records
        query = """
            SELECT COUNT(*)
            FROM pg_locks l
            JOIN stock_valuation_layer svl ON svl.id = l.objid
            WHERE l.locktype = 'tuple'
              AND l.granted = false
              AND svl.product_id = %s
              AND svl.warehouse_id = %s
              AND svl.company_id = %s
              AND svl.remaining_qty > 0
        """
        
        try:
            self.env.cr.execute(query, (prod_id, wh_id, company_id))
            lock_count = self.env.cr.fetchone()[0]
            
            if lock_count > 0:
                _logger.warning(
                    f"⚠️ Detected {lock_count} lock(s) on FIFO queue: "
                    f"product_id={prod_id}, warehouse_id={wh_id}"
                )
                return True
            
            return False
            
        except Exception as e:
            _logger.error(f"Error checking race condition: {e}")
            # Assume no race condition on error
            return False


class FifoConcurrencyHelper(models.AbstractModel):
    """
    Helper methods for safe concurrent FIFO operations.
    """
    
    _name = 'fifo.concurrency.helper'
    _description = 'FIFO Concurrency Helper Methods'
    
    
    @api.model
    def safe_consume_fifo_layers(self, layers, quantity_to_consume):
        """
        Safely consume FIFO layers with proper locking and validation.
        
        This method:
        1. Locks all layers in order (to prevent deadlock)
        2. Validates no concurrent modifications
        3. Updates remaining_qty atomically
        4. Returns consumed value
        
        Args:
            layers: Recordset of stock.valuation.layer (ordered FIFO)
            quantity_to_consume: float - quantity to consume (positive)
        
        Returns:
            dict: {
                'consumed_value': Total value consumed,
                'consumed_qty': Actual quantity consumed,
                'updated_layers': List of updated layer info
            }
        """
        if not layers:
            return {
                'consumed_value': 0.0,
                'consumed_qty': 0.0,
                'updated_layers': []
            }
        
        precision_qty = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        precision_price = self.env['decimal.precision'].precision_get('Product Price')
        
        # Lock all layers in FIFO order to prevent deadlock
        layer_ids = tuple(layers.ids)
        query = """
            SELECT id, remaining_qty, remaining_value
            FROM stock_valuation_layer
            WHERE id IN %s
            ORDER BY create_date ASC, id ASC
            FOR UPDATE
        """
        
        self.env.cr.execute(query, (layer_ids,))
        locked_layers = {row[0]: {'remaining_qty': row[1], 'remaining_value': row[2]} 
                        for row in self.env.cr.fetchall()}
        
        _logger.debug(f"🔒 Locked {len(locked_layers)} layers for consumption")
        
        # Consume layers in FIFO order
        total_consumed_value = 0.0
        total_consumed_qty = 0.0
        updated_layers = []
        qty_remaining = quantity_to_consume
        
        for layer in layers:
            if float_compare(qty_remaining, 0, precision_digits=precision_qty) <= 0:
                break
            
            # Get locked values
            locked_data = locked_layers.get(layer.id)
            if not locked_data:
                continue
            
            remaining_qty = locked_data['remaining_qty']
            remaining_value = locked_data['remaining_value']
            
            if float_compare(remaining_qty, 0, precision_digits=precision_qty) <= 0:
                continue
            
            # Calculate consumption
            qty_to_take = min(qty_remaining, remaining_qty)
            unit_cost = remaining_value / remaining_qty if remaining_qty > 0 else 0
            value_to_take = qty_to_take * unit_cost
            
            new_remaining_qty = remaining_qty - qty_to_take
            new_remaining_value = remaining_value - value_to_take
            
            # Ensure no negative due to rounding
            if new_remaining_qty < 0:
                new_remaining_qty = 0.0
            if new_remaining_value < 0:
                new_remaining_value = 0.0
            
            # Update layer atomically
            layer.write({
                'remaining_qty': new_remaining_qty,
                'remaining_value': new_remaining_value,
            })
            
            # Track update
            updated_layers.append({
                'layer_id': layer.id,
                'qty_consumed': qty_to_take,
                'value_consumed': value_to_take,
                'unit_cost': unit_cost,
                'new_remaining_qty': new_remaining_qty,
                'new_remaining_value': new_remaining_value,
            })
            
            total_consumed_value += value_to_take
            total_consumed_qty += qty_to_take
            qty_remaining -= qty_to_take
            
            _logger.debug(
                f"  📥 Consumed layer {layer.id}: "
                f"qty={qty_to_take:.4f} @ {unit_cost:.4f} = {value_to_take:.4f}, "
                f"new_remaining={new_remaining_qty:.4f}"
            )
        
        return {
            'consumed_value': total_consumed_value,
            'consumed_qty': total_consumed_qty,
            'updated_layers': updated_layers,
            'shortage_qty': qty_remaining if qty_remaining > 0 else 0.0,
        }
    
    
    @api.model
    def safe_create_valuation_layer(self, vals, check_concurrency=True):
        """
        Safely create valuation layer with concurrency check.
        
        Args:
            vals: dict - values for layer creation
            check_concurrency: bool - whether to check for race conditions
        
        Returns:
            stock.valuation.layer record
        """
        if check_concurrency and vals.get('product_id') and vals.get('warehouse_id'):
            # Check if another transaction is creating layers for same product/warehouse
            concurrency_mixin = self.env['fifo.concurrency.mixin']
            has_race = concurrency_mixin._check_for_race_condition(
                vals['product_id'],
                vals['warehouse_id'],
                vals.get('company_id', self.env.company.id)
            )
            
            if has_race:
                _logger.warning(
                    f"⚠️ Potential race condition detected when creating layer for "
                    f"product_id={vals['product_id']}, warehouse_id={vals['warehouse_id']}"
                )
        
        # Create layer
        layer = self.env['stock.valuation.layer'].create(vals)
        
        _logger.debug(f"✅ Created valuation layer {layer.id} safely")
        
        return layer
