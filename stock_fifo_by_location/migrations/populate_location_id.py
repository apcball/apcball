# -*- coding: utf-8 -*-
"""
Migration script to populate location_id for existing stock.valuation.layer records.

This script handles backfilling location_id for valuation layers created before
the field existed. It supports all location types including:

- Internal locations (warehouses, storage areas)
- Transit locations (for inter-warehouse transfers)
- Supplier/Customer locations
- Production locations

Key Features:
-------------
1. populate_location_id(env)
   Main migration function that processes all layers without location_id.
   Uses intelligent logic to determine correct location based on:
   - Layer quantity (positive/negative)
   - Move source and destination
   - Location usage types

2. populate_location_id_by_context(env, only_missing=True)
   Alternative migration using simplified context-based logic.
   Faster but less detailed than the main function.

3. populate_transit_location_layers(env)
   Specialized function for transit location scenarios:
   - Internal → Transit (warehouse shipments)
   - Transit → Internal (warehouse receipts)
   - Transit → Transit (inter-transit moves)

4. analyze_transit_locations(env)
   Diagnostic function to analyze transit location usage and
   identify layers needing migration.

Usage Examples:
---------------

Basic migration (all layers):
    python odoo-bin shell -d your_database
    >>> from odoo.addons.stock_fifo_by_location.migrations import populate_location_id
    >>> result = populate_location_id.populate_location_id(env)
    >>> print(f"Migrated: {result['successful']}, Failed: {result['failed']}")

Transit-only migration:
    >>> from odoo.addons.stock_fifo_by_location.migrations import populate_location_id
    >>> result = populate_location_id.populate_transit_location_layers(env)
    >>> print(f"Transit layers migrated: {result['successful']}")

Analysis before migration:
    >>> from odoo.addons.stock_fifo_by_location.migrations import populate_location_id
    >>> stats = populate_location_id.analyze_transit_locations(env)
    >>> print(f"Transit locations: {stats['transit_locations']}")
    >>> print(f"Layers needing migration: {stats['transit_missing']}")

Server Action (from UI):
    Can be created via create_migration_server_action(env) to allow
    running migration from Settings → Technical → Server Actions

Transit Location Scenarios:
---------------------------
This module properly handles complex inter-warehouse transfer flows:

1. Warehouse A → Transit → Warehouse B:
   - Step 1 (A→Transit): Negative layer at Warehouse A, Positive at Transit
   - Step 2 (Transit→B): Negative layer at Transit, Positive at Warehouse B

2. Direct Transit moves:
   - Supplier → Transit: Positive layer at Transit
   - Transit → Customer: Negative layer at Transit

3. Production with Transit:
   - Production → Transit: Positive layer at Transit
   - Transit → Warehouse: Positive layer at Warehouse

Important Notes:
----------------
- Always backup your database before running migration
- Test on staging environment first
- Review failed layers manually after migration
- For large databases, consider running in batches
- Migration is idempotent (safe to run multiple times)
"""

from odoo import api
from odoo.tools import float_compare


