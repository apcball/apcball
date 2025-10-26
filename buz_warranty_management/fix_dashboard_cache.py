#!/usr/bin/env python3
"""
Script to fix the warranty dashboard cache issue
"""
import os
import sys

# Add the Odoo path
odoo_path = '/opt/instance1/odoo17'
if odoo_path not in sys.path:
    sys.path.insert(0, odoo_path)

import odoo
from odoo import api, registry

def fix_dashboard_cache():
    """Fix the dashboard cache by clearing and rebuilding it"""
    db_name = 'MOG_LIVE_15_08'
    
    try:
        # Use the correct way to get registry
        from odoo.modules import registry
        reg = registry.Registry.new(db_name)
        
        with reg.cursor() as cr:
            env = api.Environment(cr, 1, {})
            
            # Clear existing cache
            cache_records = env['warranty.dashboard.cache'].search([])
            if cache_records:
                print(f"Found {len(cache_records)} cache records, clearing them...")
                cache_records.unlink()
            
            # Create new cache and update it
            print("Creating new cache record...")
            cache = env['warranty.dashboard.cache'].create({})
            
            print("Updating cache metrics...")
            cache._update_all_metrics()
            
            print("Dashboard cache successfully updated!")
            print(f"Cache status: {cache.cache_status}")
            print(f"Claims this month: {cache.claims_this_month}")
            print(f"Claims last month: {cache.claims_last_month}")
            
    except Exception as e:
        print(f"Error fixing dashboard cache: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    fix_dashboard_cache()