#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script for Transit Location Migration

This script tests the transit location migration functionality in the
stock_fifo_by_location module.

Usage:
    python test_transit_migration.py
    
Or in Odoo shell:
    odoo-bin shell -d your_database
    >>> exec(open('test_transit_migration.py').read())
"""

import sys
import os

# Try to import Odoo if running as standalone
try:
    import odoo
    from odoo import api, SUPERUSER_ID
except ImportError:
    print("Error: Odoo not found. Please run this script using odoo-bin shell")
    sys.exit(1)


def test_analyze_transit_locations(env):
    """Test the analyze_transit_locations function"""
    print("\n" + "="*60)
    print("TEST 1: Analyze Transit Locations")
    print("="*60)
    
    from odoo.addons.stock_fifo_by_location.migrations import populate_location_id
    
    result = populate_location_id.analyze_transit_locations(env)
    
    print("\n✓ Analysis completed successfully")
    print(f"  Transit locations found: {result['transit_locations']}")
    print(f"  Transit moves found: {result['transit_moves']}")
    print(f"  Total missing locations: {result['total_missing']}")
    print(f"  Transit missing locations: {result['transit_missing']}")
    
    return result


def test_populate_transit_layers(env):
    """Test the populate_transit_location_layers function"""
    print("\n" + "="*60)
    print("TEST 2: Populate Transit Location Layers")
    print("="*60)
    
    from odoo.addons.stock_fifo_by_location.migrations import populate_location_id
    
    # Count before
    ValuationLayer = env['stock.valuation.layer']
    before_count = ValuationLayer.search_count([('location_id', '=', False)])
    print(f"\nLayers without location BEFORE migration: {before_count}")
    
    # Run migration
    result = populate_location_id.populate_transit_location_layers(env)
    
    # Count after
    after_count = ValuationLayer.search_count([('location_id', '=', False)])
    print(f"\nLayers without location AFTER migration: {after_count}")
    
    print("\n✓ Transit migration completed")
    print(f"  Total processed: {result['total']}")
    print(f"  Successful: {result['successful']}")
    print(f"  Failed: {result['failed']}")
    
    if result['stats']:
        print("\n  Transfer type breakdown:")
        for key, value in result['stats'].items():
            print(f"    {key}: {value}")
    
    return result


def test_full_migration(env):
    """Test the main populate_location_id function"""
    print("\n" + "="*60)
    print("TEST 3: Full Location ID Migration")
    print("="*60)
    
    from odoo.addons.stock_fifo_by_location.migrations import populate_location_id
    
    # Count before
    ValuationLayer = env['stock.valuation.layer']
    before_count = ValuationLayer.search_count([('location_id', '=', False)])
    print(f"\nLayers without location BEFORE migration: {before_count}")
    
    if before_count == 0:
        print("\n✓ No layers need migration - all layers already have location_id")
        return {'total': 0, 'successful': 0, 'failed': 0}
    
    # Run migration
    result = populate_location_id.populate_location_id(env)
    
    # Count after
    after_count = ValuationLayer.search_count([('location_id', '=', False)])
    print(f"\nLayers without location AFTER migration: {after_count}")
    
    print("\n✓ Full migration completed")
    print(f"  Total processed: {result['total']}")
    print(f"  Successful: {result['successful']}")
    print(f"  Failed: {result['failed']}")
    
    if result['failed'] > 0:
        print(f"\n  ⚠ {result['failed']} layers failed - review these manually:")
        print(f"  Failed layer IDs: {result.get('failed_ids', [])[:10]}...")
    
    return result


def test_context_migration(env):
    """Test the context-based migration function"""
    print("\n" + "="*60)
    print("TEST 4: Context-Based Migration")
    print("="*60)
    
    from odoo.addons.stock_fifo_by_location.migrations import populate_location_id
    
    # Count before
    ValuationLayer = env['stock.valuation.layer']
    before_count = ValuationLayer.search_count([('location_id', '=', False)])
    print(f"\nLayers without location BEFORE migration: {before_count}")
    
    if before_count == 0:
        print("\n✓ No layers need migration")
        return {'migrated': 0, 'skipped': 0}
    
    # Run migration
    result = populate_location_id.populate_location_id_by_context(env, only_missing=True)
    
    # Count after
    after_count = ValuationLayer.search_count([('location_id', '=', False)])
    print(f"\nLayers without location AFTER migration: {after_count}")
    
    print("\n✓ Context migration completed")
    print(f"  Migrated: {result['migrated']}")
    print(f"  Skipped: {result['skipped']}")
    
    return result


def test_verify_transit_consistency(env):
    """Verify transit location assignments are correct"""
    print("\n" + "="*60)
    print("TEST 5: Verify Transit Location Consistency")
    print("="*60)
    
    ValuationLayer = env['stock.valuation.layer']
    StockMove = env['stock.move']
    
    # Find all transit-related layers
    transit_layers = ValuationLayer.search([
        ('location_id.usage', '=', 'transit'),
    ])
    
    print(f"\nFound {len(transit_layers)} layers with transit locations")
    
    inconsistent = 0
    consistent = 0
    
    for layer in transit_layers:
        if not layer.stock_move_id:
            continue
        
        move = layer.stock_move_id
        source_usage = move.location_id.usage if move.location_id else None
        dest_usage = move.location_dest_id.usage if move.location_dest_id else None
        
        is_consistent = False
        
        # Check consistency based on layer quantity
        if layer.quantity > 0:
            # Positive: location should be destination
            is_consistent = (layer.location_id.id == move.location_dest_id.id)
        elif layer.quantity < 0:
            # Negative: location should be source (if transit) or special rules apply
            if source_usage == 'transit':
                is_consistent = (layer.location_id.id == move.location_id.id)
            elif dest_usage == 'transit':
                is_consistent = (layer.location_id.id == move.location_dest_id.id)
        
        if is_consistent:
            consistent += 1
        else:
            inconsistent += 1
            print(f"  ⚠ Inconsistent: Layer {layer.id}, Move {move.id}")
            print(f"    Qty: {layer.quantity}, Layer Loc: {layer.location_id.name}")
            print(f"    Move: {move.location_id.name} ({source_usage}) → {move.location_dest_id.name} ({dest_usage})")
    
    print(f"\n✓ Verification completed")
    print(f"  Consistent: {consistent}")
    print(f"  Inconsistent: {inconsistent}")
    
    if inconsistent == 0:
        print("\n  ✓ All transit layers are consistent!")
    else:
        print(f"\n  ⚠ {inconsistent} layers need review")
    
    return {'consistent': consistent, 'inconsistent': inconsistent}


def run_all_tests():
    """Run all migration tests"""
    print("\n" + "#"*60)
    print("# Transit Location Migration Test Suite")
    print("#"*60)
    
    # Get environment
    if 'env' in globals():
        test_env = globals()['env']
    else:
        # Try to get from Odoo context
        try:
            import odoo
            from odoo import api, SUPERUSER_ID
            db_name = os.environ.get('ODOO_DATABASE', 'your_database')
            test_env = api.Environment(odoo.registry(db_name).cursor(), SUPERUSER_ID, {})
        except Exception as e:
            print(f"\nError: Could not create environment: {e}")
            print("Please run this script using: odoo-bin shell -d your_database")
            return
    
    results = {}
    
    try:
        # Test 1: Analyze
        results['analyze'] = test_analyze_transit_locations(test_env)
        
        # Test 2: Transit-specific migration
        results['transit_migrate'] = test_populate_transit_layers(test_env)
        
        # Test 3: Full migration (only if there are still missing)
        ValuationLayer = test_env['stock.valuation.layer']
        remaining = ValuationLayer.search_count([('location_id', '=', False)])
        
        if remaining > 0:
            results['full_migrate'] = test_full_migration(test_env)
        else:
            print("\n✓ Skipping full migration - no layers need migration")
            results['full_migrate'] = {'total': 0, 'successful': 0, 'failed': 0}
        
        # Test 4: Verify consistency
        results['verify'] = test_verify_transit_consistency(test_env)
        
        # Summary
        print("\n" + "#"*60)
        print("# Test Suite Summary")
        print("#"*60)
        print(f"\n✓ All tests completed")
        print(f"\nResults:")
        print(f"  Transit locations: {results['analyze']['transit_locations']}")
        print(f"  Transit layers migrated: {results['transit_migrate']['successful']}")
        print(f"  Total layers migrated: {results['full_migrate']['successful']}")
        print(f"  Consistent transit layers: {results['verify']['consistent']}")
        
        if results['verify']['inconsistent'] > 0:
            print(f"\n  ⚠ Warning: {results['verify']['inconsistent']} inconsistent layers found")
        else:
            print(f"\n  ✓ All transit layers are consistent!")
        
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Commit if in transaction
        if hasattr(test_env, 'cr'):
            test_env.cr.commit()
    
    print("\n" + "#"*60)


if __name__ == '__main__':
    run_all_tests()
