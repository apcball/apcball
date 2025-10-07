#!/usr/bin/env python3
"""
Cleanup script for employee_advance wizard tables
This script removes orphaned wizard records that might cause constraint errors during module upgrade.
"""

import psycopg2
import sys

def cleanup_wizard_tables():
    """Clean up wizard tables to prevent constraint errors"""
    try:
        # Connect to the database (adjust connection parameters as needed)
        conn = psycopg2.connect(
            host="localhost",
            database="odoo17",
            user="odoo",  # Adjust as needed
            password="odoo"  # Adjust as needed
        )
        
        cursor = conn.cursor()
        
        print("🧹 Starting wizard table cleanup...")
        
        # Clean up advance_refill_base_wizard table
        cursor.execute("DELETE FROM advance_refill_base_wizard;")
        refill_deleted = cursor.rowcount
        print(f"   Deleted {refill_deleted} records from advance_refill_base_wizard table")
        
        # Clean up advance_settlement_wizard table  
        cursor.execute("DELETE FROM advance_settlement_wizard;")
        settlement_deleted = cursor.rowcount
        print(f"   Deleted {settlement_deleted} records from advance_settlement_wizard table")
        
        # Commit the changes
        conn.commit()
        print("✅ Wizard table cleanup completed successfully!")
        
    except Exception as e:
        print(f"❌ Error during cleanup: {str(e)}")
        if 'conn' in locals():
            conn.rollback()
        return False
    finally:
        if 'conn' in locals():
            conn.close()
    
    return True

if __name__ == "__main__":
    print("Employee Advance Wizard Cleanup Tool")
    print("====================================")
    cleanup_wizard_tables()