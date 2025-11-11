from odoo.tests.common import TransactionCase
import logging

_logger = logging.getLogger(__name__)


class TestStockCurrentReport(TransactionCase):
    """Test cases for Stock Current Report module"""

    def setUp(self):
        super().setUp()
        self.stock_report_model = self.env['stock.current.report']
        self.warehouse_model = self.env['stock.warehouse']
        self.location_model = self.env['stock.location']

    def test_model_access(self):
        """Test that the model is accessible"""
        try:
            # Test model exists and is accessible
            self.assertTrue(self.stock_report_model.check_access())
            _logger.info("✓ Model accessibility test passed")
        except Exception as e:
            _logger.error(f"✗ Model accessibility test failed: {e}")
            self.fail(f"Model accessibility test failed: {e}")

    def test_warehouses_with_locations(self):
        """Test get_warehouses_with_internal_locations method"""
        try:
            warehouses = self.stock_report_model.get_warehouses_with_internal_locations()
            self.assertIsInstance(warehouses, list)
            _logger.info(f"✓ Found {len(warehouses)} warehouses with locations")
            
            # Test structure of returned data
            if warehouses:
                warehouse = warehouses[0]
                self.assertIn('id', warehouse)
                self.assertIn('name', warehouse)
                self.assertIn('locations', warehouse)
                _logger.info("✓ Warehouse data structure is correct")
        except Exception as e:
            _logger.error(f"✗ Warehouses with locations test failed: {e}")
            self.fail(f"Warehouses with locations test failed: {e}")

    def test_location_hierarchy(self):
        """Test get_location_hierarchy method"""
        try:
            hierarchy = self.stock_report_model.get_location_hierarchy()
            self.assertIsInstance(hierarchy, list)
            _logger.info(f"✓ Location hierarchy contains {len(hierarchy)} entries")
            
            # Test structure of hierarchy data
            if hierarchy:
                location = hierarchy[0]
                self.assertIn('id', location)
                self.assertIn('name', location)
                self.assertIn('level', location)
                _logger.info("✓ Location hierarchy structure is correct")
        except Exception as e:
            _logger.error(f"✗ Location hierarchy test failed: {e}")
            self.fail(f"Location hierarchy test failed: {e}")

    def test_warehouse_summary_stats(self):
        """Test get_warehouse_location_summary method"""
        try:
            summary = self.stock_report_model.get_warehouse_location_summary()
            self.assertIsInstance(summary, dict)
            self.assertIn('total_warehouses', summary)
            self.assertIn('total_locations', summary)
            self.assertIn('total_products', summary)
            _logger.info("✓ Warehouse summary stats test passed")
            _logger.info(f"  Summary: {summary}")
        except Exception as e:
            _logger.error(f"✗ Warehouse summary stats test failed: {e}")
            self.fail(f"Warehouse summary stats test failed: {e}")

    def test_sql_view_creation(self):
        """Test that SQL view is created correctly"""
        try:
            # Test view exists
            self.env.cr.execute("""
                SELECT COUNT(*) FROM information_schema.views 
                WHERE table_name = 'stock_current_report'
            """)
            view_exists = self.env.cr.fetchone()[0] > 0
            self.assertTrue(view_exists, "SQL view should exist")
            _logger.info("✓ SQL view creation test passed")
            
            # Test view has data
            count = self.stock_report_model.search_count([])
            _logger.info(f"✓ SQL view contains {count} records")
        except Exception as e:
            _logger.error(f"✗ SQL view creation test failed: {e}")
            self.fail(f"SQL view creation test failed: {e}")

    def test_export_wizard(self):
        """Test export wizard functionality"""
        try:
            wizard_model = self.env['stock.current.export.wizard']
            self.assertTrue(wizard_model, "Export wizard model should exist")
            
            # Create wizard instance
            wizard = wizard_model.create({
                'date_from': '2023-01-01',
                'date_to': '2023-12-31'
            })
            self.assertTrue(wizard, "Wizard should be created successfully")
            _logger.info("✓ Export wizard creation test passed")
        except Exception as e:
            _logger.error(f"✗ Export wizard test failed: {e}")
            self.fail(f"Export wizard test failed: {e}")

    def test_access_rights(self):
        """Test that access rights are properly configured"""
        try:
            # Test user access
            user_group = self.env.ref('stock.group_stock_user')
            manager_group = self.env.ref('stock.group_stock_manager')
            
            # Check that access rights exist
            access_user = self.env['ir.model.access'].search([
                ('model_id.model', '=', 'stock.current.report'),
                ('group_id', '=', user_group.id)
            ])
            self.assertTrue(access_user, "User access rights should exist")
            
            access_manager = self.env['ir.model.access'].search([
                ('model_id.model', '=', 'stock.current.report'),
                ('group_id', '=', manager_group.id)
            ])
            self.assertTrue(access_manager, "Manager access rights should exist")
            
            _logger.info("✓ Access rights test passed")
        except Exception as e:
            _logger.error(f"✗ Access rights test failed: {e}")
            self.fail(f"Access rights test failed: {e}")


class TestStockCurrentReportIntegration(TransactionCase):
    """Integration tests for the complete module"""

    def test_menu_items_exist(self):
        """Test that menu items are properly created"""
        try:
            menu_root = self.env.ref('buz_stock_current_report.menu_stock_current_report_root')
            self.assertTrue(menu_root, "Root menu should exist")
            
            menu_view = self.env.ref('buz_stock_current_report.menu_stock_current_report_view')
            self.assertTrue(menu_view, "View menu should exist")
            
            menu_sidebar = self.env.ref('buz_stock_current_report.menu_stock_current_report_sidebar')
            self.assertTrue(menu_sidebar, "Sidebar menu should exist")
            
            menu_export = self.env.ref('buz_stock_current_report.menu_stock_current_export_wizard')
            self.assertTrue(menu_export, "Export menu should exist")
            
            _logger.info("✓ Menu items test passed")
        except Exception as e:
            _logger.error(f"✗ Menu items test failed: {e}")
            self.fail(f"Menu items test failed: {e}")

    def test_actions_exist(self):
        """Test that window actions are properly created"""
        try:
            action_report = self.env.ref('buz_stock_current_report.action_stock_current_report')
            self.assertTrue(action_report, "Report action should exist")
            
            action_sidebar = self.env.ref('buz_stock_current_report.action_stock_current_report_sidebar')
            self.assertTrue(action_sidebar, "Sidebar action should exist")
            
            action_export = self.env.ref('buz_stock_current_report.action_stock_current_export_wizard')
            self.assertTrue(action_export, "Export action should exist")
            
            _logger.info("✓ Actions test passed")
        except Exception as e:
            _logger.error(f"✗ Actions test failed: {e}")
            self.fail(f"Actions test failed: {e}")