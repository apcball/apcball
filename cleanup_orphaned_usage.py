#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Cleanup script for orphaned stock valuation layer usage records
Run this after upgrading modules if you had regenerations before the fix
"""

import sys
import xmlrpc.client

def connect_to_odoo(url, db, username, password):
    """Connect to Odoo and return uid and models proxy"""
    try:
        common = xmlrpc.client.ServerProxy('{}/xmlrpc/2/common'.format(url))
        uid = common.authenticate(db, username, password, {})
        
        if not uid:
            print("✗ Authentication failed")
            return None, None
        
        models = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(url))
        print(f"✓ Connected to Odoo (User ID: {uid})")
        return uid, models
        
    except Exception as e:
        print(f"✗ Connection error: {str(e)}")
        return None, None

def find_orphaned_records(models, db, uid, password):
    """Find orphaned usage records"""
    print("\nSearching for orphaned usage records...")
    
    try:
        # Get all usage records
        usage_ids = models.execute_kw(
            db, uid, password,
            'stock.valuation.layer.usage', 'search',
            [[]]
        )
        
        if not usage_ids:
            print("✓ No usage records found in database")
            return []
        
        print(f"Found {len(usage_ids)} total usage records")
        
        # Get all valid SVL IDs
        svl_ids = models.execute_kw(
            db, uid, password,
            'stock.valuation.layer', 'search',
            [[]]
        )
        
        print(f"Found {len(svl_ids)} total SVL records")
        
        # Check each usage record
        orphaned_ids = []
        
        usage_records = models.execute_kw(
            db, uid, password,
            'stock.valuation.layer.usage', 'read',
            [usage_ids],
            {'fields': ['id', 'stock_valuation_layer_id', 'dest_stock_valuation_layer_id', 'stock_move_id']}
        )
        
        for usage in usage_records:
            is_orphaned = False
            reasons = []
            
            # Check source SVL
            svl_id = usage.get('stock_valuation_layer_id')
            if svl_id:
                if svl_id[0] not in svl_ids:
                    is_orphaned = True
                    reasons.append(f"Source SVL {svl_id[0]} not found")
            
            # Check destination SVL
            dest_svl_id = usage.get('dest_stock_valuation_layer_id')
            if dest_svl_id and dest_svl_id[0]:
                if dest_svl_id[0] not in svl_ids:
                    is_orphaned = True
                    reasons.append(f"Dest SVL {dest_svl_id[0]} not found")
            
            if is_orphaned:
                orphaned_ids.append({
                    'id': usage['id'],
                    'reasons': reasons,
                    'stock_move_id': usage.get('stock_move_id', [False, ''])[1]
                })
        
        if orphaned_ids:
            print(f"\n⚠ Found {len(orphaned_ids)} orphaned usage records:")
            for record in orphaned_ids[:10]:  # Show first 10
                print(f"  - ID {record['id']}: {', '.join(record['reasons'])}")
            
            if len(orphaned_ids) > 10:
                print(f"  ... and {len(orphaned_ids) - 10} more")
        else:
            print("✓ No orphaned usage records found")
        
        return orphaned_ids
        
    except Exception as e:
        print(f"✗ Error searching for orphaned records: {str(e)}")
        return []

def cleanup_orphaned_records(models, db, uid, password, orphaned_ids, dry_run=True):
    """Delete orphaned usage records"""
    if not orphaned_ids:
        print("\nNo orphaned records to clean up")
        return True
    
    ids_to_delete = [r['id'] for r in orphaned_ids]
    
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Cleaning up {len(ids_to_delete)} orphaned records...")
    
    if dry_run:
        print("\n⚠ DRY RUN MODE - No records will be deleted")
        print(f"Would delete {len(ids_to_delete)} usage records:")
        for record in orphaned_ids[:10]:
            print(f"  - Usage ID {record['id']}: {', '.join(record['reasons'])}")
        
        if len(orphaned_ids) > 10:
            print(f"  ... and {len(ids_to_delete) - 10} more")
        
        print("\nTo actually delete these records, run with --execute flag")
        return True
    
    try:
        # Delete records in batches of 100
        batch_size = 100
        deleted_count = 0
        
        for i in range(0, len(ids_to_delete), batch_size):
            batch = ids_to_delete[i:i + batch_size]
            
            models.execute_kw(
                db, uid, password,
                'stock.valuation.layer.usage', 'unlink',
                [batch]
            )
            
            deleted_count += len(batch)
            print(f"  Deleted {deleted_count}/{len(ids_to_delete)} records...")
        
        print(f"\n✓ Successfully deleted {deleted_count} orphaned records")
        return True
        
    except Exception as e:
        print(f"\n✗ Error deleting orphaned records: {str(e)}")
        return False

def main():
    """Main cleanup function"""
    print("=" * 70)
    print("Stock Valuation Layer Usage - Orphaned Records Cleanup")
    print("=" * 70)
    print()
    
    # Check arguments
    if len(sys.argv) < 5:
        print("Usage:")
        print("  Dry run (preview):  python3 cleanup_orphaned_usage.py <url> <db> <user> <pass>")
        print("  Execute cleanup:    python3 cleanup_orphaned_usage.py <url> <db> <user> <pass> --execute")
        print()
        print("Example:")
        print("  python3 cleanup_orphaned_usage.py http://localhost:8069 my_db admin admin")
        print("  python3 cleanup_orphaned_usage.py http://localhost:8069 my_db admin admin --execute")
        print()
        sys.exit(1)
    
    url = sys.argv[1]
    db = sys.argv[2]
    username = sys.argv[3]
    password = sys.argv[4]
    execute_mode = '--execute' in sys.argv
    
    print(f"URL: {url}")
    print(f"Database: {db}")
    print(f"Username: {username}")
    print(f"Mode: {'EXECUTE' if execute_mode else 'DRY RUN'}")
    print()
    
    # Connect to Odoo
    uid, models = connect_to_odoo(url, db, username, password)
    if not uid or not models:
        sys.exit(1)
    
    # Find orphaned records
    orphaned_records = find_orphaned_records(models, db, uid, password)
    
    if not orphaned_records:
        print()
        print("✓ Database is clean - no orphaned records found")
        print()
        sys.exit(0)
    
    # Cleanup
    success = cleanup_orphaned_records(models, db, uid, password, orphaned_records, dry_run=not execute_mode)
    
    print()
    print("=" * 70)
    if success:
        if execute_mode:
            print("✓ Cleanup completed successfully")
            print()
            print("Verify the cleanup:")
            print(f"  python3 test_stock_layer_compatibility.py {url} {db} {username} {password}")
        else:
            print("✓ Dry run completed - No changes made")
            print()
            print("To execute the cleanup:")
            print(f"  python3 cleanup_orphaned_usage.py {url} {db} {username} {password} --execute")
    else:
        print("✗ Cleanup failed - Please check the errors above")
    
    print("=" * 70)
    print()
    
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()
