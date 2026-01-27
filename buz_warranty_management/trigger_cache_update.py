#!/usr/bin/env python3
"""
Script to trigger cache update via XML-RPC
"""
import xmlrpc.client

# Configuration
url = 'https://mogdev.work'
db = 'MOG_LIVE_15_08'
username = 'admin'  # Change this
password = 'your_password'  # Change this

try:
    # Connect
    common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
    uid = common.authenticate(db, username, password, {})
    
    if not uid:
        print("Authentication failed!")
        exit(1)
    
    models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
    
    # Get cache
    cache_ids = models.execute_kw(db, uid, password,
        'warranty.dashboard.cache', 'search',
        [[]], {'limit': 1})
    
    if cache_ids:
        cache_id = cache_ids[0]
        print(f"Found cache: {cache_id}")
        
        # Trigger update
        models.execute_kw(db, uid, password,
            'warranty.dashboard.cache', 'write',
            [[cache_id], {'cache_status': 'expired'}])
        
        print("Triggered cache update")
        
        # Call update method
        models.execute_kw(db, uid, password,
            'warranty.dashboard.cache', '_update_all_metrics',
            [[cache_id]])
        
        print("Cache updated successfully!")
        
        # Check result
        cache_data = models.execute_kw(db, uid, password,
            'warranty.dashboard.cache', 'read',
            [[cache_id], ['cache_status', 'total_warranties', 'last_update']])
        
        print(f"Cache status: {cache_data}")
    else:
        print("No cache found")
        
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
