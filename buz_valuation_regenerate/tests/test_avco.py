import odoo
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestAVCOValuationRegeneration(TransactionCase):
    
    def setUp(self):
        super().setUp()
        
        # Get the required models
        self.Product = self.env['product.product']
        self.StockMove = self.env['stock.move']
        self.StockLocation = self.env['stock.location']
        self.StockValuationLayer = self.env['stock.valuation.layer']
        self.Company = self.env['res.company']
        self.Wizard = self.env['valuation.regenerate.wizard']
        
        # Get default company
        self.company = self.env.ref('base.main_company')
        
        # Get stock locations
        self.supplier_location = self.env.ref('stock.stock_location_suppliers')
        self.customer_location = self.env.ref('stock.stock_location_customers')
        self.stock_location = self.env.ref('stock.stock_location_stock')
        
        # Create a product with AVCO costing method
        self.product_avco = self.Product.create({
            'name': 'Test AVCO Product',
            'type': 'product',
            'categ_id': self.env.ref('product.product_category_all').id,
            'standard_price': 100.0,
            'list_price': 150.0,
        })
        # Set the product category's costing method to AVCO
        self.product_avco.categ_id.property_cost_method = 'average'

    def test_avco_regen_basic(self):
        """Test basic AVCO regeneration"""
        # Create some stock moves to establish inventory
        incoming_move1 = self.StockMove.create({
            'name': 'Incoming Move 1',
            'product_id': self.product_avco.id,
            'product_uom_qty': 10,
            'product_uom': self.product_avco.uom_id.id,
            'location_id': self.supplier_location.id,
            'location_dest_id': self.stock_location.id,
            'company_id': self.company.id,
            'price_unit': 100.0,
            'state': 'done',
        })
        
        incoming_move1._action_confirm()
        incoming_move1._action_assign()
        incoming_move1.move_line_ids.qty_done = 10
        incoming_move1._action_done()
        
        # Verify SVL was created
        svls_after_incoming1 = self.StockValuationLayer.search([
            ('product_id', '=', self.product_avco.id)
        ])
        self.assertEqual(len(svls_after_incoming1), 1)
        self.assertEqual(svls_after_incoming1.value, 1000.0)  # 10 * 100
        
        # Create another incoming move with different cost
        incoming_move2 = self.StockMove.create({
            'name': 'Incoming Move 2',
            'product_id': self.product_avco.id,
            'product_uom_qty': 10,
            'product_uom': self.product_avco.uom_id.id,
            'location_id': self.supplier_location.id,
            'location_dest_id': self.stock_location.id,
            'company_id': self.company.id,
            'price_unit': 120.0,  # Different cost
            'state': 'done',
        })
        
        incoming_move2._action_confirm()
        incoming_move2._action_assign()
        incoming_move2.move_line_ids.qty_done = 10
        incoming_move2._action_done()
        
        # After second incoming, the average cost should be (10*100 + 10*120)/(10+10) = 110
        current_svls = self.StockValuationLayer.search([
            ('product_id', '=', self.product_avco.id)
        ], order='create_date')
        
        # Now create an outgoing move to test AVCO cost calculation
        outgoing_move = self.StockMove.create({
            'name': 'Outgoing Move',
            'product_id': self.product_avco.id,
            'product_uom_qty': 8,
            'product_uom': self.product_avco.uom_id.id,
            'location_id': self.stock_location.id,
            'location_dest_id': self.customer_location.id,
            'company_id': self.company.id,
            'state': 'done',
        })
        
        outgoing_move._action_confirm()
        outgoing_move._action_assign()
        outgoing_move.move_line_ids.qty_done = 8
        outgoing_move._action_done()
        
        # After AVCO, the outgoing move should use average cost at that time: 110
        # So the value should be 8 * 110 = 880 (negative for outgoing)
        final_svls = self.StockValuationLayer.search([
            ('product_id', '=', self.product_avco.id)
        ], order='create_date')
        
        # The outgoing SVL should have a value based on average cost
        outgoing_svl = final_svls[-1]  # Last created SVL should be the outgoing
        self.assertAlmostEqual(outgoing_svl.value, -880.0, places=2)  # 8 * 110 with negative sign for outgoing
        
        # Create the wizard to regenerate SVLs
        wizard = self.Wizard.create({
            'company_id': self.company.id,
            'mode': 'product',
            'product_ids': [(6, 0, [self.product_avco.id])],
            'rebuild_valuation_layers': True,
            'rebuild_account_moves': False,  # Don't rebuild JEs for this test
            'recompute_cost_method': 'avco',
            'dry_run': True,  # Start with dry run
        })
        
        # Run the compute plan
        wizard.action_compute_plan()
        
        # The preview should show the SVLs that would be affected
        self.assertGreaterEqual(len(wizard.line_preview_ids), 3)  # At least 3 SVLs should be affected
        
        # Now do a real regeneration (not dry run)
        wizard.dry_run = False
        result = wizard.action_apply_regeneration()
        
        # Verify the regeneration completed successfully
        self.assertIn('type', result)
        self.assertEqual(result['type'], 'ir.actions.client')
        
        # After regeneration, check that the SVLs are still following AVCO logic
        regenerated_svls = self.StockValuationLayer.search([
            ('product_id', '=', self.product_avco.id)
        ], order='create_date')
        
        # Should still have the same number of SVLs after regeneration
        self.assertEqual(len(regenerated_svls), len(final_svls))
        
        # The outgoing SVL should still be calculated using AVCO
        regenerated_outgoing_svl = regenerated_svls[-1]
        # Should still be approximately -880 (with potential small rounding differences)
        self.assertAlmostEqual(regenerated_outgoing_svl.value, -880.0, places=2)