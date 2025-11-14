# -*- coding: utf-8 -*-
"""
Migration script to populate location_id for existing stock.valuation.layer records.

This script should be run after module installation to backfill location_id
for valuation layers that were created before the field existed.

Usage:
    python manage.py shell
    >>> from odoo import api
    >>> from odoo.addons.stock_fifo_by_location.migrations import migrate_valuation_layers
    >>> migrate_valuation_layers.populate_location_id(env)
    
Or as a server action accessible from UI.
"""

from odoo import api
from odoo.tools import float_compare


def populate_location_id(env):
    """
    Populate location_id for existing stock.valuation.layer records.
    
    This function attempts to derive location_id from related stock.move
    or stock.move.line records. Items that cannot be resolved are logged
    for manual review.
    
    Args:
        env: Odoo environment
    """
    ValuationLayer = env['stock.valuation.layer']
    
    print("\n=== Stock FIFO by Location: Migration Start ===\n")
    print("Populating location_id for existing valuation layers...\n")
    
    # Find all layers without location_id
    layers_to_migrate = ValuationLayer.search([('location_id', '=', False)])
    
    total_count = len(layers_to_migrate)
    successful = 0
    failed = 0
    failed_layers = []
    
    print(f"Found {total_count} layers to migrate.\n")
    
    for i, layer in enumerate(layers_to_migrate, 1):
        location_id = None
        reason = None
        
        # Try to find location from related stock.move
        if layer.stock_move_id:
            move = layer.stock_move_id
            
            # For layers created from moves, use destination location
            if move.location_dest_id:
                location_id = move.location_dest_id.id
                reason = f"from stock.move {move.id} (dest_location)"
        
        # Fallback: try stock.move.line
        if not location_id and layer.stock_move_id:
            move_lines = env['stock.move.line'].search([
                ('move_id', '=', layer.stock_move_id.id),
            ], limit=1)
            
            if move_lines:
                location_id = move_lines[0].location_dest_id.id
                reason = f"from stock.move.line {move_lines[0].id}"
        
        # Try matching by product and date if no move link
        if not location_id:
            # Find moves of same product around layer creation time
            related_moves = env['stock.move'].search([
                ('product_id', '=', layer.product_id.id),
                ('date', '>=', layer.create_date - __import__('datetime').timedelta(days=1)),
                ('date', '<=', layer.create_date + __import__('datetime').timedelta(days=1)),
                ('state', '=', 'done'),
            ], limit=1, order='date desc')
            
            if related_moves:
                location_id = related_moves[0].location_dest_id.id
                reason = f"inferred from similar moves"
        
        if location_id:
            try:
                layer.location_id = location_id
                successful += 1
                print(f"[{i}/{total_count}] Layer {layer.id}: ✓ {reason}")
            except Exception as e:
                failed += 1
                failed_layers.append((layer.id, str(e)))
                print(f"[{i}/{total_count}] Layer {layer.id}: ✗ Error writing location: {e}")
        else:
            failed += 1
            failed_layers.append((layer.id, 'Could not determine location'))
            print(f"[{i}/{total_count}] Layer {layer.id}: ✗ Could not determine location")
    
    # Summary
    print(f"\n=== Migration Summary ===")
    print(f"Total processed: {total_count}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    
    if failed_layers:
        print(f"\n=== Layers Requiring Manual Review ===")
        for layer_id, reason in failed_layers:
            print(f"Layer {layer_id}: {reason}")
        print(f"\nPlease review these layers manually:")
        print(f"SELECT * FROM stock_valuation_layer WHERE id IN ({', '.join(str(l[0]) for l in failed_layers)});")
    
    print(f"\n=== Migration Complete ===\n")
    
    return {
        'total': total_count,
        'successful': successful,
        'failed': failed,
        'failed_ids': [l[0] for l in failed_layers],
    }


def populate_location_id_by_context(env, only_missing=True):
    """
    Alternative migration that uses move context more carefully.
    
    Args:
        env: Odoo environment
        only_missing: bool - only process layers without location_id
    """
    ValuationLayer = env['stock.valuation.layer']
    
    domain = []
    if only_missing:
        domain.append(('location_id', '=', False))
    
    layers = ValuationLayer.search(domain)
    
    for layer in layers:
        if not layer.stock_move_id:
            continue
        
        move = layer.stock_move_id
        
        # Determine location based on move type
        if move.location_id.usage != 'internal' and move.location_dest_id.usage == 'internal':
            # Incoming - use destination
            layer.location_id = move.location_dest_id.id
        
        elif move.location_id.usage == 'internal' and move.location_dest_id.usage != 'internal':
            # Outgoing - use source
            layer.location_id = move.location_id.id
        
        else:
            # Internal transfer - use destination
            layer.location_id = move.location_dest_id.id
    
    print(f"Migrated {len(layers)} layers with context-based location assignment")


def create_migration_server_action(env):
    """
    Create a server action in Odoo UI to trigger migration manually.
    """
    IrActionsServer = env['ir.actions.server']
    
    action = IrActionsServer.create({
        'name': 'Populate Location IDs for Valuation Layers',
        'type': 'ir.actions.server',
        'model_id': env.ref('stock.model_stock_valuation_layer').id,
        'binding_model_id': env.ref('stock.model_stock_valuation_layer').id,
        'state': 'code',
        'code': '''
from odoo.addons.stock_fifo_by_location.migrations import populate_location_id
result = populate_location_id.populate_location_id(env)
''',
    })
    
    return action
