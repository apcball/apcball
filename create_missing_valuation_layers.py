#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script to create missing valuation layers for inter-warehouse transfers
that were validated before the module was updated.

Usage:
    From Odoo shell:
    cd /opt/instance1/odoo17
    python3 odoo-bin shell -d MOG_LIVE_15_08
    >>> exec(open('/opt/instance1/odoo17/custom-addons/create_missing_valuation_layers.py').read())
"""

def create_missing_valuation_layers(env, move_ids=None):
    """
    Create valuation layers for inter-warehouse transfers that are missing them.
    
    Args:
        env: Odoo environment
        move_ids: List of specific move IDs to process (optional)
    """
    import logging
    _logger = logging.getLogger(__name__)
    
    print("=" * 80)
    print("Creating Missing Valuation Layers for Inter-Warehouse Transfers")
    print("=" * 80)
    print()
    
    # Get stock moves
    domain = [
        ('state', '=', 'done'),
        ('product_id.type', '=', 'product'),
    ]
    
    if move_ids:
        domain.append(('id', 'in', move_ids))
    
    moves = env['stock.move'].search(domain)
    print(f"Found {len(moves)} done moves to check")
    print()
    
    valuation_layer_model = env['stock.valuation.layer']
    created_count = 0
    skipped_count = 0
    error_count = 0
    
    for move in moves:
        try:
            product = move.product_id
            
            # Skip if not real-time valuation
            if product.valuation != 'real_time':
                continue
            
            # Get warehouses
            source_wh = move.location_id.warehouse_id if move.location_id else None
            dest_wh = move.location_dest_id.warehouse_id if move.location_dest_id else None
            
            # Only for inter-warehouse transfers
            if not (source_wh and dest_wh and source_wh.id != dest_wh.id):
                continue
            
            # Check if layers already exist
            existing_layers = valuation_layer_model.search([
                ('stock_move_id', '=', move.id),
            ])
            
            if existing_layers:
                skipped_count += 1
                continue
            
            # No layers exist - create them
            print(f"Creating layers for move {move.name} (ID: {move.id})")
            print(f"  Product: {product.name}")
            print(f"  Qty: {move.product_qty}")
            print(f"  {source_wh.name} → {dest_wh.name}")
            
            company = move.company_id
            
            # Get cost from FIFO service with fallback to standard_price
            fifo_service = env['fifo.service']
            try:
                fifo_result = fifo_service.calculate_fifo_cost_with_landed_cost(
                    product, source_wh, move.product_qty, company.id
                )
                
                if isinstance(fifo_result, dict):
                    unit_cost = fifo_result.get('unit_cost', 0.0)
                else:
                    unit_cost = float(fifo_result) if fifo_result else 0.0
            except Exception as e:
                print(f"  Warning: FIFO calculation failed: {e}")
                unit_cost = 0.0
            
            # Fallback to standard price if still zero
            if unit_cost <= 0:
                unit_cost = product.standard_price or 0.0
                print(f"  Using standard_price: {unit_cost}")
            else:
                print(f"  Using FIFO cost: {unit_cost}")
            
            # Create negative layer at source warehouse
            neg_layer = valuation_layer_model.sudo().create({
                'stock_move_id': move.id,
                'product_id': product.id,
                'warehouse_id': source_wh.id,
                'quantity': -move.product_qty,
                'unit_cost': unit_cost,
                'value': -move.product_qty * unit_cost,
                'company_id': company.id,
                'description': f'Retroactive: {source_wh.name} → {dest_wh.name}',
            })
            
            # Create positive layer at destination warehouse
            pos_layer = valuation_layer_model.sudo().create({
                'stock_move_id': move.id,
                'product_id': product.id,
                'warehouse_id': dest_wh.id,
                'quantity': move.product_qty,
                'unit_cost': unit_cost,
                'value': move.product_qty * unit_cost,
                'company_id': company.id,
                'description': f'Retroactive: {source_wh.name} → {dest_wh.name}',
            })
            
            print(f"  ✓ Created 2 layers: {neg_layer.id}, {pos_layer.id}")
            print(f"  Value: {move.product_qty} @ {unit_cost} = {move.product_qty * unit_cost}")
            print()
            
            created_count += 1
            
        except Exception as e:
            print(f"  ✗ Error processing move {move.id}: {e}")
            print()
            error_count += 1
    
    # Commit changes
    env.cr.commit()
    
    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Created layers for: {created_count} moves")
    print(f"Skipped (existing):  {skipped_count} moves")
    print(f"Errors:             {error_count} moves")
    print()
    
    return {
        'created': created_count,
        'skipped': skipped_count,
        'errors': error_count
    }


# Auto-run if executed in Odoo shell
if __name__ == '__main__' or 'env' in dir():
    try:
        # For specific moves from the screenshots
        specific_moves = [514826]  # Move with qty 1.0 that needs layers
        
        print("Processing specific moves:", specific_moves)
        result = create_missing_valuation_layers(env, move_ids=specific_moves)
        
        print("\n" + "=" * 80)
        print("✓ COMPLETED")
        print("=" * 80)
        
    except NameError:
        print("This script should be run from Odoo shell:")
        print("python3 odoo-bin shell -d MOG_LIVE_15_08")
        print(">>> exec(open('/opt/instance1/odoo17/custom-addons/create_missing_valuation_layers.py').read())")
