# -*- coding: utf-8 -*-
"""
Pre-migration script for stock_fifo_by_location 17.0.1.0.4

This script prepares the database for the migration from location-based to warehouse-based FIFO.
It adds the new warehouse_id column before the module update.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Pre-migration: Add warehouse_id column to stock.valuation.layer
    
    This must be done before the module update to avoid errors.
    """
    _logger.info("Starting pre-migration for stock_fifo_by_location 17.0.1.0.4")
    
    # Check if warehouse_id column already exists
    cr.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='stock_valuation_layer' 
        AND column_name='warehouse_id'
    """)
    
    if not cr.fetchone():
        _logger.info("Adding warehouse_id column to stock_valuation_layer")
        cr.execute("""
            ALTER TABLE stock_valuation_layer 
            ADD COLUMN warehouse_id INTEGER
        """)
        
        # Create index for performance
        cr.execute("""
            CREATE INDEX IF NOT EXISTS stock_valuation_layer_warehouse_id_index 
            ON stock_valuation_layer(warehouse_id)
        """)
    
    # Check if warehouse_id column exists in stock_valuation_layer_landed_cost
    cr.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='stock_valuation_layer_landed_cost' 
        AND column_name='warehouse_id'
    """)
    
    if not cr.fetchone():
        _logger.info("Adding warehouse_id column to stock_valuation_layer_landed_cost")
        cr.execute("""
            ALTER TABLE stock_valuation_layer_landed_cost 
            ADD COLUMN warehouse_id INTEGER
        """)
        
        # Create index for performance
        cr.execute("""
            CREATE INDEX IF NOT EXISTS stock_valuation_layer_landed_cost_warehouse_id_index 
            ON stock_valuation_layer_landed_cost(warehouse_id)
        """)
    
    _logger.info("Pre-migration completed successfully")
