#!/usr/bin/env python3
"""
Test script to verify transit locations are properly loaded in the warehouse sidebar
"""

import sys
import os

# Add the Odoo path to sys.path
sys.path.append('/opt/instance1/odoo17')

import odoo
from odoo import api, registry

def test_transit_locations():
    """Test that transit locations are properly loaded"""
    
    # Database connection info
    db_name = 'odoo17'
    username = 'admin'
    password = 'admin'
    
    try:
        # Initialize registry
        registry.Registry(db_name).check_signaling()
        
        # Connect to Odoo
        odoo.tools.config['addons_path'] = ['/opt/instance1/odoo17/addons', '/opt/instance1/odoo17/custom-addons']
        
        with odoo.api.Environment.manage():
            # Get the environment
            env = api.Environment(registry.Registry(db_name).cursor(), 1, {})
            
            # Test the new method
            print("Testing get_warehouses_with_locations method...")
            warehouses = env['stock.current.report'].get_warehouses_with_locations()
            
            print(f"\nFound {len(warehouses)} warehouses")
            
            for warehouse in warehouses:
                print(f"\nWarehouse: {warehouse['name']}")
                print(f"  Internal locations: {len(warehouse.get('internal_locations', []))}")
                print(f"  Transit locations: {len(warehouse.get('transit_locations', []))}")
                
                # Show internal locations
                if warehouse.get('internal_locations'):
                    print("  Internal location details:")
                    for loc in warehouse['internal_locations'][:3]:  # Show first 3
                        print(f"    - {loc['name']} (Products: {loc.get('product_count', 0)})")
                
                # Show transit locations
                if warehouse.get('transit_locations'):
                    print("  Transit location details:")
                    for loc in warehouse['transit_locations'][:3]:  # Show first 3
                        print(f"    - {loc['name']} (Products: {loc.get('product_count', 0)})")
            
            print("\n✅ Test completed successfully!")
            return True
            
    except Exception as e:
        print(f"\n❌ Error during test: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_transit_locations()