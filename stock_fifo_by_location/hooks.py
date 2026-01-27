# -*- coding: utf-8 -*-
"""
Post-install hook for stock_fifo_by_location module

This hook will automatically fix existing valuation data when installing the module
on an existing database with historical stock data.
"""

import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """
    Post-installation hook to fix existing valuation data.
    
    This will be called automatically after module installation.
    It performs three operations:
    1. Fix NULL remaining_value in negative layers
    2. Recalculate remaining_qty per warehouse using FIFO
    3. Fix value mismatch (qty=0 but value≠0)
    
    Args:
        env: Odoo environment with SUPERUSER_ID
    """
    
    _logger.info("="*80)
    _logger.info("Running post-install hook for stock_fifo_by_location")
    _logger.info("="*80)
    
    try:
        # Step 1: Fix NULL remaining values
        _logger.info("Step 1: Fixing NULL remaining values...")
        null_fixed = _fix_null_remaining_values(env)
        _logger.info(f"✅ Fixed {null_fixed} layers with NULL remaining_value")
        
        # Step 2: Fix negative remaining
        _logger.info("Step 2: Fixing negative remaining...")
        neg_fixed = _fix_negative_remaining(env)
        _logger.info(f"✅ Fixed {neg_fixed} layers with negative remaining_qty")
        
        # Step 3: Fix excess remaining
        _logger.info("Step 3: Fixing excess remaining...")
        excess_fixed = _fix_excess_remaining(env)
        _logger.info(f"✅ Fixed {excess_fixed} layers with excess remaining_qty")
        
        # Step 4: Recalculate remaining qty/value
        _logger.info("Step 4: Recalculating remaining qty/value per warehouse...")
        products_fixed, layers_updated = _recalculate_remaining_by_warehouse(env)
        _logger.info(f"✅ Processed {products_fixed} products, updated {layers_updated} layers")
        
        # Step 5: Fix value mismatch
        _logger.info("Step 5: Fixing value mismatch...")
        value_fixed = _fix_value_mismatch(env)
        _logger.info(f"✅ Fixed {value_fixed} products with value mismatch")
        
        # Verification
        _logger.info("Step 6: Verification...")
        verification = _verify_database(env)
        _logger.info(f"Total products: {verification['total_products']}")
        _logger.info(f"Value mismatch: {verification['value_mismatch']}")
        _logger.info(f"Remaining mismatch: {verification['remain_mismatch']}")
        _logger.info(f"Negative remaining: {verification['negative_remaining']}")
        _logger.info(f"Excess remaining: {verification['excess_remaining']}")
        
        if (verification['value_mismatch'] == 0 and 
            verification['remain_mismatch'] == 0 and
            verification['negative_remaining'] == 0 and
            verification['excess_remaining'] == 0):
            _logger.info("="*80)
            _logger.info("✅ Post-install hook completed successfully!")
            _logger.info("All valuation data has been fixed.")
            _logger.info("="*80)
        else:
            _logger.warning("="*80)
            _logger.warning("⚠️ Some issues remain after post-install hook")
            _logger.warning("Please run 'Recalculate Valuation' wizard manually")
            _logger.warning("Menu: Inventory > Configuration > Recalculate Valuation")
            _logger.warning("="*80)
        
    except Exception as e:
        _logger.error("="*80)
        _logger.error(f"❌ Error in post-install hook: {e}")
        _logger.error("Please run 'Recalculate Valuation' wizard manually")
        _logger.error("Menu: Inventory > Configuration > Recalculate Valuation")
        _logger.error("="*80)
        # Don't raise exception - allow installation to complete


def _fix_null_remaining_values(env):
    """Fix NULL remaining_value in negative layers"""
    query = """
        UPDATE stock_valuation_layer
        SET remaining_value = 0.0
        WHERE quantity < 0
          AND remaining_value IS NULL
    """
    env.cr.execute(query)
    return env.cr.rowcount


