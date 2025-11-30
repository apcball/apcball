#!/usr/bin/env python3
"""
Fix valuation layers for return moves that have incorrect warehouse_id.

Problem:
- Return move negative layers are assigned to wrong warehouse
- Should be at SOURCE warehouse (where stock is taken from)
- Not at DESTINATION warehouse

This script:
1. Find all return moves with inter-warehouse transfer
2. Check their valuation layers
3. Fix negative layers to have SOURCE warehouse_id
4. Fix positive layers to have DEST warehouse_id
5. Update remaining_qty if needed
"""

import sys
import os

# Add Odoo to path
sys.path.append('/opt/instance1/odoo17')

import odoo
from odoo import api, SUPERUSER_ID

# Configuration
DB_NAME = 'MOG_LIVE_15_08'
CONFIG_FILE = '/etc/instance1.conf'

def fix_return_move_layers():
    """Fix valuation layers for return moves."""
    
    odoo.tools.config.parse_config(['-c', CONFIG_FILE])
    odoo.tools.config['db_name'] = DB_NAME
    
    registry = odoo.registry(DB_NAME)
    
    with registry.cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {})
        
        print("=" * 80)
        print("FIXING RETURN MOVE VALUATION LAYERS")
        print("=" * 80)
        
        # Find all return moves
        StockMove = env['stock.move']
        ValuationLayer = env['stock.valuation.layer']
        
        # Get return moves that involve inter-warehouse transfers
        return_moves = StockMove.search([
            ('origin_returned_move_id', '!=', False),
            ('state', '=', 'done'),
        ])
        
        print(f"\nFound {len(return_moves)} return moves")
        
        fixed_count = 0
        error_count = 0
        
        for move in return_moves:
                try:
                    source_wh = move.location_id.warehouse_id
                    dest_wh = move.location_dest_id.warehouse_id
                    
                    # Skip if not inter-warehouse
                    if not (source_wh and dest_wh and source_wh.id != dest_wh.id):
                        continue
                    
                    # Get valuation layers for this move
                    layers = ValuationLayer.search([
                        ('stock_move_id', '=', move.id),
                    ])
                    
                    if not layers:
                        continue
                    
                    print(f"\n{'='*60}")
                    print(f"Return Move: {move.name} ({move.reference})")
                    print(f"  {source_wh.name} → {dest_wh.name}")
                    print(f"  Qty: {move.product_qty}")
                    
                    needs_fix = False
                    
                    for layer in layers:
                        if layer.quantity < 0:
                            # Negative layer should be at SOURCE warehouse
                            if not layer.warehouse_id or layer.warehouse_id.id != source_wh.id:
                                needs_fix = True
                                old_wh_name = layer.warehouse_id.name if layer.warehouse_id else 'None'
                                print(f"  ❌ Layer {layer.id} (qty={layer.quantity}): {old_wh_name} → {source_wh.name}")
                                layer.warehouse_id = source_wh.id
                                print(f"     ✅ Fixed to {source_wh.name}")
                        
                        elif layer.quantity > 0:
                            # Positive layer should be at DEST warehouse
                            if not layer.warehouse_id or layer.warehouse_id.id != dest_wh.id:
                                needs_fix = True
                                old_wh_name = layer.warehouse_id.name if layer.warehouse_id else 'None'
                                print(f"  ❌ Layer {layer.id} (qty={layer.quantity}): {old_wh_name} → {dest_wh.name}")
                                layer.warehouse_id = dest_wh.id
                                print(f"     ✅ Fixed to {dest_wh.name}")
                    
                    if needs_fix:
                        fixed_count += 1
                        cr.commit()
                        print(f"  ✅ Move {move.name} fixed and committed")
                    
            except Exception as e:
                error_count += 1
                print(f"  ❌ Error fixing move {move.name}: {e}")
                cr.rollback()
        
        print("\n" + "=" * 80)
        print(f"SUMMARY:")
        print(f"  Fixed moves: {fixed_count}")
        print(f"  Errors: {error_count}")
        print("=" * 80)

if __name__ == '__main__':
    fix_return_move_layers()
