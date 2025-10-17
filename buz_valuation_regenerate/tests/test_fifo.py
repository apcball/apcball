import odoo
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestFIFOValuationRegeneration(TransactionCase):
    
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
        
        # Create a product with FIFO costing method
        self.product_fifo = self.Product.create({
            'name': 'Test FIFO Product',
            'type': 'product',
            'categ_id': self.env.ref('product.product_category_all').id,
            'standard_price': 100.0,
            'list_price': 150.0,
        })
        # Set the product category's costing method to FIFO
        self.product_fifo.categ_id.property_cost_method = 'fifo'

    def test_fifo_regen_basic(self):
        """Test basic FIFO regeneration"""
        # Create some stock moves to establish inventory
        incoming_move1 = self.StockMove.create({
            'name': 'Incoming Move 1',
            'product_id': self.product_fifo.id,
            'product_uom_qty': 10,
            'product_uom': self.product_fifo.uom_id.id,
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
        svls_after_incoming = self.StockValuationLayer.search([
            ('product_id', '=', self.product_fifo.id)
        ])
        self.assertEqual(len(svls_after_incoming), 1)
        self.assertEqual(svls_after_incoming.value, 1000.0)  # 10 * 100
        
        # Create another incoming move with different cost
        incoming_move2 = self.StockMove.create({
            'name': 'Incoming Move 2',
            'product_id': self.product_fifo.id,
            'product_uom_qty': 5,
            'product_uom': self.product_fifo.uom_id.id,
            'location_id': self.supplier_location.id,
            'location_dest_id': self.stock_location.id,
            'company_id': self.company.id,
            'price_unit': 120.0,  # Different cost
            'state': 'done',
        })
        
        incoming_move2._action_confirm()
        incoming_move2._action_assign()
        incoming_move2.move_line_ids.qty_done = 5
        incoming_move2._action_done()
        
        # Now create an outgoing move to test FIFO cost calculation
        outgoing_move = self.StockMove.create({
            'name': 'Outgoing Move',
            'product_id': self.product_fifo.id,
            'product_uom_qty': 8,
            'product_uom': self.product_fifo.uom_id.id,
            'location_id': self.stock_location.id,
            'location_dest_id': self.customer_location.id,
            'company_id': self.company.id,
            'state': 'done',
        })
        
        outgoing_move._action_confirm()
        outgoing_move._action_assign()
        outgoing_move.move_line_ids.qty_done = 8
        outgoing_move._action_done()
        
        # After FIFO, the outgoing move should take 8 units from the first batch (10 units at 100)
        # So the value should be 8 * 100 = 800 (negative for outgoing)
        svls_after_outgoing = self.StockValuationLayer.search([
            ('product_id', '=', self.product_fifo.id)
        ], order='create_date')
        
        # The outgoing SVL should have a value of -800 (8 units at FIFO price of 100)
        outgoing_svl = svls_after_outgoing[-1]  # Last created SVL should be the outgoing
        self.assertEqual(outgoing_svl.value, -800.0)  # 8 * 100 with negative sign for outgoing
        
        # Create the wizard to regenerate SVLs
        wizard = self.Wizard.create({
            'company_id': self.company.id,
            'mode': 'product',
            'product_ids': [(6, 0, [self.product_fifo.id])],
            'rebuild_valuation_layers': True,
            'rebuild_account_moves': False,  # Don't rebuild JEs for this test
            'recompute_cost_method': 'fifo',
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
        
        # After regeneration, check that the SVLs are still following FIFO logic
        regenerated_svls = self.StockValuationLayer.search([
            ('product_id', '=', self.product_fifo.id)
        ], order='create_date')
        
        # Should still have the same number of SVLs after regeneration
        self.assertEqual(len(regenerated_svls), len(svls_after_outgoing))
        
        # The outgoing SVL should still be calculated using FIFO (8 units at 100 cost)
        regenerated_outgoing_svl = regenerated_svls[-1]
        self.assertEqual(regenerated_outgoing_svl.value, -800.0)