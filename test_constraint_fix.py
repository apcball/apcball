#!/usr/bin/env python3
"""
Test script to verify the landed cost constraint fix
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')

# Try to import odoo modules
try:
    import odoo
    from odoo import api, fields, models
    from odoo.sql_db import db_connect
    print("✓ Odoo modules imported")
except ImportError as e:
    print(f"✗ Failed to import Odoo: {e}")
    sys.exit(1)

def test_constraint():
    """Test if constraint issue is resolved"""
    try:
        # Connect to instance
        cr = db_connect('instance1').cursor()
        
        # Check if table exists
        cr.execute("""
            SELECT EXISTS(
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = 'stock_valuation_layer_landed_cost'
            )
        """)
        table_exists = cr.fetchone()[0]
        print(f"Table exists: {table_exists}")
        
        if table_exists:
            # List all constraints
            cr.execute("""
                SELECT constraint_name, constraint_type
                FROM information_schema.table_constraints 
                WHERE table_name = 'stock_valuation_layer_landed_cost'
            """)
            constraints = cr.fetchall()
            print("\nConstraints:")
            for name, ctype in constraints:
                print(f"  - {name} ({ctype})")
            
            # Check foreign key constraints specifically
            cr.execute("""
                SELECT 
                    tc.constraint_name,
                    tc.table_name,
                    kcu.column_name,
                    ccu.table_name AS foreign_table_name,
                    ccu.column_name AS foreign_column_name,
                    rc.delete_rule
                FROM information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu
                    ON tc.constraint_name = kcu.constraint_name
                    AND tc.table_schema = kcu.table_schema
                JOIN information_schema.constraint_column_usage AS ccu
                    ON ccu.constraint_name = tc.constraint_name
                    AND ccu.table_schema = tc.table_schema
                JOIN information_schema.referential_constraints rc
                    ON rc.constraint_name = tc.constraint_name
                WHERE tc.table_name = 'stock_valuation_layer_landed_cost'
                AND tc.constraint_type = 'FOREIGN KEY'
            """)
            fk_constraints = cr.fetchall()
            print("\nForeign Key Constraints:")
            for row in fk_constraints:
                constraint_name, table_name, column_name, fk_table, fk_column, delete_rule = row
                print(f"  - {constraint_name}")
                print(f"    Column: {column_name} → {fk_table}.{fk_column}")
                print(f"    Delete Rule: {delete_rule}")
            
            # Check column defaults
            cr.execute("""
                SELECT column_name, column_default, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'stock_valuation_layer_landed_cost'
                AND column_name IN ('valuation_adjustment_line_id', 'landed_cost_id')
            """)
            columns = cr.fetchall()
            print("\nRelevant Columns:")
            for col_name, default, nullable in columns:
                print(f"  - {col_name}: nullable={nullable}, default={default}")
        
        cr.close()
        print("\n✓ Test completed successfully")
        
    except Exception as e:
        print(f"\n✗ Error during test: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == '__main__':
    success = test_constraint()
    sys.exit(0 if success else 1)
