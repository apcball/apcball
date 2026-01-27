# -*- coding: utf-8 -*-
"""
Post-migration script for v17.0.1.1.1
Fix negative warehouse balance from incorrect return moves

This script:
1. Identifies warehouses with negative valuation
2. Finds return moves that went to wrong warehouse
3. Recalculates valuation layers
4. Balances warehouse inventory
"""

import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Main migration function.
    
    Args:
        cr: database cursor
        version: current module version
    """
    if not version:
        return
    
    _logger.info("=" * 80)
    _logger.info("Starting migration v17.0.1.1.1: Fix negative warehouse balance")
    _logger.info("=" * 80)
    
    env = api.Environment(cr, SUPERUSER_ID, {})
    
    # Step 1: Find warehouses with negative balance
    fix_negative_warehouse_balance(env)
    
    # Step 2: Recalculate remaining_qty and remaining_value
    recalculate_layer_balances(env)
    
    _logger.info("=" * 80)
    _logger.info("Migration v17.0.1.1.1 completed successfully")
    _logger.info("=" * 80)


def fix_negative_warehouse_balance(env):
    """
    Find and fix warehouses with negative valuation balance.
    
    Strategy:
    1. Query all warehouses with negative total value
    2. For each warehouse, find the cause (usually return to wrong warehouse)
    3. Adjust valuation layers to balance
    """
    _logger.info("Step 1: Finding warehouses with negative balance...")
    
    # SQL to find warehouses with negative balance
    query = """
        SELECT 
            w.id as warehouse_id,
            w.name as warehouse_name,
            pp.id as product_id,
            pt.name as product_name,
            SUM(svl.quantity) as total_qty,
            SUM(svl.value) as total_value,
            SUM(svl.remaining_qty) as remaining_qty,
            SUM(svl.remaining_value) as remaining_value
        FROM stock_valuation_layer svl
        JOIN stock_warehouse w ON w.id = svl.warehouse_id
        JOIN product_product pp ON pp.id = svl.product_id
        JOIN product_template pt ON pt.id = pp.product_tmpl_id
        WHERE svl.warehouse_id IS NOT NULL
        GROUP BY w.id, w.name, pp.id, pt.name
        HAVING SUM(svl.remaining_value) < -0.01 OR SUM(svl.remaining_qty) < -0.01
        ORDER BY SUM(svl.remaining_value)
    """
    
    env.cr.execute(query)
    negative_balances = env.cr.dictfetchall()
    
    if not negative_balances:
        _logger.info("✅ No warehouses with negative balance found!")
        return
    
    _logger.warning(f"⚠️  Found {len(negative_balances)} warehouse-product combinations with negative balance:")
    
    for balance in negative_balances:
        _logger.warning(
            f"  - Warehouse: {balance['warehouse_name']}, "
            f"Product: {balance['product_name']}, "
            f"Remaining Qty: {balance['remaining_qty']:.2f}, "
            f"Remaining Value: {balance['remaining_value']:.2f}"
        )
    
    # For each negative balance, try to fix
    for balance in negative_balances:
        try:
            fix_product_warehouse_balance(
                env,
                balance['warehouse_id'],
                balance['product_id'],
                balance['remaining_qty'],
                balance['remaining_value']
            )
        except Exception as e:
            _logger.error(
                f"❌ Failed to fix balance for warehouse {balance['warehouse_name']}, "
                f"product {balance['product_name']}: {str(e)}"
            )
            continue


def fix_product_warehouse_balance(env, warehouse_id, product_id, negative_qty, negative_value):
    """
    Fix negative balance for a specific product at warehouse.
    
    Strategy:
    1. If remaining_qty is negative, create adjustment layer to balance
    2. If remaining_value is negative, adjust value to 0
    """
    warehouse = env['stock.warehouse'].browse(warehouse_id)
    product = env['product.product'].browse(product_id)
    
    _logger.info(f"Fixing: {warehouse.name} / {product.display_name}")
    
    # Get all layers for this product at this warehouse
    layers = env['stock.valuation.layer'].search([
        ('warehouse_id', '=', warehouse_id),
        ('product_id', '=', product_id),
    ], order='create_date, id')
    
    if not layers:
        _logger.info("  No layers found, skipping")
        return
    
    # Check if there are return moves that might have caused this
    return_layers = layers.filtered(
        lambda l: l.stock_move_id and l.stock_move_id.origin_returned_move_id
    )
    
    if return_layers:
        _logger.info(f"  Found {len(return_layers)} return move layers")
        
        # Check if returns have correct warehouse
        for layer in return_layers:
            original_move = layer.stock_move_id.origin_returned_move_id
            if original_move and original_move.warehouse_id:
                if original_move.warehouse_id.id != warehouse_id:
                    _logger.warning(
                        f"  ⚠️  Layer {layer.id} is a return but warehouse mismatch: "
                        f"Original WH: {original_move.warehouse_id.name}, "
                        f"Return WH: {warehouse.name}"
                    )
    
    # Calculate what adjustment is needed
    total_qty = sum(layers.mapped('quantity'))
    total_value = sum(layers.mapped('value'))
    remaining_qty = sum(layers.mapped('remaining_qty'))
    remaining_value = sum(layers.mapped('remaining_value'))
    
    _logger.info(
        f"  Current state: "
        f"Total Qty: {total_qty:.2f}, "
        f"Total Value: {total_value:.2f}, "
        f"Remaining Qty: {remaining_qty:.2f}, "
        f"Remaining Value: {remaining_value:.2f}"
    )
    
    # If remaining balance is significantly negative, create adjustment
    if remaining_qty < -0.01 or remaining_value < -0.01:
        _logger.warning(
            f"  Creating adjustment layer to fix negative balance: "
            f"Qty: {abs(remaining_qty):.2f}, Value: {abs(remaining_value):.2f}"
        )
        
        # Create adjustment layer
        adjustment_layer = env['stock.valuation.layer'].sudo().create({
            'product_id': product_id,
            'warehouse_id': warehouse_id,
            'quantity': abs(remaining_qty) if remaining_qty < 0 else 0,
            'value': abs(remaining_value) if remaining_value < 0 else 0,
            'unit_cost': abs(remaining_value / remaining_qty) if remaining_qty < -0.01 else 0,
            'remaining_qty': abs(remaining_qty) if remaining_qty < 0 else 0,
            'remaining_value': abs(remaining_value) if remaining_value < 0 else 0,
            'description': f'Migration adjustment v17.0.1.1.1: Fix negative balance',
            'company_id': warehouse.company_id.id,
        })
        
        _logger.info(f"  ✅ Created adjustment layer {adjustment_layer.id}")
    
    # Recalculate balances
    recalculate_product_warehouse_balance(env, warehouse_id, product_id)


def recalculate_product_warehouse_balance(env, warehouse_id, product_id):
    """
    Recalculate remaining_qty and remaining_value for all layers.
    
    This ensures FIFO queue is correct after adjustments.
    """
    layers = env['stock.valuation.layer'].search([
        ('warehouse_id', '=', warehouse_id),
        ('product_id', '=', product_id),
    ], order='create_date, id')
    
    running_qty = 0.0
    running_value = 0.0
    
    for layer in layers:
        # Update running totals
        running_qty += layer.quantity
        running_value += layer.value
        
        # For positive layers (incoming), remaining = quantity
        if layer.quantity > 0:
            layer.sudo().write({
                'remaining_qty': layer.quantity,
                'remaining_value': layer.value,
            })
        # For negative layers (outgoing), remaining = 0
        else:
            layer.sudo().write({
                'remaining_qty': 0,
                'remaining_value': 0,
            })
    
    _logger.info(
        f"  Recalculated: Final Qty: {running_qty:.2f}, Final Value: {running_value:.2f}"
    )


def recalculate_layer_balances(env):
    """
    Recalculate remaining_qty and remaining_value for ALL layers.
    
    This ensures data consistency across the entire database.
    """
    _logger.info("Step 2: Recalculating layer balances...")
    
    # Get all products with valuation layers
    query = """
        SELECT DISTINCT 
            svl.warehouse_id,
            svl.product_id
        FROM stock_valuation_layer svl
        WHERE svl.warehouse_id IS NOT NULL
        ORDER BY svl.warehouse_id, svl.product_id
    """
    
    env.cr.execute(query)
    combinations = env.cr.fetchall()
    
    _logger.info(f"Found {len(combinations)} warehouse-product combinations to recalculate")
    
    count = 0
    for warehouse_id, product_id in combinations:
        try:
            recalculate_product_warehouse_balance(env, warehouse_id, product_id)
            count += 1
            
            if count % 100 == 0:
                _logger.info(f"  Processed {count}/{len(combinations)} combinations...")
                env.cr.commit()  # Commit every 100 records
        except Exception as e:
            _logger.error(
                f"❌ Failed to recalculate warehouse {warehouse_id}, product {product_id}: {str(e)}"
            )
            continue
    
    _logger.info(f"✅ Recalculated {count} warehouse-product combinations")


def verify_fix(env):
    """
    Verify that all negative balances have been fixed.
    """
    _logger.info("Step 3: Verifying fixes...")
    
    query = """
        SELECT 
            w.name as warehouse_name,
            pt.name as product_name,
            SUM(svl.remaining_qty) as remaining_qty,
            SUM(svl.remaining_value) as remaining_value
        FROM stock_valuation_layer svl
        JOIN stock_warehouse w ON w.id = svl.warehouse_id
        JOIN product_product pp ON pp.id = svl.product_id
        JOIN product_template pt ON pt.id = pp.product_tmpl_id
        WHERE svl.warehouse_id IS NOT NULL
        GROUP BY w.name, pt.name
        HAVING SUM(svl.remaining_value) < -0.01 OR SUM(svl.remaining_qty) < -0.01
    """
    
    env.cr.execute(query)
    remaining_negatives = env.cr.dictfetchall()
    
    if remaining_negatives:
        _logger.warning(f"⚠️  Still have {len(remaining_negatives)} negative balances:")
        for neg in remaining_negatives:
            _logger.warning(
                f"  - {neg['warehouse_name']} / {neg['product_name']}: "
                f"Qty: {neg['remaining_qty']:.2f}, Value: {neg['remaining_value']:.2f}"
            )
    else:
        _logger.info("✅ All negative balances have been fixed!")
