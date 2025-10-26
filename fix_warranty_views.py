#!/usr/bin/env python3
"""
Fix warranty management views in database
This script will:
1. Delete orphaned views
2. Reload module views
3. Test accessibility
"""

import sys
import os

# Add Odoo to path
sys.path.append('/opt/instance1/odoo17')

import odoo
from odoo import api, SUPERUSER_ID

# Configuration
CONFIG_FILE = '/etc/instance1.conf'
DATABASE = 'MOG_LIVE_15_08'

def fix_warranty_views():
    """Fix warranty views"""
    odoo.tools.config.parse_config(['-c', CONFIG_FILE])
    
    with odoo.api.Environment.manage():
        registry = odoo.registry(DATABASE)
        with registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            
            print("=" * 60)
            print("Fixing Warranty Management Views")
            print("=" * 60)
            
            # 1. Check for existing views
            print("\n1. Checking existing views...")
            views = env['ir.ui.view'].search([
                ('model', 'in', ['warranty.dashboard', 'warranty.card', 'warranty.claim'])
            ])
            print(f"   Found {len(views)} warranty-related views")
            
            # 2. Check for invalid views
            print("\n2. Checking for invalid views...")
            invalid_views = []
            for view in views:
                try:
                    # Try to read the view
                    view.read(['arch_db'])
                except Exception as e:
                    print(f"   ⚠ Invalid view: {view.name} (ID: {view.id}) - {e}")
                    invalid_views.append(view)
            
            if invalid_views:
                print(f"\n   Found {len(invalid_views)} invalid views. Deleting...")
                for view in invalid_views:
                    try:
                        view.unlink()
                        print(f"   ✓ Deleted view: {view.name}")
                    except Exception as e:
                        print(f"   ✗ Failed to delete view: {view.name} - {e}")
            else:
                print("   ✓ No invalid views found")
            
            # 3. Upgrade the module to reload views
            print("\n3. Upgrading module to reload views...")
            module = env['ir.module.module'].search([
                ('name', '=', 'buz_warranty_management')
            ], limit=1)
            
            if module:
                print(f"   Module state: {module.state}")
                if module.state == 'installed':
                    print("   Triggering module update...")
                    module.button_immediate_upgrade()
                    print("   ✓ Module upgraded successfully")
                else:
                    print(f"   ⚠ Module not installed. Current state: {module.state}")
            else:
                print("   ✗ Module not found in database")
            
            # 4. Test dashboard access
            print("\n4. Testing dashboard access...")
            try:
                dashboard = env['warranty.dashboard'].get_dashboard()
                print(f"   ✓ Dashboard accessible (ID: {dashboard.id})")
                
                # Read dashboard fields
                dashboard_data = dashboard.read([
                    'total_warranties',
                    'active_warranties',
                    'expired_warranties',
                    'cache_status'
                ])
                print(f"   Dashboard data: {dashboard_data}")
                
            except Exception as e:
                print(f"   ✗ Dashboard error: {e}")
                import traceback
                traceback.print_exc()
            
            # 5. Commit changes
            cr.commit()
            
            print("\n" + "=" * 60)
            print("✅ Fix completed!")
            print("=" * 60)
            print("\nPlease restart the Odoo service:")
            print("  sudo systemctl restart instance1")
            print("=" * 60)

if __name__ == '__main__':
    try:
        fix_warranty_views()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