def populate_location_id(env):
    """
    Populate location_id for existing stock.valuation.layer records.
    
    This function attempts to derive location_id from related stock.move
    or stock.move.line records. Items that cannot be resolved are logged
    for manual review.
    
    Supports:
    - Internal locations
    - Transit locations (for inter-warehouse transfers)
    - Supplier/Customer moves
    - Production moves
    
    Args:
        env: Odoo environment
    """
    ValuationLayer = env['stock.valuation.layer']
    
    print("\n=== Stock FIFO by Location: Migration Start ===\n")
    print("Populating location_id for existing valuation layers...\n")
    print("Supports internal, transit, and other location types.\n")
    
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
            
            # Determine location based on layer quantity (positive/negative) and move type
            layer_qty = layer.quantity
            source_usage = move.location_id.usage if move.location_id else None
            dest_usage = move.location_dest_id.usage if move.location_dest_id else None
            
            # For positive layers (incoming/receiving)
            if layer_qty > 0:
                # Always use destination for positive layers
                if move.location_dest_id:
                    location_id = move.location_dest_id.id
                    
                    if dest_usage == 'transit':
                        reason = f"from stock.move {move.id} (dest_transit: {move.location_dest_id.name})"
                    elif dest_usage == 'internal':
                        reason = f"from stock.move {move.id} (dest_internal: {move.location_dest_id.name})"
                    else:
                        reason = f"from stock.move {move.id} (dest: {move.location_dest_id.name})"
            
            # For negative layers (outgoing/consumption)
            elif layer_qty < 0:
                # Use source location for outgoing
                if move.location_id:
                    # Special handling for transit scenarios
                    if source_usage == 'transit':
                        # Transit → Anywhere: Track transit location as source
                        location_id = move.location_id.id
                        reason = f"from stock.move {move.id} (source_transit: {move.location_id.name})"
                    
                    elif source_usage == 'internal':
                        # Internal → Anywhere: Track warehouse as source
                        location_id = move.location_id.id
                        reason = f"from stock.move {move.id} (source_internal: {move.location_id.name})"
                    
                    elif source_usage in ('supplier', 'production', 'customer'):
                        # Non-internal source: use destination instead (edge case)
                        if move.location_dest_id:
                            location_id = move.location_dest_id.id
                            
                            if dest_usage == 'transit':
                                reason = f"from stock.move {move.id} (dest_transit fallback: {move.location_dest_id.name})"
                            else:
                                reason = f"from stock.move {move.id} (dest fallback: {move.location_dest_id.name})"
                    
                    else:
                        # Generic source
                        location_id = move.location_id.id
                        reason = f"from stock.move {move.id} (source: {move.location_id.name})"
            
            # For zero quantity layers (rare but possible)
            else:
                if move.location_dest_id:
                    location_id = move.location_dest_id.id
                    reason = f"from stock.move {move.id} (dest, zero qty)"
        
        # Fallback: try stock.move.line
        if not location_id and layer.stock_move_id:
            move_lines = env['stock.move.line'].search([
                ('move_id', '=', layer.stock_move_id.id),
            ], limit=1)
            
            if move_lines:
                move_line = move_lines[0]
                layer_qty = layer.quantity
                
                if layer_qty > 0:
                    location_id = move_line.location_dest_id.id
                    reason = f"from stock.move.line {move_line.id} (dest)"
                else:
                    location_id = move_line.location_id.id
                    reason = f"from stock.move.line {move_line.id} (source)"
        
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
                reason = f"inferred from similar moves (dest)"
        
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
    
    Handles all location types including:
    - Internal locations (warehouses)
    - Transit locations (inter-warehouse transfers)
    - Supplier/Customer locations
    - Production locations
    
    Args:
        env: Odoo environment
        only_missing: bool - only process layers without location_id
    """
    ValuationLayer = env['stock.valuation.layer']
    
    print("\n=== Context-Based Location Migration ===\n")
    
    domain = []
    if only_missing:
        domain.append(('location_id', '=', False))
    
    layers = ValuationLayer.search(domain)
    
    print(f"Processing {len(layers)} layers with context-based logic...\n")
    
    migrated = 0
    skipped = 0
    
    for layer in layers:
        if not layer.stock_move_id:
            skipped += 1
            continue
        
        move = layer.stock_move_id
        source_usage = move.location_id.usage if move.location_id else None
        dest_usage = move.location_dest_id.usage if move.location_dest_id else None
        layer_qty = layer.quantity
        
        # Determine location based on move type and layer quantity
        # Positive layers (incoming/receiving)
        if layer_qty > 0:
            # Always use destination for positive layers
            layer.location_id = move.location_dest_id.id
            migrated += 1
            print(f"Layer {layer.id}: Positive → {move.location_dest_id.name} ({dest_usage})")
        
        # Negative layers (outgoing/consumption)
        elif layer_qty < 0:
            # Transit → Anywhere: Track transit as source
            if source_usage == 'transit':
                layer.location_id = move.location_id.id
                migrated += 1
                print(f"Layer {layer.id}: Negative Transit→Any → {move.location_id.name}")
            
            # Internal → Anywhere: Track warehouse as source
            elif source_usage == 'internal':
                layer.location_id = move.location_id.id
                migrated += 1
                print(f"Layer {layer.id}: Negative Internal→Any → {move.location_id.name}")
            
            # Non-internal source (supplier/production) → Internal/Transit: Track destination
            elif dest_usage in ('internal', 'transit'):
                layer.location_id = move.location_dest_id.id
                migrated += 1
                print(f"Layer {layer.id}: Negative {source_usage}→{dest_usage} → {move.location_dest_id.name}")
            
            # Other cases: use source if available
            elif move.location_id:
                layer.location_id = move.location_id.id
                migrated += 1
                print(f"Layer {layer.id}: Negative fallback → {move.location_id.name}")
            
            else:
                skipped += 1
                print(f"Layer {layer.id}: Negative - Could not determine location")
        
        # Zero quantity (rare)
        else:
            if move.location_dest_id:
                layer.location_id = move.location_dest_id.id
                migrated += 1
                print(f"Layer {layer.id}: Zero qty → {move.location_dest_id.name}")
            else:
                skipped += 1
    
    print(f"\n=== Context Migration Summary ===")
    print(f"Total processed: {len(layers)}")
    print(f"Migrated: {migrated}")
    print(f"Skipped: {skipped}")
    print(f"=================================\n")
    
    return {'migrated': migrated, 'skipped': skipped}


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


def populate_transit_location_layers(env):
    """
    Specialized migration function for Transit location valuation layers.
    
    This function specifically handles valuation layers involved in inter-warehouse
    transfers using Transit locations:
    - Internal → Transit (warehouse shipment)
    - Transit → Internal (warehouse receipt)
    - Transit → Transit (inter-transit moves)
    
    Args:
        env: Odoo environment
    
    Returns:
        dict: Migration statistics
    """
    ValuationLayer = env['stock.valuation.layer']
    StockMove = env['stock.move']
    
    print("\n=== Transit Location Migration Start ===\n")
    print("Processing valuation layers for Transit locations...\n")
    
    # Find all layers without location_id that might involve transit
    layers_no_location = ValuationLayer.search([('location_id', '=', False)])
    
    total_count = 0
    successful = 0
    failed = 0
    failed_layers = []
    transit_stats = {
        'internal_to_transit': 0,
        'transit_to_internal': 0,
        'transit_to_transit': 0,
    }
    
    for layer in layers_no_location:
        if not layer.stock_move_id:
            continue
        
        move = layer.stock_move_id
        source_usage = move.location_id.usage if move.location_id else None
        dest_usage = move.location_dest_id.usage if move.location_dest_id else None
        
        # Check if this move involves transit location
        is_transit_related = (source_usage == 'transit' or dest_usage == 'transit')
        
        if not is_transit_related:
            continue
        
        total_count += 1
        location_id = None
        reason = None
        move_type = None
        
        # Determine location based on transit scenario
        layer_qty = layer.quantity
        
        # Scenario 1: Internal → Transit (Warehouse Shipment)
        if source_usage == 'internal' and dest_usage == 'transit':
            move_type = 'internal_to_transit'
            
            if layer_qty < 0:
                # Negative layer: Track source warehouse
                location_id = move.location_id.id
                reason = f"Internal→Transit: Source warehouse {move.location_id.name}"
            elif layer_qty > 0:
                # Positive layer: Track destination transit
                location_id = move.location_dest_id.id
                reason = f"Internal→Transit: Dest transit {move.location_dest_id.name}"
        
        # Scenario 2: Transit → Internal (Warehouse Receipt)
        elif source_usage == 'transit' and dest_usage == 'internal':
            move_type = 'transit_to_internal'
            
            if layer_qty < 0:
                # Negative layer: Track source transit
                location_id = move.location_id.id
                reason = f"Transit→Internal: Source transit {move.location_id.name}"
            elif layer_qty > 0:
                # Positive layer: Track destination warehouse
                location_id = move.location_dest_id.id
                reason = f"Transit→Internal: Dest warehouse {move.location_dest_id.name}"
        
        # Scenario 3: Transit → Transit (Inter-Transit Move)
        elif source_usage == 'transit' and dest_usage == 'transit':
            move_type = 'transit_to_transit'
            
            if layer_qty < 0:
                # Negative layer: Track source transit
                location_id = move.location_id.id
                reason = f"Transit→Transit: Source transit {move.location_id.name}"
            elif layer_qty > 0:
                # Positive layer: Track destination transit
                location_id = move.location_dest_id.id
                reason = f"Transit→Transit: Dest transit {move.location_dest_id.name}"
        
        # Scenario 4: Supplier/Production → Transit
        elif source_usage in ('supplier', 'production') and dest_usage == 'transit':
            move_type = 'internal_to_transit'  # Count as internal_to_transit
            
            # Always use destination transit for incoming
            location_id = move.location_dest_id.id
            reason = f"{source_usage}→Transit: Dest transit {move.location_dest_id.name}"
        
        # Scenario 5: Transit → Customer
        elif source_usage == 'transit' and dest_usage == 'customer':
            move_type = 'transit_to_internal'  # Count as transit_to_internal
            
            # Use source transit for outgoing
            location_id = move.location_id.id
            reason = f"Transit→Customer: Source transit {move.location_id.name}"
        
        # Apply the location
        if location_id:
            try:
                layer.location_id = location_id
                successful += 1
                
                if move_type:
                    transit_stats[move_type] = transit_stats.get(move_type, 0) + 1
                
                print(f"Layer {layer.id}: ✓ {reason}")
            except Exception as e:
                failed += 1
                failed_layers.append((layer.id, str(e)))
                print(f"Layer {layer.id}: ✗ Error: {e}")
        else:
            failed += 1
            failed_layers.append((layer.id, 'Could not determine transit location'))
            print(f"Layer {layer.id}: ✗ Could not determine location")
    
    # Summary
    print(f"\n=== Transit Location Migration Summary ===")
    print(f"Total transit-related layers: {total_count}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print(f"\nBreakdown by transfer type:")
    print(f"  Internal → Transit: {transit_stats['internal_to_transit']}")
    print(f"  Transit → Internal: {transit_stats['transit_to_internal']}")
    print(f"  Transit → Transit: {transit_stats['transit_to_transit']}")
    
    if failed_layers:
        print(f"\n=== Failed Transit Layers ===")
        for layer_id, reason in failed_layers:
            print(f"Layer {layer_id}: {reason}")
    
    print(f"\n=== Transit Migration Complete ===\n")
    
    return {
        'total': total_count,
        'successful': successful,
        'failed': failed,
        'failed_ids': [l[0] for l in failed_layers],
        'stats': transit_stats,
    }


def analyze_transit_locations(env):
    """
    Analyze and report on Transit locations in the system.
    
    This diagnostic function helps understand the current state of
    transit locations and their usage in stock moves and valuation layers.
    
    Args:
        env: Odoo environment
    
    Returns:
        dict: Analysis results
    """
    StockLocation = env['stock.location']
    StockMove = env['stock.move']
    ValuationLayer = env['stock.valuation.layer']
    
    print("\n=== Transit Location Analysis ===\n")
    
    # Find all transit locations
    transit_locations = StockLocation.search([('usage', '=', 'transit')])
    
    print(f"Found {len(transit_locations)} Transit locations:\n")
    
    for loc in transit_locations:
        print(f"  - {loc.name} (ID: {loc.id})")
        print(f"    Location: {loc.location_id.name if loc.location_id else 'None'}")
        print(f"    Company: {loc.company_id.name if loc.company_id else 'All'}")
        
        # Count moves involving this location
        moves_from = StockMove.search_count([
            ('location_id', '=', loc.id),
            ('state', '=', 'done'),
        ])
        moves_to = StockMove.search_count([
            ('location_dest_id', '=', loc.id),
            ('state', '=', 'done'),
        ])
        
        print(f"    Moves FROM: {moves_from}")
        print(f"    Moves TO: {moves_to}")
        
        # Count valuation layers
        layers = ValuationLayer.search_count([('location_id', '=', loc.id)])
        layers_missing = ValuationLayer.search_count([
            ('location_id', '=', False),
            '|',
            ('stock_move_id.location_id', '=', loc.id),
            ('stock_move_id.location_dest_id', '=', loc.id),
        ])
        
        print(f"    Valuation layers WITH location: {layers}")
        print(f"    Valuation layers MISSING location: {layers_missing}")
        print()
    
    # Overall statistics
    total_layers_missing = ValuationLayer.search_count([('location_id', '=', False)])
    
    # Transit-related moves without proper layer location
    transit_moves = StockMove.search([
        '|',
        ('location_id.usage', '=', 'transit'),
        ('location_dest_id.usage', '=', 'transit'),
        ('state', '=', 'done'),
    ])
    
    transit_layers_missing = 0
    for move in transit_moves:
        layers = ValuationLayer.search([
            ('stock_move_id', '=', move.id),
            ('location_id', '=', False),
        ])
        transit_layers_missing += len(layers)
    
    print(f"=== Overall Statistics ===")
    print(f"Total transit locations: {len(transit_locations)}")
    print(f"Total done moves involving transit: {len(transit_moves)}")
    print(f"Total layers missing location_id: {total_layers_missing}")
    print(f"Transit-related layers missing location_id: {transit_layers_missing}")
    print(f"\n=== Analysis Complete ===\n")
    
    return {
        'transit_locations': len(transit_locations),
        'transit_moves': len(transit_moves),
        'total_missing': total_layers_missing,
        'transit_missing': transit_layers_missing,
    }
