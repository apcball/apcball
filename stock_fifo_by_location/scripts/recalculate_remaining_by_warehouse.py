#!/usr/bin/env python3
"""
Recalculate remaining_qty and remaining_value for all products per warehouse

This script re-runs FIFO calculation for each warehouse independently to ensure:
1. remaining_qty is correctly calculated per warehouse
2. No cross-warehouse FIFO consumption
3. All negative layers have remaining = 0
"""

import sys
import os

# Add Odoo to path
sys.path.append('/opt/instance1/odoo17')

import odoo
from odoo import api, SUPERUSER_ID

# Initialize Odoo
odoo.tools.config.parse_config([
    '-c', '/etc/instance1.conf',
    '-d', 'MOG_Test',
])

print("\n" + "="*80)
print("Recalculate Remaining Qty/Value by Warehouse")
print("="*80)

registry = odoo.registry('MOG_Test')
with registry.cursor() as cr:
    env = api.Environment(cr, SUPERUSER_ID, {})
    
    # Get all warehouses
    warehouses = env['stock.warehouse'].search([])
    print(f"\nพบ {len(warehouses)} warehouses")
    
    total_products_fixed = 0
    total_layers_updated = 0
    
    for wh in warehouses:
        print(f"\n{'='*80}")
        print(f"Processing: {wh.name} ({wh.code})")
        print(f"{'='*80}")
        
        # Get all products with layers in this warehouse
        query = """
            SELECT DISTINCT product_id
            FROM stock_valuation_layer
            WHERE warehouse_id = %s
            ORDER BY product_id
        """
        cr.execute(query, (wh.id,))
        product_ids = [row[0] for row in cr.fetchall()]
        
        print(f"  Found {len(product_ids)} products in warehouse")
        
        products_fixed = 0
        layers_updated = 0
        
        for product_id in product_ids:
            # Get all layers for this product in this warehouse, ordered by FIFO
            cr.execute("""
                SELECT id, quantity, value
                FROM stock_valuation_layer
                WHERE product_id = %s AND warehouse_id = %s
                ORDER BY create_date, id
            """, (product_id, wh.id))
            
            layers = cr.fetchall()
            
            # Simulate FIFO: track remaining for positive layers
            remaining_stock = {}  # layer_id -> remaining_qty
            
            for layer_id, qty, value in layers:
                if qty > 0:
                    # Positive layer: initially all remaining
                    remaining_stock[layer_id] = {'qty': qty, 'value': value}
                elif qty < 0:
                    # Negative layer: consume from FIFO queue
                    qty_to_consume = abs(qty)
                    
                    for pos_layer_id in list(remaining_stock.keys()):
                        if qty_to_consume <= 0:
                            break
                        
                        available = remaining_stock[pos_layer_id]['qty']
                        consumed_qty = min(available, qty_to_consume)
                        
                        # Calculate value consumed proportionally
                        if available > 0:
                            unit_cost = remaining_stock[pos_layer_id]['value'] / available
                            consumed_value = consumed_qty * unit_cost
                        else:
                            consumed_value = 0
                        
                        # Update remaining
                        remaining_stock[pos_layer_id]['qty'] -= consumed_qty
                        remaining_stock[pos_layer_id]['value'] -= consumed_value
                        
                        qty_to_consume -= consumed_qty
                        
                        # Remove from queue if fully consumed
                        if remaining_stock[pos_layer_id]['qty'] <= 0.0001:
                            del remaining_stock[pos_layer_id]
            
            # Update database with calculated remaining values
            for layer_id, qty, value in layers:
                if qty > 0:
                    # Positive layer
                    new_remaining_qty = remaining_stock.get(layer_id, {}).get('qty', 0.0)
                    new_remaining_value = remaining_stock.get(layer_id, {}).get('value', 0.0)
                else:
                    # Negative layer: always 0
                    new_remaining_qty = 0.0
                    new_remaining_value = 0.0
                
                # Update layer
                cr.execute("""
                    UPDATE stock_valuation_layer
                    SET remaining_qty = %s,
                        remaining_value = %s
                    WHERE id = %s
                """, (new_remaining_qty, new_remaining_value, layer_id))
                
                layers_updated += 1
            
            products_fixed += 1
            
            if products_fixed % 100 == 0:
                print(f"    Progress: {products_fixed}/{len(product_ids)} products...")
                cr.commit()  # Commit every 100 products
        
        print(f"  ✅ Warehouse {wh.code}: {products_fixed} products, {layers_updated} layers updated")
        total_products_fixed += products_fixed
        total_layers_updated += layers_updated
        
        # Commit after each warehouse
        cr.commit()
    
    print("\n" + "="*80)
    print(f"สรุปผลการ recalculate:")
    print(f"  ✅ Total products: {total_products_fixed}")
    print(f"  ✅ Total layers updated: {total_layers_updated}")
    print("="*80)
