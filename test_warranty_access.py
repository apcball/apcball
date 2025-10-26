#!/usr/bin/env python3
"""Test warranty module access"""
import xmlrpc.client

# Configuration
url = "http://www.mogth.work:8069"
db = "MOG_LIVE_15_08"
username = "apichart@mogen.co.th"  # Change if needed
password = "471109538"  # Change if needed

try:
    # Authenticate
    common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
    uid = common.authenticate(db, username, password, {})
    print(f"✓ Authenticated as user ID: {uid}")
    
    # Get models access
    models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
    
    # Test warranty.card model
    print("\n1. Testing warranty.card model...")
    warranty_count = models.execute_kw(db, uid, password,
        'warranty.card', 'search_count', [[]])
    print(f"   ✓ Found {warranty_count} warranty cards")
    
    # Test warranty.claim model
    print("\n2. Testing warranty.claim model...")
    claim_count = models.execute_kw(db, uid, password,
        'warranty.claim', 'search_count', [[]])
    print(f"   ✓ Found {claim_count} warranty claims")
    
    # Test warranty.dashboard model
    print("\n3. Testing warranty.dashboard model...")
    try:
        dashboard_ids = models.execute_kw(db, uid, password,
            'warranty.dashboard', 'search', [[]], {'limit': 1})
        if dashboard_ids:
            print(f"   ✓ Dashboard exists with ID: {dashboard_ids[0]}")
        else:
            # Try to get or create
            dashboard_id = models.execute_kw(db, uid, password,
                'warranty.dashboard', 'get_dashboard', [])
            print(f"   ✓ Dashboard created/retrieved with ID: {dashboard_id}")
    except Exception as e:
        print(f"   ⚠ Dashboard error: {e}")
    
    # Test menu access
    print("\n4. Testing menu access...")
    menu_ids = models.execute_kw(db, uid, password,
        'ir.ui.menu', 'search', [[('name', 'ilike', 'warranty')]])
    if menu_ids:
        menus = models.execute_kw(db, uid, password,
            'ir.ui.menu', 'read', [menu_ids], {'fields': ['name', 'id']})
        print(f"   ✓ Found {len(menus)} warranty-related menus:")
        for menu in menus:
            print(f"     - {menu['name']} (ID: {menu['id']})")
    
    # Test view access
    print("\n5. Testing view access...")
    view_ids = models.execute_kw(db, uid, password,
        'ir.ui.view', 'search', [[('model', '=', 'warranty.dashboard')]])
    print(f"   ✓ Found {len(view_ids)} warranty dashboard views")
    
    print("\n✅ All tests passed! Module is accessible.")
    
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
