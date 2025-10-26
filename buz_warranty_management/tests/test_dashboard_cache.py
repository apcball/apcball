from odoo.tests.common import TransactionCase
import time


class TestDashboardCache(TransactionCase):
    
    def test_cache_creation(self):
        """Test cache creation and basic functionality"""
        # Create cache
        cache = self.env['warranty.dashboard.cache'].create({})
        
        # Verify initial state
        self.assertEqual(cache.cache_status, 'expired')
        self.assertTrue(cache.last_update)
        self.assertFalse(cache.is_updating)
    
    def test_cache_update_metrics(self):
        """Test cache metrics update"""
        # Create test warranty
        partner = self.env['res.partner'].create({
            'name': 'Test Customer'
        })
        product = self.env['product.product'].create({
            'name': 'Test Product',
            'warranty_duration': 12,
            'warranty_period_unit': 'month'
        })
        
        warranty = self.env['warranty.card'].create({
            'partner_id': partner.id,
            'product_id': product.id,
            'start_date': '2023-01-01'
        })
        
        # Update cache
        cache = self.env['warranty.dashboard.cache'].get_or_create_cache()
        
        # Verify metrics
        self.assertEqual(cache.total_warranties, 1)
        self.assertEqual(cache.active_warranties, 1)
        self.assertGreater(cache.active_percentage, 0)
    
    def test_cache_trigger(self):
        """Test cache trigger mechanism"""
        # Create cache
        cache = self.env['warranty.dashboard.cache'].create({})
        initial_trigger_count = cache.trigger_count
        
        # Trigger update
        self.env['warranty.dashboard.cache']._trigger_update('test_trigger')
        
        # Verify trigger was recorded
        cache.refresh()
        self.assertEqual(cache.trigger_count, initial_trigger_count + 1)
        self.assertEqual(cache.last_trigger_type, 'test_trigger')
    
    def test_dashboard_with_cache(self):
        """Test dashboard using cached data"""
        # Create test data
        partner = self.env['res.partner'].create({
            'name': 'Test Customer'
        })
        product = self.env['product.product'].create({
            'name': 'Test Product',
            'warranty_duration': 12,
            'warranty_period_unit': 'month'
        })
        
        warranty = self.env['warranty.card'].create({
            'partner_id': partner.id,
            'product_id': product.id,
            'start_date': '2023-01-01'
        })
        
        # Update cache
        cache = self.env['warranty.dashboard.cache'].get_or_create_cache()
        
        # Create dashboard
        dashboard = self.env['warranty.dashboard'].create({})
        
        # Verify dashboard uses cached data
        self.assertEqual(dashboard.total_warranties, 1)
        self.assertEqual(dashboard.cache_id.id, cache.id)
        self.assertEqual(dashboard.cache_status, 'valid')
    
    def test_manual_refresh(self):
        """Test manual refresh functionality"""
        # Create dashboard
        dashboard = self.env['warranty.dashboard'].create({})
        
        # Test refresh action
        result = dashboard.action_refresh_cache()
        
        # Verify action returns notification dict
        self.assertIsInstance(result, dict)
        self.assertEqual(result['type'], 'ir.actions.client')
        self.assertEqual(result['tag'], 'display_notification')