def _fix_negative_remaining(env):
    """Fix positive layers with negative remaining_qty"""
    query = """
        SELECT id, quantity, remaining_qty, value, remaining_value
        FROM stock_valuation_layer
        WHERE quantity > 0 AND remaining_qty < 0
    """
    env.cr.execute(query)
    layers_with_issue = env.cr.fetchall()
    
    fixed_count = 0
    for layer_id, qty, remain_qty, value, remain_value in layers_with_issue:
        env.cr.execute("""
            UPDATE stock_valuation_layer
            SET remaining_qty = quantity,
                remaining_value = value
            WHERE id = %s
        """, (layer_id,))
        fixed_count += 1
        _logger.warning(f"Fixed negative remaining: layer {layer_id}, "
                       f"qty={qty}, remain={remain_qty} -> {qty}")
    
    return fixed_count


def _fix_excess_remaining(env):
    """Fix layers where remaining_qty > quantity"""
    query = """
        SELECT id, quantity, remaining_qty, value, remaining_value
        FROM stock_valuation_layer
        WHERE quantity > 0 AND remaining_qty > quantity
    """
    env.cr.execute(query)
    layers_with_issue = env.cr.fetchall()
    
    fixed_count = 0
    for layer_id, qty, remain_qty, value, remain_value in layers_with_issue:
        if qty > 0:
            unit_cost = value / qty
            new_remain_qty = qty
            new_remain_value = qty * unit_cost
        else:
            new_remain_qty = 0.0
            new_remain_value = 0.0
        
        env.cr.execute("""
            UPDATE stock_valuation_layer
            SET remaining_qty = %s,
                remaining_value = %s
            WHERE id = %s
        """, (new_remain_qty, new_remain_value, layer_id))
        fixed_count += 1
        _logger.warning(f"Fixed excess remaining: layer {layer_id}, "
                       f"qty={qty}, remain={remain_qty} -> {new_remain_qty}")
    
    return fixed_count


def _recalculate_remaining_by_warehouse(env):
    """Recalculate remaining_qty and remaining_value per warehouse"""
    warehouses = env['stock.warehouse'].search([])
    
    total_products = 0
    total_layers = 0
    
    for warehouse in warehouses:
        _logger.info(f"  Processing warehouse: {warehouse.name} ({warehouse.code})")
        
        # Get all products in this warehouse
        query = """
            SELECT DISTINCT product_id
            FROM stock_valuation_layer
            WHERE warehouse_id = %s
            ORDER BY product_id
        """
        env.cr.execute(query, (warehouse.id,))
        product_ids = [row[0] for row in env.cr.fetchall()]
        
        for product_id in product_ids:
            # Get all layers for this product in this warehouse
            env.cr.execute("""
                SELECT id, quantity, value
                FROM stock_valuation_layer
                WHERE product_id = %s AND warehouse_id = %s
                ORDER BY create_date, id
            """, (product_id, warehouse.id))
            
            layers = env.cr.fetchall()
            
            # Simulate FIFO
            remaining_stock = {}
            
            for layer_id, qty, value in layers:
                if qty > 0:
                    remaining_stock[layer_id] = {'qty': qty, 'value': value}
                elif qty < 0:
                    qty_to_consume = abs(qty)
                    
                    for pos_layer_id in list(remaining_stock.keys()):
                        if qty_to_consume <= 0:
                            break
                        
                        available = remaining_stock[pos_layer_id]['qty']
                        consumed_qty = min(available, qty_to_consume)
                        
                        if available > 0:
                            unit_cost = remaining_stock[pos_layer_id]['value'] / available
                            consumed_value = consumed_qty * unit_cost
                        else:
                            consumed_value = 0
                        
                        remaining_stock[pos_layer_id]['qty'] -= consumed_qty
                        remaining_stock[pos_layer_id]['value'] -= consumed_value
                        qty_to_consume -= consumed_qty
                        
                        if remaining_stock[pos_layer_id]['qty'] <= 0.0001:
                            del remaining_stock[pos_layer_id]
            
            # Update database
            for layer_id, qty, value in layers:
                if qty > 0:
                    new_qty = remaining_stock.get(layer_id, {}).get('qty', 0.0)
                    new_value = remaining_stock.get(layer_id, {}).get('value', 0.0)
                else:
                    new_qty = 0.0
                    new_value = 0.0
                
                env.cr.execute("""
                    UPDATE stock_valuation_layer
                    SET remaining_qty = %s, remaining_value = %s
                    WHERE id = %s
                """, (new_qty, new_value, layer_id))
                
                total_layers += 1
            
            total_products += 1
            
            # Commit every 100 products
            if total_products % 100 == 0:
                env.cr.commit()
                _logger.info(f"    Progress: {total_products} products processed...")
    
    return total_products, total_layers


