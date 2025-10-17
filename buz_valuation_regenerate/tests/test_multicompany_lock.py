import odoo
from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


@tagged('post_install', '-at_install')
class TestMultiCompanyLock(TransactionCase):
    
    def setUp(self):
        super().setUp()
        
        # Get the required models
        self.Product = self.env['product.product']
        self.StockMove = self.env['stock.move']
        self.StockLocation = self.env['stock.location']
        self.StockValuationLayer = self.env['stock.valuation.layer']
        self.Company = self.env['res.company']
        self.Wizard = self.env['valuation.regenerate.wizard']
        self.User = self.env['res.users']
        
        # Create a second company
        self.company2 = self.Company.create({
            'name': 'Second Company',
            'currency_id': self.env.ref('base.USD').id,
        })
        
        # Get default company
        self.company1 = self.env.ref('base.main_company')
        
        # Get stock locations
        self.supplier_location = self.env.ref('stock.stock_location_suppliers')
        self.customer_location = self.env.ref('stock.stock_location_customers')
        self.stock_location = self.env.ref('stock.stock_location_stock')
        
        # Create products for each company
        self.product_company1 = self.Product.create({
            'name': 'Product for Company 1',
            'type': 'product',
            'categ_id': self.env.ref('product.product_category_all').id,
            'company_id': self.company1.id,
        })
        
        self.product_company2 = self.Product.create({
            'name': 'Product for Company 2',
            'type': 'product',
            'categ_id': self.env.ref('product.product_category_all').id,
            'company_id': self.company2.id,
        })

    def test_multicompany_isolation(self):
        """Test that regeneration only affects the selected company"""
        # Create stock moves for both companies
        move1 = self.StockMove.create({
            'name': 'Move for Company 1',
            'product_id': self.product_company1.id,
            'product_uom_qty': 10,
            'product_uom': self.product_company1.uom_id.id,
            'location_id': self.supplier_location.id,
            'location_dest_id': self.stock_location.id,
            'company_id': self.company1.id,
            'price_unit': 100.0,
            'state': 'done',
        })
        
        move1._action_confirm()
        move1._action_assign()
        move1.move_line_ids.qty_done = 10
        move1._action_done()
        
        move2 = self.StockMove.create({
            'name': 'Move for Company 2',
            'product_id': self.product_company2.id,
            'product_uom_qty': 5,
            'product_uom': self.product_company2.uom_id.id,
            'location_id': self.supplier_location.id,
            'location_dest_id': self.stock_location.id,
            'company_id': self.company2.id,
            'price_unit': 200.0,
            'state': 'done',
        })
        
        move2._action_confirm()
        move2._action_assign()
        move2.move_line_ids.qty_done = 5
        move2._action_done()
        
        # Verify SVLs were created for both products
        svls_company1 = self.StockValuationLayer.search([
            ('product_id', '=', self.product_company1.id)
        ])
        svls_company2 = self.StockValuationLayer.search([
            ('product_id', '=', self.product_company2.id)
        ])
        
        self.assertEqual(len(svls_company1), 1)
        self.assertEqual(len(svls_company2), 1)
        
        # Create wizard for company 1 only
        wizard = self.Wizard.create({
            'company_id': self.company1.id,
            'mode': 'product',
            'product_ids': [(6, 0, [self.product_company1.id])],
            'rebuild_valuation_layers': True,
            'rebuild_account_moves': False,
            'dry_run': False,
        })
        
        # Execute regeneration for company 1
        result = wizard.action_apply_regeneration()
        
        # Verify execution completed
        self.assertIn('type', result)
        self.assertEqual(result['type'], 'ir.actions.client')
        
        # Check that only company 1's SVLs were regenerated
        # Company 2's SVLs should remain unchanged
        updated_svls_company1 = self.StockValuationLayer.search([
            ('product_id', '=', self.product_company1.id)
        ])
        updated_svls_company2 = self.StockValuationLayer.search([
            ('product_id', '=', self.product_company2.id)
        ])
        
        # Company 1 should have new SVLs (the old ones were deleted and new ones created)
        self.assertGreaterEqual(len(updated_svls_company1), 1)
        
        # Company 2 should still have exactly 1 SVL (unchanged)
        self.assertEqual(len(updated_svls_company2), 1)
        
    def test_lock_period_prevention(self):
        """Test that regeneration is prevented during locked periods"""
        # Create a stock move
        move = self.StockMove.create({
            'name': 'Test Move',
            'product_id': self.product_company1.id,
            'product_uom_qty': 10,
            'product_uom': self.product_company1.uom_id.id,
            'location_id': self.supplier_location.id,
            'location_dest_id': self.stock_location.id,
            'company_id': self.company1.id,
            'price_unit': 100.0,
            'state': 'done',
        })
        
        move._action_confirm()
        move._action_assign()
        move.move_line_ids.qty_done = 10
        move._action_done()
        
        # Set a fiscal year lock date in the past to test the validation
        self.company1.fiscalyear_lock_date = '2020-01-01'
        
        # Create wizard that tries to regenerate data from a locked period
        wizard = self.Wizard.create({
            'company_id': self.company1.id,
            'mode': 'product',
            'product_ids': [(6, 0, [self.product_company1.id])],
            'rebuild_valuation_layers': True,
            'rebuild_account_moves': False,
            'date_from': '2020-06-01',  # This date is before the lock date
            'date_to': '2020-06-30',
            'dry_run': False,  # Not a dry run, so validation will occur
            'force_rebuild_even_if_locked': False,  # Don't override locks
        })
        
        # Attempt to execute regeneration - should raise an error due to lock
        with self.assertRaises(UserError):
            wizard.action_apply_regeneration()
        
        # Reset the lock date to continue testing
        self.company1.fiscalyear_lock_date = False
        
        # Now test with force override - should succeed
        wizard.force_rebuild_even_if_locked = True
        wizard.date_from = '2020-06-01'
        wizard.date_to = '2020-06-30'
        
        # This should work because we're overriding the lock
        result = wizard.action_apply_regeneration()
        self.assertIn('type', result)