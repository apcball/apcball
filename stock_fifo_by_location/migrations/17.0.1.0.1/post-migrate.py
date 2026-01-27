# -*- coding: utf-8 -*-
"""
Post-migration script to fix foreign key constraint on stock.valuation.layer.landed.cost

This migration changes the ondelete behavior of valuation_adjustment_line_id
from RESTRICT to CASCADE to allow proper deletion of landed cost records.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Update foreign key constraint to reference correct table and allow cascading deletes.
    
    Changes:
    1. Update reference from stock_landed_cost_lines to stock_valuation_adjustment_lines
    2. Set ondelete to CASCADE
    """
    _logger.info("Starting migration to fix valuation_adjustment_line_id constraint")
    
    # Check if constraint exists and get current configuration
    cr.execute("""
        SELECT 
            con.conname,
            cls.relname as foreign_table,
            con.confdeltype
        FROM pg_constraint con
        JOIN pg_class cls ON cls.oid = con.confrelid
        WHERE con.conname = 'stock_valuation_layer_landed__valuation_adjustment_line_id_fkey'
    """)
    
    constraint = cr.fetchone()
    
    if constraint:
        constraint_name, foreign_table, current_delete_type = constraint
        _logger.info(f"Current constraint: {constraint_name} -> {foreign_table}, delete type: {current_delete_type}")
        
        # Check if update is needed
        needs_update = (
            foreign_table != 'stock_valuation_adjustment_lines' or 
            current_delete_type != 'c'
        )
        
        if needs_update:
            _logger.info(f"Updating constraint (current table: {foreign_table}, should be: stock_valuation_adjustment_lines)")
            
            try:
                # Drop existing constraint
                cr.execute("""
                    ALTER TABLE stock_valuation_layer_landed_cost 
                    DROP CONSTRAINT IF EXISTS stock_valuation_layer_landed__valuation_adjustment_line_id_fkey
                """)
                
                # Add new constraint with correct reference and CASCADE
                cr.execute("""
                    ALTER TABLE stock_valuation_layer_landed_cost 
                    ADD CONSTRAINT stock_valuation_layer_landed__valuation_adjustment_line_id_fkey 
                    FOREIGN KEY (valuation_adjustment_line_id) 
                    REFERENCES stock_valuation_adjustment_lines(id) 
                    ON DELETE CASCADE
                """)
                
                _logger.info("Successfully updated constraint")
                
            except Exception as e:
                _logger.error(f"Error updating constraint: {e}")
                raise
        else:
            _logger.info("Constraint already correct, no changes needed")
    else:
        _logger.warning("Constraint not found, it will be created during module upgrade")
    
    _logger.info("Migration completed successfully")
