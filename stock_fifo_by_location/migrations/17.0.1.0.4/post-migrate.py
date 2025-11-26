# -*- coding: utf-8 -*-
"""
Post-migration script for stock_fifo_by_location 17.0.1.0.4

This script migrates existing location_id data to warehouse_id.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Post-migration: Convert location_id to warehouse_id in all records
    """
    _logger.info("Starting post-migration for stock_fifo_by_location 17.0.1.0.4")
    
    # Migrate stock.valuation.layer records
    _logger.info("Migrating stock.valuation.layer records from location_id to warehouse_id")
    
    cr.execute("""
        UPDATE stock_valuation_layer svl
        SET warehouse_id = sl.warehouse_id
        FROM stock_location sl
        WHERE svl.location_id = sl.id
        AND svl.warehouse_id IS NULL
        AND sl.warehouse_id IS NOT NULL
    """)
    
    migrated_layers = cr.rowcount
    _logger.info(f"Migrated {migrated_layers} stock.valuation.layer records")
    
    # Check for records without warehouse
    cr.execute("""
        SELECT COUNT(*) 
        FROM stock_valuation_layer 
        WHERE location_id IS NOT NULL 
        AND warehouse_id IS NULL
    """)
    
    unmigrated_layers = cr.fetchone()[0]
    if unmigrated_layers > 0:
        _logger.warning(f"Found {unmigrated_layers} valuation layers with location but no warehouse")
        _logger.warning("These layers have locations that are not assigned to any warehouse")
    
    # Migrate stock.valuation.layer.landed.cost records
    _logger.info("Migrating stock.valuation.layer.landed.cost records from location_id to warehouse_id")
    
    cr.execute("""
        UPDATE stock_valuation_layer_landed_cost svllc
        SET warehouse_id = sl.warehouse_id
        FROM stock_location sl
        WHERE svllc.location_id = sl.id
        AND svllc.warehouse_id IS NULL
        AND sl.warehouse_id IS NOT NULL
    """)
    
    migrated_lc = cr.rowcount
    _logger.info(f"Migrated {migrated_lc} stock.valuation.layer.landed.cost records")
    
    # Check for landed cost records without warehouse
    cr.execute("""
        SELECT COUNT(*) 
        FROM stock_valuation_layer_landed_cost 
        WHERE location_id IS NOT NULL 
        AND warehouse_id IS NULL
    """)
    
    unmigrated_lc = cr.fetchone()[0]
    if unmigrated_lc > 0:
        _logger.warning(f"Found {unmigrated_lc} landed cost records with location but no warehouse")
        _logger.warning("These records have locations that are not assigned to any warehouse")
    
    # Optional: Drop old location_id columns (commented out for safety)
    # Uncomment these lines after verifying migration success
    
    # _logger.info("Dropping old location_id columns (keeping for reference)")
    # cr.execute("ALTER TABLE stock_valuation_layer DROP COLUMN IF EXISTS location_id")
    # cr.execute("ALTER TABLE stock_valuation_layer_landed_cost DROP COLUMN IF EXISTS location_id")
    
    _logger.info("Post-migration completed successfully")
    _logger.info("=" * 80)
    _logger.info("MIGRATION SUMMARY:")
    _logger.info(f"  - Migrated {migrated_layers} valuation layers")
    _logger.info(f"  - Migrated {migrated_lc} landed cost records")
    if unmigrated_layers > 0 or unmigrated_lc > 0:
        _logger.info(f"  - WARNING: {unmigrated_layers + unmigrated_lc} records could not be migrated")
        _logger.info("  - These records have locations not assigned to any warehouse")
        _logger.info("  - Please review and manually assign warehouses to these locations")
    _logger.info("=" * 80)
