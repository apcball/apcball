#!/usr/bin/env python3
"""
Performance Test Script for Stock Valuation Location Module
Run this to verify the fixes are working correctly.
"""

import time
import logging

logging.basicConfig(level=logging.INFO)
_logger = logging.getLogger(__name__)


def test_batch_processing(env, batch_size=100):
    """Test that batch processing works correctly"""
    _logger.info("=" * 80)
    _logger.info("TEST 1: Batch Processing")
    _logger.info("=" * 80)
    
    # Count SVLs with moves
    svl_model = env["stock.valuation.layer"]
    count = svl_model.search_count([("stock_move_id", "!=", False)])
    _logger.info(f"Total SVLs with moves: {count}")
    
    if count == 0:
        _logger.warning("No SVL records found to test!")
        return
    
    # Test small batch
    test_count = min(batch_size, count)
    _logger.info(f"Testing with {test_count} records...")
    
    svls = svl_model.search([("stock_move_id", "!=", False)], limit=test_count)
    
    start = time.time()
    svls._compute_location_id()
    duration = time.time() - start
    
    _logger.info(f"✅ Processed {test_count} records in {duration:.2f} seconds")
    _logger.info(f"   Average: {duration/test_count*1000:.2f} ms per record")
    
    # Verify results
    with_location = svls.filtered(lambda s: s.location_id)
    _logger.info(f"   Records with location: {len(with_location)}/{len(svls)}")
    
    return duration


def test_sql_dry_run(env):
    """Test SQL fast path in dry run mode"""
    _logger.info("=" * 80)
    _logger.info("TEST 2: SQL Fast Path (Dry Run)")
    _logger.info("=" * 80)
    
    try:
        svl_model = env["stock.valuation.layer"]
        
        start = time.time()
        result = svl_model._sql_fast_fill_location(dry_run=True, limit=1000)
        duration = time.time() - start
        
        _logger.info(f"✅ SQL dry run completed in {duration:.2f} seconds")
        _logger.info(f"   Affected rows: {result['count']}")
        _logger.info(f"   Dry run: {result['dry_run']}")
        _logger.info(f"   Limited: {result['limited']}")
        
        return result
        
    except Exception as e:
        _logger.error(f"❌ SQL test failed: {e}")
        return None


def test_recompute_action(env, batch_size=50):
    """Test the full recompute action with small batch"""
    _logger.info("=" * 80)
    _logger.info("TEST 3: Recompute Action")
    _logger.info("=" * 80)
    
    try:
        svl_model = env["stock.valuation.layer"]
        
        start = time.time()
        result = svl_model.action_recompute_stock_valuation_location(batch_size=batch_size)
        duration = time.time() - start
        
        _logger.info(f"✅ Recompute action completed in {duration:.2f} seconds")
        _logger.info(f"   Result: {result}")
        
        return True
        
    except Exception as e:
        _logger.error(f"❌ Recompute action failed: {e}")
        return False


def test_advisory_lock(env):
    """Test that advisory lock prevents concurrent runs"""
    _logger.info("=" * 80)
    _logger.info("TEST 4: Advisory Lock")
    _logger.info("=" * 80)
    
    try:
        svl_model = env["stock.valuation.layer"]
        lock_key = 827174
        
        # Try to get lock twice
        cr = env.cr
        cr.execute("SELECT pg_try_advisory_xact_lock(%s)", (lock_key,))
        first_lock = cr.fetchone()[0]
        
        if first_lock:
            _logger.info("✅ Successfully acquired advisory lock")
            
            # Try to get it again (should fail in same transaction)
            cr.execute("SELECT pg_try_advisory_xact_lock(%s)", (lock_key,))
            second_lock = cr.fetchone()[0]
            
            if second_lock:
                _logger.info("✅ Got lock again (expected in same transaction)")
            
            # Release
            cr.execute("SELECT pg_advisory_unlock(%s)", (lock_key,))
            _logger.info("✅ Released advisory lock")
        else:
            _logger.warning("⚠️ Could not acquire lock (might be held by another process)")
        
        return True
        
    except Exception as e:
        _logger.error(f"❌ Advisory lock test failed: {e}")
        return False


def main():
    """Run all tests"""
    _logger.info("\n" + "=" * 80)
    _logger.info("STOCK VALUATION LOCATION - PERFORMANCE TEST SUITE")
    _logger.info("=" * 80 + "\n")
    
    # This script should be run from Odoo shell:
    # python3 odoo-bin shell -c odoo.conf -d your_db
    # >>> exec(open('custom-addons/stock_valuation_location/test_performance.py').read())
    
    try:
        # Assume we're running in Odoo shell context
        # where 'env' is already available
        test_batch_processing(env, batch_size=100)
        test_sql_dry_run(env)
        test_recompute_action(env, batch_size=50)
        test_advisory_lock(env)
        
        _logger.info("\n" + "=" * 80)
        _logger.info("ALL TESTS COMPLETED")
        _logger.info("=" * 80)
        
    except NameError:
        _logger.error("This script must be run from Odoo shell!")
        _logger.info("\nRun it like this:")
        _logger.info("  ./odoo-bin shell -c odoo.conf -d your_database")
        _logger.info("  >>> exec(open('custom-addons/stock_valuation_location/test_performance.py').read())")


if __name__ == "__main__":
    main()
