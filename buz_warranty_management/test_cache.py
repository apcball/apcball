#!/usr/bin/env python3
"""
Simple test script to check cache functionality
"""

# Test the SQL queries directly
import psycopg2
from datetime import datetime, timedelta

# Database connection parameters - adjust as needed
db_params = {
    'host': 'localhost',
    'database': 'odoo17',
    'user': 'odoo17',
    'password': 'odoo17',
}

try:
    # Connect to database
    conn = psycopg2.connect(**db_params)
    cur = conn.cursor()
    
    print("Testing warranty_claim table access...")
    
    # Test if table exists
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = 'warranty_claim'
        )
    """)
    table_exists = cur.fetchone()[0]
    print(f"warranty_claim table exists: {table_exists}")
    
    if table_exists:
        # Test claims this month query
        today = datetime.now().date()
        first_day_this_month = today.replace(day=1)
        
        cur.execute("""
            SELECT COUNT(*) FROM warranty_claim 
            WHERE claim_date >= %s
        """, (first_day_this_month,))
        claims_this_month = cur.fetchone()[0]
        print(f"Claims this month: {claims_this_month}")
        
        # Test claims last month query
        if today.month == 1:
            first_day_last_month = today.replace(year=today.year-1, month=12, day=1)
            last_day_last_month = today.replace(day=1) - timedelta(days=1)
        else:
            first_day_last_month = today.replace(month=today.month-1, day=1)
            last_day_last_month = today.replace(day=1) - timedelta(days=1)
        
        cur.execute("""
            SELECT COUNT(*) FROM warranty_claim 
            WHERE claim_date >= %s AND claim_date <= %s
        """, (first_day_last_month, last_day_last_month))
        claims_last_month = cur.fetchone()[0]
        print(f"Claims last month: {claims_last_month}")
        
        # Test warranty card queries
        cur.execute("SELECT COUNT(*) FROM warranty_card")
        total_warranties = cur.fetchone()[0]
        print(f"Total warranties: {total_warranties}")
        
        cur.execute("SELECT COUNT(*) FROM warranty_card WHERE state = 'active'")
        active_warranties = cur.fetchone()[0]
        print(f"Active warranties: {active_warranties}")
    
    conn.close()
    print("Database test completed successfully")
    
except Exception as e:
    print(f"Error: {str(e)}")
    import traceback
    traceback.print_exc()