def _fix_value_mismatch(env):
    """Fix products where total_qty=0 but total_value≠0"""
    query = """
        SELECT 
            pp.id as product_id,
            SUM(svl.quantity) as total_qty,
            SUM(svl.value) as total_value
        FROM stock_valuation_layer svl
        JOIN product_product pp ON pp.id = svl.product_id
        GROUP BY pp.id
        HAVING ABS(SUM(svl.quantity)) < 0.01
           AND ABS(SUM(svl.value)) > 0.01
    """
    env.cr.execute(query)
    products_with_issue = env.cr.fetchall()
    
    fixed_count = 0
    
    for product_id, total_qty, total_value in products_with_issue:
        # Get all layers
        env.cr.execute("""
            SELECT id, quantity, value, warehouse_id
            FROM stock_valuation_layer
            WHERE product_id = %s
            ORDER BY create_date, id
        """, (product_id,))
        
        layers = env.cr.fetchall()
        
        positive_layers = [(lid, qty, val, wh) for lid, qty, val, wh in layers if qty > 0]
        negative_layers = [(lid, qty, val, wh) for lid, qty, val, wh in layers if qty < 0]
        
        positive_value = sum(val for _, _, val, _ in positive_layers)
        negative_value = sum(val for _, _, val, _ in negative_layers)
        
        value_diff = positive_value + negative_value
        
        if abs(value_diff) < 0.01:
            continue
        
        # Distribute adjustment across negative layers
        total_negative_qty = abs(sum(qty for _, qty, _, _ in negative_layers))
        
        if total_negative_qty < 0.01:
            continue
        
        for layer_id, qty, val, wh in negative_layers:
            proportion = abs(qty) / total_negative_qty
            adjustment = -value_diff * proportion
            new_value = val + adjustment
            
            env.cr.execute("""
                UPDATE stock_valuation_layer
                SET value = %s
                WHERE id = %s
            """, (new_value, layer_id))
        
        fixed_count += 1
    
    return fixed_count


def _verify_database(env):
    """Verify database consistency"""
    query = """
        SELECT 
            COUNT(*) as total_products,
            COUNT(CASE WHEN ABS(total_qty) < 0.01 AND ABS(total_value) > 0.01 THEN 1 END) as value_mismatch,
            COUNT(CASE WHEN ABS(moved_remain_diff) > 0.01 THEN 1 END) as remain_mismatch
        FROM (
            SELECT 
                pp.id,
                SUM(svl.quantity) as total_qty,
                SUM(svl.value) as total_value,
                SUM(svl.quantity) - SUM(svl.remaining_qty) as moved_remain_diff
            FROM stock_valuation_layer svl
            JOIN product_product pp ON pp.id = svl.product_id
            GROUP BY pp.id
        ) sub
    """
    env.cr.execute(query)
    result = env.cr.fetchone()
    
    # Check for negative remaining
    env.cr.execute("""
        SELECT COUNT(*)
        FROM stock_valuation_layer
        WHERE quantity > 0 AND remaining_qty < 0
    """)
    negative_remaining = env.cr.fetchone()[0]
    
    # Check for excess remaining
    env.cr.execute("""
        SELECT COUNT(*)
        FROM stock_valuation_layer
        WHERE quantity > 0 AND remaining_qty > quantity
    """)
    excess_remaining = env.cr.fetchone()[0]
    
    return {
        'total_products': result[0],
        'value_mismatch': result[1],
        'remain_mismatch': result[2],
        'negative_remaining': negative_remaining,
        'excess_remaining': excess_remaining,
    }
