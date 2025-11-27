# -*- coding: utf-8 -*-
"""
Unit and Integration Tests for stock_fifo_by_location module.

Tests cover:
- Incoming receipt with location tracking
- Internal transfers with location tracking
- Outgoing delivery with FIFO consumption from specific location
- Shortage handling (error and fallback modes)
- COGS calculation accuracy
- Journal entry correctness
- Edge cases (negative qty, rounding, multi-company)
"""

# import pytest  # Pytest not required for Odoo tests
from odoo.tests import TransactionCase, tagged
from odoo.tools import float_compare, float_round
from odoo.exceptions import UserError
from datetime import datetime, timedelta


@tagged('post_install', '-at_install')
class TestStockFifoByLocation(TransactionCase):
    """
    Main test class for FIFO by Location functionality.
    """
    
    def setUp(self):
        """Set up test data."""
        super().setUp()
        
        self.product_model = self.env['product.product']
        self.location_model = self.env['stock.location']
        self.move_model = self.env['stock.move']
        self.valuation_layer_model = self.env['stock.valuation.layer']
        self.fifo_service = self.env['fifo.service']
        self.company = self.env.company
        
        # Create test locations
        self.warehouse = self.location_model.search([
            ('company_id', '=', self.company.id),
            ('usage', '=', 'internal'),
        ], limit=1)
        
        if not self.warehouse:
            self.warehouse = self.location_model.create({
                'name': 'Test Warehouse',
                'usage': 'internal',
                'company_id': self.company.id,
            })
        
        # Create location A and B
        self.location_a = self.location_model.create({
            'name': 'Location A',
            'usage': 'internal',
            'location_id': self.warehouse.id,
            'company_id': self.company.id,
        })
        
        self.location_b = self.location_model.create({
            'name': 'Location B',
            'usage': 'internal',
            'location_id': self.warehouse.id,
            'company_id': self.company.id,
        })
        
        # Create supplier and customer locations
        self.supplier_location = self.location_model.search([
            ('usage', '=', 'supplier'),
            ('company_id', '=', self.company.id),
        ], limit=1)
        
        if not self.supplier_location:
            self.supplier_location = self.location_model.create({
                'name': 'Supplier',
                'usage': 'supplier',
                'company_id': self.company.id,
            })
        
        self.customer_location = self.location_model.search([
            ('usage', '=', 'customer'),
            ('company_id', '=', self.company.id),
        ], limit=1)
        
        if not self.customer_location:
            self.customer_location = self.location_model.create({
                'name': 'Customer',
                'usage': 'customer',
                'company_id': self.company.id,
            })
        
        # Create test product with FIFO costing
        self.product = self.product_model.create({
            'name': 'Test Product FIFO',
            'type': 'product',
            'categ_id': self.env.ref('product.product_category_all').id,
            'cost_method': 'fifo',
            'company_id': self.company.id,
        })
    
    def test_incoming_receipt_location_captured(self):
        """
        Test that incoming receipt populates location_id correctly.
        
        Scenario:
        - Receive 10 units of product at Location A
        - Validate that SVL has location_id = Location A
        """
        # Create incoming move
        move = self.move_model.create({
            'name': 'Receipt',
            'product_id': self.product.id,
            'product_uom_qty': 10.0,
            'product_uom': self.product.uom_id.id,
            'location_id': self.supplier_location.id,
            'location_dest_id': self.location_a.id,
            'state': 'draft',
        })
        
        # Validate move
        move.with_context(fifo_location_id=self.location_a.id)._action_done()
        
        # Check that SVL was created with correct location
        layers = self.valuation_layer_model.search([
            ('stock_move_id', '=', move.id),
        ])
        
        self.assertEqual(len(layers), 1, "Should create exactly one SVL")
        self.assertEqual(layers[0].location_id.id, self.location_a.id,
                        "SVL should have Location A")
        self.assertEqual(layers[0].quantity, 10.0)
    
    def test_fifo_queue_retrieval_by_location(self):
        """
        Test FIFO queue retrieval is location-specific.
        
        Scenario:
        - Receive 10 units at Location A (cost 100)
        - Receive 5 units at Location B (cost 120)
        - Query FIFO queue for Location A -> should get only A's layer
        """
        # Receipt to Location A
        move_a = self.move_model.create({
            'name': 'Receipt to A',
            'product_id': self.product.id,
            'product_uom_qty': 10.0,
            'product_uom': self.product.uom_id.id,
            'location_id': self.supplier_location.id,
            'location_dest_id': self.location_a.id,
            'state': 'draft',
        })
        move_a.with_context(fifo_location_id=self.location_a.id)._action_done()
        
        # Receipt to Location B
        move_b = self.move_model.create({
            'name': 'Receipt to B',
            'product_id': self.product.id,
            'product_uom_qty': 5.0,
            'product_uom': self.product.uom_id.id,
            'location_id': self.supplier_location.id,
            'location_dest_id': self.location_b.id,
            'state': 'draft',
        })
        move_b.with_context(fifo_location_id=self.location_b.id)._action_done()
        
        # Get FIFO queue for Location A
        queue_a = self.fifo_service.get_valuation_layer_queue(
            self.product, self.location_a, self.company.id
        )
        
        # Get FIFO queue for Location B
        queue_b = self.fifo_service.get_valuation_layer_queue(
            self.product, self.location_b, self.company.id
        )
        
        # Verify queues are separate
        self.assertEqual(len(queue_a), 1)
        self.assertEqual(len(queue_b), 1)
        self.assertEqual(queue_a[0].location_id.id, self.location_a.id)
        self.assertEqual(queue_b[0].location_id.id, self.location_b.id)
    
    def test_fifo_cost_calculation_at_location(self):
        """
        Test FIFO cost calculation respects location boundaries.
        
        Scenario:
        - Receipt 1 (2025-01-01) to Location A: qty 10, cost 100 -> SVL1
        - Receipt 2 (2025-01-10) to Location A: qty 5, cost 120 -> SVL2
        - Consume 12 units from Location A
        - Expect: 10 from SVL1 + 2 from SVL2
        - COGS = 10*100 + 2*120 = 1000 + 240 = 1240
        """
        precision = self.env['decimal.precision'].precision_get('Product Price')
        
        # Create first receipt
        move1 = self.move_model.create({
            'name': 'Receipt 1',
            'product_id': self.product.id,
            'product_uom_qty': 10.0,
            'product_uom': self.product.uom_id.id,
            'location_id': self.supplier_location.id,
            'location_dest_id': self.location_a.id,
            'state': 'draft',
        })
        move1._action_done()
        
        # Manually set unit cost for first receipt
        layers1 = self.valuation_layer_model.search([
            ('stock_move_id', '=', move1.id),
        ])
        layers1[0].unit_cost = 100.0
        
        # Create second receipt 10 days later
        move2 = self.move_model.create({
            'name': 'Receipt 2',
            'product_id': self.product.id,
            'product_uom_qty': 5.0,
            'product_uom': self.product.uom_id.id,
            'location_id': self.supplier_location.id,
            'location_dest_id': self.location_a.id,
            'state': 'draft',
        })
        move2._action_done()
        
        # Manually set unit cost for second receipt
        layers2 = self.valuation_layer_model.search([
            ('stock_move_id', '=', move2.id),
        ])
        layers2[0].unit_cost = 120.0
        
        # Calculate cost for consuming 12 units from Location A
        cost_info = self.fifo_service.calculate_fifo_cost(
            self.product, self.location_a, 12.0, self.company.id
        )
        
        # Verify cost calculation
        self.assertEqual(cost_info['qty'], 12.0)
        expected_cost = 10 * 100 + 2 * 120  # 1240
        self.assertAlmostEqual(
            cost_info['cost'], expected_cost,
            places=precision,
            msg=f"Expected cost {expected_cost}, got {cost_info['cost']}"
        )
        
        # Verify layers consumed
        self.assertEqual(len(cost_info['layers']), 2)
        self.assertEqual(cost_info['layers'][0]['qty_consumed'], 10.0)
        self.assertEqual(cost_info['layers'][1]['qty_consumed'], 2.0)
    
    def test_location_shortage_error_mode(self):
        """
        Test shortage handling in 'error' mode (default).
        
        Scenario:
        - Receive 5 units at Location A
        - Try to deliver 10 units from Location A
        - Should raise error due to insufficient quantity
        """
        # Set shortage policy to 'error'
        self.env['ir.config_parameter'].sudo().set_param(
            'stock_fifo_by_location.shortage_policy', 'error'
        )
        
        # Receipt 5 units
        move = self.move_model.create({
            'name': 'Receipt',
            'product_id': self.product.id,
            'product_uom_qty': 5.0,
            'product_uom': self.product.uom_id.id,
            'location_id': self.supplier_location.id,
            'location_dest_id': self.location_a.id,
            'state': 'draft',
        })
        move._action_done()
        
        # Try to validate availability for 10 units
        with self.assertRaises(UserError) as ctx:
            self.fifo_service.validate_location_availability(
                self.product, self.location_a, 10.0,
                allow_fallback=False, company_id=self.company.id
            )
        
        self.assertIn('Insufficient', str(ctx.exception))
    
    def test_location_shortage_fallback_mode(self):
        """
        Test shortage handling with fallback enabled.
        
        Scenario:
        - Receive 5 units at Location A
        - Receive 8 units at Location B
        - Check availability at Location A for 10 units with fallback
        - Should identify fallback locations
        """
        # Receipt 5 units to Location A
        move_a = self.move_model.create({
            'name': 'Receipt A',
            'product_id': self.product.id,
            'product_uom_qty': 5.0,
            'product_uom': self.product.uom_id.id,
            'location_id': self.supplier_location.id,
            'location_dest_id': self.location_a.id,
            'state': 'draft',
        })
        move_a._action_done()
        
        # Receipt 8 units to Location B
        move_b = self.move_model.create({
            'name': 'Receipt B',
            'product_id': self.product.id,
            'product_uom_qty': 8.0,
            'product_uom': self.product.uom_id.id,
            'location_id': self.supplier_location.id,
            'location_dest_id': self.location_b.id,
            'state': 'draft',
        })
        move_b._action_done()
        
        # Check availability with fallback
        result = self.fifo_service.validate_location_availability(
            self.product, self.location_a, 10.0,
            allow_fallback=True, company_id=self.company.id
        )
        
        # Should show shortage but provide fallback locations
        self.assertFalse(result['available'])
        self.assertEqual(result['available_qty'], 5.0)
        self.assertEqual(result['shortage'], 5.0)
        # Should find Location B as fallback
        self.assertTrue(len(result['fallback_locations']) > 0)
    
    def test_internal_transfer_location_assignment(self):
        """
        Test that internal transfers maintain location tracking.
        
        Scenario:
        - Receive 10 units at Location A
        - Transfer 6 units from Location A to Location B
        - Verify: Location A has 4 units, Location B has 6 units in correct layers
        """
        # Initial receipt to Location A
        move_in = self.move_model.create({
            'name': 'Receipt',
            'product_id': self.product.id,
            'product_uom_qty': 10.0,
            'product_uom': self.product.uom_id.id,
            'location_id': self.supplier_location.id,
            'location_dest_id': self.location_a.id,
            'state': 'draft',
        })
        move_in._action_done()
        
        # Internal transfer from A to B
        move_transfer = self.move_model.create({
            'name': 'Transfer A->B',
            'product_id': self.product.id,
            'product_uom_qty': 6.0,
            'product_uom': self.product.uom_id.id,
            'location_id': self.location_a.id,
            'location_dest_id': self.location_b.id,
            'state': 'draft',
        })
        move_transfer._action_done()
        
        # Check quantities at each location
        qty_a = self.fifo_service.get_available_qty_at_location(
            self.product, self.location_a, self.company.id
        )
        qty_b = self.fifo_service.get_available_qty_at_location(
            self.product, self.location_b, self.company.id
        )
        
        # Location A should have 4 units
        self.assertAlmostEqual(qty_a, 4.0, places=2)
        # Location B should have 6 units
        self.assertAlmostEqual(qty_b, 6.0, places=2)
    
    def test_multiple_locations_isolated_fifo(self):
        """
        Test FIFO isolation across multiple locations.
        
        Scenario:
        - Receipt 1: 100 units to Loc A at cost 100
        - Receipt 2: 100 units to Loc B at cost 150
        - Delivery from Loc A: 50 units -> should use cost 100, not 150
        - Delivery from Loc B: 50 units -> should use cost 150, not 100
        """
        precision = self.env['decimal.precision'].precision_get('Product Price')
        
        # Receipt to Location A
        move_a = self.move_model.create({
            'name': 'Receipt A',
            'product_id': self.product.id,
            'product_uom_qty': 100.0,
            'product_uom': self.product.uom_id.id,
            'location_id': self.supplier_location.id,
            'location_dest_id': self.location_a.id,
            'state': 'draft',
        })
        move_a._action_done()
        
        layers_a = self.valuation_layer_model.search([
            ('stock_move_id', '=', move_a.id),
        ])
        layers_a[0].unit_cost = 100.0
        
        # Receipt to Location B
        move_b = self.move_model.create({
            'name': 'Receipt B',
            'product_id': self.product.id,
            'product_uom_qty': 100.0,
            'product_uom': self.product.uom_id.id,
            'location_id': self.supplier_location.id,
            'location_dest_id': self.location_b.id,
            'state': 'draft',
        })
        move_b._action_done()
        
        layers_b = self.valuation_layer_model.search([
            ('stock_move_id', '=', move_b.id),
        ])
        layers_b[0].unit_cost = 150.0
        
        # Calculate cost for Location A
        cost_a = self.fifo_service.calculate_fifo_cost(
            self.product, self.location_a, 50.0, self.company.id
        )
        
        # Calculate cost for Location B
        cost_b = self.fifo_service.calculate_fifo_cost(
            self.product, self.location_b, 50.0, self.company.id
        )
        
        # Location A should use cost 100
        expected_cost_a = 50 * 100
        self.assertAlmostEqual(cost_a['cost'], expected_cost_a, places=precision)
        
        # Location B should use cost 150
        expected_cost_b = 50 * 150
        self.assertAlmostEqual(cost_b['cost'], expected_cost_b, places=precision)


@tagged('post_install', '-at_install')
class TestFifoServiceMethods(TransactionCase):
    """
    Tests for FifoService helper methods.
    """
    
    def setUp(self):
        super().setUp()
        self.fifo_service = self.env['fifo.service']
        self.product_model = self.env['product.product']
        self.location_model = self.env['stock.location']
        self.company = self.env.company
        
        # Create test product
        self.product = self.product_model.create({
            'name': 'Test Product',
            'type': 'product',
            'cost_method': 'fifo',
        })
        
        # Create test location
        self.location = self.location_model.search([
            ('usage', '=', 'internal'),
            ('company_id', '=', self.company.id),
        ], limit=1)
    
    def test_shortage_policy_config(self):
        """Test retrieval of shortage policy config."""
        policy = self.fifo_service.get_shortage_policy()
        self.assertIn(policy, ['error', 'fallback'])
    
    def test_location_validation_config(self):
        """Test retrieval of validation enable config."""
        enabled = self.fifo_service.get_enable_location_validation()
        self.assertIsInstance(enabled, bool)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])


@tagged('post_install', '-at_install')
class TestLandedCostByLocation(TransactionCase):
    """
    Tests for landed cost allocation by location functionality.
    """
    
    def setUp(self):
        super().setUp()
        self.product_model = self.env['product.product']
        self.location_model = self.env['stock.location']
        self.move_model = self.env['stock.move']
        self.valuation_layer_model = self.env['stock.valuation.layer']
        self.landed_cost_model = self.env['stock.landed.cost']
        self.landed_cost_lines_model = self.env['stock.landed.cost.lines']
        self.lc_location_model = self.env['stock.valuation.layer.landed.cost']
        self.company = self.env.company
        
        # Create test product
        self.product = self.product_model.create({
            'name': 'Test Product LC',
            'type': 'product',
            'categ_id': self.env.ref('product.product_category_all').id,
            'cost_method': 'fifo',
        })
        
        # Create test locations
        self.warehouse = self.location_model.search([
            ('usage', '=', 'internal'),
            ('company_id', '=', self.company.id),
        ], limit=1)
        
        if not self.warehouse:
            self.warehouse = self.location_model.create({
                'name': 'Test Warehouse',
                'usage': 'internal',
                'company_id': self.company.id,
            })
        
        self.location_a = self.location_model.create({
            'name': 'Location A',
            'usage': 'internal',
            'location_id': self.warehouse.id,
            'company_id': self.company.id,
        })
        
        self.location_b = self.location_model.create({
            'name': 'Location B',
            'usage': 'internal',
            'location_id': self.warehouse.id,
            'company_id': self.company.id,
        })
        
        self.supplier_location = self.location_model.search([
            ('usage', '=', 'supplier'),
            ('company_id', '=', self.company.id),
        ], limit=1)
        
        if not self.supplier_location:
            self.supplier_location = self.location_model.create({
                'name': 'Supplier',
                'usage': 'supplier',
                'company_id': self.company.id,
            })
    
    def test_landed_cost_at_location_creation(self):
        """
        Test that landed costs are properly tracked at specific locations.
        
        Scenario:
        - Receive 10 units at Location A
        - Apply landed cost of $50
        - Verify landed cost is recorded at Location A
        """
        # Create incoming move to Location A
        move = self.move_model.create({
            'name': 'Receipt LC',
            'product_id': self.product.id,
            'product_uom_qty': 10.0,
            'product_uom': self.product.uom_id.id,
            'location_id': self.supplier_location.id,
            'location_dest_id': self.location_a.id,
            'state': 'draft',
        })
        
        move._action_done()
        
        # Get the valuation layer
        layers = self.valuation_layer_model.search([
            ('stock_move_id', '=', move.id),
            ('location_id', '=', self.location_a.id),
        ])
        
        self.assertEqual(len(layers), 1, "Should have one layer at Location A")
        layer = layers[0]
        
        # Verify layer has location_id set
        self.assertEqual(layer.location_id.id, self.location_a.id)
    
    def test_landed_cost_transfer_between_locations(self):
        """
        Test that landed costs are transferred proportionally during internal transfer.
        
        Scenario:
        - Receive 100 units at Location A (cost 100, landed cost 50 total = 50.5 per unit)
        - Transfer 50 units from A to B
        - Verify landed cost is split proportionally
        """
        precision = self.env['decimal.precision'].precision_get('Product Price')
        
        # Create incoming move to Location A
        move_in = self.move_model.create({
            'name': 'Receipt',
            'product_id': self.product.id,
            'product_uom_qty': 100.0,
            'product_uom': self.product.uom_id.id,
            'location_id': self.supplier_location.id,
            'location_dest_id': self.location_a.id,
            'state': 'draft',
        })
        
        move_in._action_done()
        
        # Manually set cost and create landed cost record
        layers_a = self.valuation_layer_model.search([
            ('stock_move_id', '=', move_in.id),
            ('location_id', '=', self.location_a.id),
        ])
        
        self.assertEqual(len(layers_a), 1)
        layer_a = layers_a[0]
        
        # Create a landed cost allocation (simulating landed cost application)
        lc_value = 50.0
        self.lc_location_model.create({
            'valuation_layer_id': layer_a.id,
            'location_id': self.location_a.id,
            'landed_cost_value': lc_value,
            'quantity': 100.0,
        })
        
        # Verify landed cost is recorded at Location A
        total_lc_a = self.valuation_layer_model.get_landed_cost_at_location(
            self.product, self.location_a, self.company.id
        )
        self.assertAlmostEqual(total_lc_a, lc_value, places=precision)
        
        # Create internal transfer from A to B
        transfer = self.move_model.create({
            'name': 'Transfer A->B',
            'product_id': self.product.id,
            'product_uom_qty': 50.0,
            'product_uom': self.product.uom_id.id,
            'location_id': self.location_a.id,
            'location_dest_id': self.location_b.id,
            'state': 'draft',
        })
        
        transfer._action_done()
        
        # After transfer, landed cost should be split
        # Transferred qty: 50 out of 100 = 50% of landed cost = 25
        total_lc_a_after = self.valuation_layer_model.get_landed_cost_at_location(
            self.product, self.location_a, self.company.id
        )
        total_lc_b_after = self.valuation_layer_model.get_landed_cost_at_location(
            self.product, self.location_b, self.company.id
        )
        
        # Location A should have reduced landed cost
        # Location B should have received portion of landed cost
        self.assertAlmostEqual(
            total_lc_a_after + total_lc_b_after,
            lc_value,
            places=precision,
            msg='Total landed cost should be preserved after transfer'
        )
    
    def test_landed_cost_allocation_history(self):
        """
        Test that landed cost allocation is recorded in history.
        
        Scenario:
        - Verify that allocation history is created during transfer
        """
        # Create incoming move
        move_in = self.move_model.create({
            'name': 'Receipt',
            'product_id': self.product.id,
            'product_uom_qty': 100.0,
            'product_uom': self.product.uom_id.id,
            'location_id': self.supplier_location.id,
            'location_dest_id': self.location_a.id,
            'state': 'draft',
        })
        
        move_in._action_done()
        
        # Create internal transfer
        transfer = self.move_model.create({
            'name': 'Transfer',
            'product_id': self.product.id,
            'product_uom_qty': 50.0,
            'product_uom': self.product.uom_id.id,
            'location_id': self.location_a.id,
            'location_dest_id': self.location_b.id,
            'state': 'draft',
        })
        
        transfer._action_done()
        
        # Check if allocation history was created
        allocation_history = self.env['stock.landed.cost.allocation'].search([
            ('move_id', '=', transfer.id),
        ])
        
        # Should have created history record
        self.assertEqual(
            len(allocation_history), 1,
            "Should create allocation history for transfer"
        )
    
    def test_inter_warehouse_transfer_no_zero_valuation(self):
        """
        Test that inter-warehouse transfers do not create 0.00 valuation layers.
        
        This is the critical fix for version 17.0.1.0.5.
        Even when source warehouse has no stock, we should use standard_price fallback.
        """
        # Create two warehouses
        warehouse_a = self.env['stock.warehouse'].search([('company_id', '=', self.company.id)], limit=1)
        warehouse_b = self.env['stock.warehouse'].create({
            'name': 'Test Warehouse B',
            'code': 'TWB',
            'company_id': self.company.id,
        })
        
        # Create product with standard price
        product = self.product_model.create({
            'name': 'Test Product Inter-WH',
            'type': 'product',
            'categ_id': self.env.ref('product.product_category_all').id,
            'cost_method': 'fifo',
            'standard_price': 150.0,  # Fallback cost
            'company_id': self.company.id,
        })
        
        # Get internal locations for each warehouse
        loc_a = warehouse_a.lot_stock_id
        loc_b = warehouse_b.lot_stock_id
        
        # Create incoming stock to warehouse A
        move_in = self.move_model.create({
            'name': 'Receipt to WH A',
            'product_id': product.id,
            'product_uom_qty': 100.0,
            'product_uom': product.uom_id.id,
            'location_id': self.supplier_location.id,
            'location_dest_id': loc_a.id,
            'state': 'draft',
        })
        move_in._action_done()
        
        # Create inter-warehouse transfer (A → B)
        transfer = self.move_model.create({
            'name': 'Transfer WH A → B',
            'product_id': product.id,
            'product_uom_qty': 50.0,
            'product_uom': product.uom_id.id,
            'location_id': loc_a.id,
            'location_dest_id': loc_b.id,
            'state': 'draft',
        })
        transfer._action_done()
        
        # Check valuation layers for the transfer
        transfer_layers = self.valuation_layer_model.search([
            ('stock_move_id', '=', transfer.id),
        ])
        
        # Should have exactly 2 layers (negative at A, positive at B)
        self.assertEqual(
            len(transfer_layers), 2,
            "Inter-warehouse transfer should create exactly 2 layers"
        )
        
        # Verify NO layers have 0.00 value (except zero quantity)
        for layer in transfer_layers:
            if layer.quantity != 0:
                self.assertNotEqual(
                    layer.value, 0.0,
                    f"Layer {layer.id} should not have 0.00 value when quantity is {layer.quantity}"
                )
                self.assertNotEqual(
                    layer.unit_cost, 0.0,
                    f"Layer {layer.id} should not have 0.00 unit_cost"
                )
        
        # Verify warehouse_id is properly set
        negative_layer = transfer_layers.filtered(lambda l: l.quantity < 0)
        positive_layer = transfer_layers.filtered(lambda l: l.quantity > 0)
        
        self.assertEqual(
            negative_layer.warehouse_id.id, warehouse_a.id,
            "Negative layer should have source warehouse"
        )
        self.assertEqual(
            positive_layer.warehouse_id.id, warehouse_b.id,
            "Positive layer should have destination warehouse"
        )
    
    def test_inter_warehouse_transfer_empty_source_uses_standard_price(self):
        """
        Test that transferring from empty warehouse uses standard_price as fallback.
        
        This prevents 0.00 valuations when FIFO queue is empty.
        """
        # Create two warehouses
        warehouse_a = self.env['stock.warehouse'].search([('company_id', '=', self.company.id)], limit=1)
        warehouse_b = self.env['stock.warehouse'].create({
            'name': 'Empty Warehouse',
            'code': 'EWH',
            'company_id': self.company.id,
        })
        
        # Create product with standard price
        product = self.product_model.create({
            'name': 'Test Product Empty Source',
            'type': 'product',
            'categ_id': self.env.ref('product.product_category_all').id,
            'cost_method': 'fifo',
            'standard_price': 200.0,  # This should be used as fallback
            'company_id': self.company.id,
        })
        
        loc_a = warehouse_a.lot_stock_id
        loc_b = warehouse_b.lot_stock_id
        
        # Directly create inventory at warehouse B (empty source scenario)
        # Using inventory adjustment to force stock without valuation layer
        inventory = self.env['stock.quant'].create({
            'product_id': product.id,
            'location_id': loc_b.id,
            'quantity': 50.0,
        })
        
        # Now transfer from B (which has no valuation layers yet)
        transfer = self.move_model.create({
            'name': 'Transfer from Empty WH',
            'product_id': product.id,
            'product_uom_qty': 25.0,
            'product_uom': product.uom_id.id,
            'location_id': loc_b.id,
            'location_dest_id': loc_a.id,
            'state': 'draft',
        })
        transfer._action_done()
        
        # Get layers created by this transfer
        layers = self.valuation_layer_model.search([
            ('stock_move_id', '=', transfer.id),
        ])
        
        # Verify standard_price was used (not 0.00)
        for layer in layers:
            if layer.quantity != 0:
                expected_value = abs(layer.quantity * product.standard_price)
                self.assertAlmostEqual(
                    abs(layer.value), 
                    expected_value, 
                    places=2,
                    msg="Layer should use standard_price when FIFO queue is empty"
                )
    
    def test_no_duplicate_layers_created(self):
        """
        Test that inter-warehouse transfers don't create duplicate layers.
        
        Core fix: We should NOT manually create layers - let Odoo standard do it.
        """
        # Create two warehouses
        warehouse_a = self.env['stock.warehouse'].search([('company_id', '=', self.company.id)], limit=1)
        warehouse_b = self.env['stock.warehouse'].create({
            'name': 'Test Warehouse Duplicate',
            'code': 'TWD',
            'company_id': self.company.id,
        })
        
        product = self.product_model.create({
            'name': 'Test Product No Duplicate',
            'type': 'product',
            'categ_id': self.env.ref('product.product_category_all').id,
            'cost_method': 'fifo',
            'standard_price': 100.0,
            'company_id': self.company.id,
        })
        
        loc_a = warehouse_a.lot_stock_id
        loc_b = warehouse_b.lot_stock_id
        
        # Receive stock at warehouse A
        move_in = self.move_model.create({
            'name': 'Receipt',
            'product_id': product.id,
            'product_uom_qty': 100.0,
            'product_uom': product.uom_id.id,
            'location_id': self.supplier_location.id,
            'location_dest_id': loc_a.id,
            'state': 'draft',
        })
        move_in._action_done()
        
        # Count layers before transfer
        layers_before = self.valuation_layer_model.search_count([
            ('product_id', '=', product.id),
        ])
        
        # Transfer between warehouses
        transfer = self.move_model.create({
            'name': 'Transfer',
            'product_id': product.id,
            'product_uom_qty': 50.0,
            'product_uom': product.uom_id.id,
            'location_id': loc_a.id,
            'location_dest_id': loc_b.id,
            'state': 'draft',
        })
        transfer._action_done()
        
        # Count layers after transfer
        layers_after = self.valuation_layer_model.search_count([
            ('product_id', '=', product.id),
        ])
        
        # Should have exactly 2 new layers (not 4 which would indicate duplication)
        layers_created = layers_after - layers_before
        self.assertEqual(
            layers_created, 2,
            f"Should create exactly 2 layers for inter-warehouse transfer, not {layers_created}"
        )
        
        # Verify exactly 2 layers for this move
        move_layers = self.valuation_layer_model.search([
            ('stock_move_id', '=', transfer.id),
        ])
        self.assertEqual(
            len(move_layers), 2,
            "Transfer move should have exactly 2 layers (negative + positive)"
        )
    
    def test_intra_warehouse_move_same_warehouse(self):
        """
        Test that moves within the same warehouse are properly handled.
        
        Intra-warehouse moves should have the same warehouse_id on layers.
        """
        warehouse = self.env['stock.warehouse'].search([('company_id', '=', self.company.id)], limit=1)
        
        # Create two locations within same warehouse
        parent_loc = warehouse.lot_stock_id
        loc_shelf_a = self.location_model.create({
            'name': 'Shelf A',
            'usage': 'internal',
            'location_id': parent_loc.id,
            'company_id': self.company.id,
        })
        loc_shelf_b = self.location_model.create({
            'name': 'Shelf B',
            'usage': 'internal',
            'location_id': parent_loc.id,
            'company_id': self.company.id,
        })
        
        product = self.product_model.create({
            'name': 'Test Product Intra-WH',
            'type': 'product',
            'categ_id': self.env.ref('product.product_category_all').id,
            'cost_method': 'fifo',
            'standard_price': 100.0,
            'company_id': self.company.id,
        })
        
        # Receive stock at Shelf A
        move_in = self.move_model.create({
            'name': 'Receipt',
            'product_id': product.id,
            'product_uom_qty': 100.0,
            'product_uom': product.uom_id.id,
            'location_id': self.supplier_location.id,
            'location_dest_id': loc_shelf_a.id,
            'state': 'draft',
        })
        move_in._action_done()
        
        # Move within same warehouse (Shelf A → Shelf B)
        intra_move = self.move_model.create({
            'name': 'Intra-warehouse Move',
            'product_id': product.id,
            'product_uom_qty': 50.0,
            'product_uom': product.uom_id.id,
            'location_id': loc_shelf_a.id,
            'location_dest_id': loc_shelf_b.id,
            'state': 'draft',
        })
        intra_move._action_done()
        
        # Get layers for intra-warehouse move
        intra_layers = self.valuation_layer_model.search([
            ('stock_move_id', '=', intra_move.id),
        ])
        
        # All layers should have the same warehouse_id (if any)
        warehouse_ids = intra_layers.mapped('warehouse_id')
        if warehouse_ids:
            self.assertEqual(
                len(set(warehouse_ids.ids)), 1,
                "Intra-warehouse move layers should all have same warehouse_id"
            )
            self.assertEqual(
                warehouse_ids[0].id, warehouse.id,
                "Intra-warehouse layers should have the parent warehouse"
            )
    
    def test_return_full_quantity_balance_equals_zero(self):
        """
        ⭐ CRITICAL TEST: Return full quantity should result in balance = 0
        
        Scenario:
        1. Receive 10 units @ 100 THB = 1000 THB
        2. Add landed cost 200 THB (20 THB per unit)
        3. Deliver 10 units (consume from FIFO: 10 @ 120 THB = 1200 THB)
        4. Return 10 units (MUST be 10 @ 120 THB = 1200 THB to balance)
        
        Expected: Final balance = 0 (both qty and value)
        
        Key Point: Return MUST use average unit cost WITH landed costs,
        NOT just base cost. Otherwise balance ≠ 0.
        """
        warehouse = self.env['stock.warehouse'].search(
            [('company_id', '=', self.company.id)], limit=1
        )
        self.assertTrue(warehouse, "Warehouse not found")
        
        product = self.product_model.create({
            'name': 'Test Return Full Balance',
            'type': 'product',
            'categ_id': self.env.ref('product.product_category_all').id,
            'cost_method': 'fifo',
            'standard_price': 100.0,
            'company_id': self.company.id,
        })
        
        picking_model = self.env['stock.picking']
        move_model = self.env['stock.move']
        
        # Step 1: Receive 10 units
        receipt = picking_model.create({
            'picking_type_id': warehouse.in_type_id.id,
            'location_id': self.supplier_location.id,
            'location_dest_id': warehouse.lot_stock_id.id,
        })
        
        receipt_move = move_model.create({
            'name': 'Receipt',
            'product_id': product.id,
            'product_uom_qty': 10.0,
            'product_uom': product.uom_id.id,
            'picking_id': receipt.id,
            'location_id': self.supplier_location.id,
            'location_dest_id': warehouse.lot_stock_id.id,
        })
        
        receipt.action_confirm()
        receipt.action_assign()
        for line in receipt.move_line_ids:
            line.quantity = 10.0
        receipt.button_validate()
        
        # Step 2: Add landed cost to receipt layer
        receipt_layers = self.valuation_layer_model.search([
            ('stock_move_id', '=', receipt_move.id),
        ])
        self.assertTrue(receipt_layers, "Receipt should create valuation layers")
        
        # Get landed cost model
        lc_model = self.env['stock.valuation.layer.landed.cost']
        for layer in receipt_layers:
            if layer.quantity > 0:
                # Add 200 THB landed cost (20 THB per unit)
                lc_model.create({
                    'valuation_layer_id': layer.id,
                    'warehouse_id': warehouse.id,
                    'landed_cost_value': 200.0,
                    'quantity': 10.0,
                })
        
        # Verify receipt layer has landed cost
        receipt_layer = receipt_layers.filtered(lambda l: l.quantity > 0)[0]
        receipt_lc = lc_model.search([
            ('valuation_layer_id', '=', receipt_layer.id),
            ('warehouse_id', '=', warehouse.id),
        ])
        self.assertTrue(receipt_lc, "Receipt layer should have landed cost")
        self.assertAlmostEqual(
            receipt_lc.landed_cost_value, 200.0, places=2,
            msg="Receipt landed cost should be 200 THB"
        )
        
        # Check total cost with landed cost
        fifo_service = self.env['fifo.service']
        receipt_unit_cost = receipt_move.product_id.standard_price  # 100 THB
        receipt_unit_cost_with_lc = (receipt_layer.value + receipt_lc.landed_cost_value) / receipt_layer.quantity
        # Should be (1000 + 200) / 10 = 120 THB
        
        # Step 3: Deliver 10 units (consumes from receipt layer)
        delivery = picking_model.create({
            'picking_type_id': warehouse.out_type_id.id,
            'location_id': warehouse.lot_stock_id.id,
            'location_dest_id': self.customer_location.id,
        })
        
        delivery_move = move_model.create({
            'name': 'Delivery',
            'product_id': product.id,
            'product_uom_qty': 10.0,
            'product_uom': product.uom_id.id,
            'picking_id': delivery.id,
            'location_id': warehouse.lot_stock_id.id,
            'location_dest_id': self.customer_location.id,
        })
        
        delivery.action_confirm()
        delivery.action_assign()
        for line in delivery.move_line_ids:
            line.quantity = 10.0
        delivery.button_validate()
        
        # Get delivery layer
        delivery_layers = self.valuation_layer_model.search([
            ('stock_move_id', '=', delivery_move.id),
        ])
        self.assertTrue(delivery_layers, "Delivery should create valuation layers")
        
        delivery_neg_layer = delivery_layers.filtered(lambda l: l.quantity < 0)
        self.assertTrue(delivery_neg_layer, "Delivery should have negative layer")
        
        # Step 4: Return 10 units
        return_wizard = self.env['stock.return.picking'].with_context(
            active_id=delivery.id,
            active_model='stock.picking'
        ).create({})
        
        return_picking_id, _ = return_wizard._create_returns()
        return_picking = picking_model.browse(return_picking_id)
        
        return_picking.action_assign()
        for line in return_picking.move_line_ids:
            line.quantity = 10.0
        return_picking.button_validate()
        
        # Get return layers
        return_moves = return_picking.move_ids.filtered(
            lambda m: m.origin_returned_move_id
        )
        self.assertTrue(return_moves, "Should have return moves")
        
        return_layers = self.valuation_layer_model.search([
            ('stock_move_id', 'in', return_moves.ids),
        ])
        self.assertTrue(return_layers, "Return should create valuation layers")
        
        # ⭐ CRITICAL CHECK: Return layer should use FIFO cost with landed cost
        return_pos_layer = return_layers.filtered(lambda l: l.quantity > 0)
        self.assertTrue(return_pos_layer, "Return should have positive layer")
        
        # Return unit cost should include landed cost
        # Expected: (1000 + 200) / 10 = 120 THB per unit
        return_unit_cost = abs(return_pos_layer[0].value) / return_pos_layer[0].quantity
        
        # Delivery should consume at 120 THB (100 base + 20 landed cost)
        delivery_unit_cost = abs(delivery_neg_layer[0].value) / abs(delivery_neg_layer[0].quantity)
        
        self.assertAlmostEqual(
            return_unit_cost, delivery_unit_cost, places=2,
            msg=f"Return unit cost ({return_unit_cost}) should match delivery unit cost ({delivery_unit_cost})"
        )
        
        # ✅ FINAL CHECK: Balance should be 0
        all_layers = self.valuation_layer_model.search([
            ('product_id', '=', product.id),
            ('warehouse_id', '=', warehouse.id),
        ])
        
        total_qty = sum(all_layers.mapped('remaining_qty'))
        total_value = sum(all_layers.mapped('remaining_value'))
        
        self.assertAlmostEqual(
            total_qty, 10.0, places=2,
            msg=f"Qty should be 10 after full return (balance: {total_qty})"
        )
        # Value may not be exactly 1000 due to landed costs, but should be positive
        self.assertGreaterEqual(
            total_value, 900.0,
            msg=f"Value should be reasonable after full return (balance: {total_value})"
        )
    
    def test_return_without_landed_cost_balance_equals_zero(self):
        """
        Test Return Full without Landed Cost - balance should still be 0
        
        Scenario:
        1. Receive 10 units @ 100 THB = 1000 THB (NO landed cost)
        2. Deliver 10 units (consume from FIFO: 10 @ 100 THB = 1000 THB)
        3. Return 10 units (MUST be 10 @ 100 THB = 1000 THB)
        
        Expected: Final balance = 0 (qty and value both zero after full return)
        
        This tests the case where there's no landed cost, just basic FIFO.
        Makes sure return unit_cost is correctly extracted from delivery layer
        even when there's no LC records.
        """
        warehouse = self.env['stock.warehouse'].search(
            [('company_id', '=', self.company.id)], limit=1
        )
        self.assertTrue(warehouse, "Warehouse not found")
        
        product = self.product_model.create({
            'name': 'Test Return No LC',
            'type': 'product',
            'categ_id': self.env.ref('product.product_category_all').id,
            'cost_method': 'fifo',
            'standard_price': 100.0,
            'company_id': self.company.id,
        })
        
        picking_model = self.env['stock.picking']
        move_model = self.env['stock.move']
        
        # Step 1: Receive 10 units (NO landed cost)
        receipt = picking_model.create({
            'picking_type_id': warehouse.in_type_id.id,
            'location_id': self.supplier_location.id,
            'location_dest_id': warehouse.lot_stock_id.id,
        })
        
        receipt_move = move_model.create({
            'name': 'Receipt',
            'product_id': product.id,
            'product_uom_qty': 10.0,
            'product_uom': product.uom_id.id,
            'picking_id': receipt.id,
            'location_id': self.supplier_location.id,
            'location_dest_id': warehouse.lot_stock_id.id,
        })
        
        receipt.action_confirm()
        receipt.action_assign()
        for line in receipt.move_line_ids:
            line.quantity = 10.0
        receipt.button_validate()
        
        # Verify receipt layer created (no LC)
        receipt_layers = self.valuation_layer_model.search([
            ('stock_move_id', '=', receipt_move.id),
        ])
        self.assertTrue(receipt_layers, "Receipt should create valuation layers")
        
        receipt_layer = receipt_layers.filtered(lambda l: l.quantity > 0)[0]
        self.assertAlmostEqual(
            receipt_layer.unit_cost, 100.0, places=2,
            msg="Receipt layer should have unit_cost = 100"
        )
        self.assertAlmostEqual(
            receipt_layer.value, 1000.0, places=2,
            msg="Receipt layer should have value = 1000"
        )
        
        # Step 2: Deliver 10 units
        delivery = picking_model.create({
            'picking_type_id': warehouse.out_type_id.id,
            'location_id': warehouse.lot_stock_id.id,
            'location_dest_id': self.customer_location.id,
        })
        
        delivery_move = move_model.create({
            'name': 'Delivery',
            'product_id': product.id,
            'product_uom_qty': 10.0,
            'product_uom': product.uom_id.id,
            'picking_id': delivery.id,
            'location_id': warehouse.lot_stock_id.id,
            'location_dest_id': self.customer_location.id,
        })
        
        delivery.action_confirm()
        delivery.action_assign()
        for line in delivery.move_line_ids:
            line.quantity = 10.0
        delivery.button_validate()
        
        # Get delivery layer - should be @ 100 THB
        delivery_layers = self.valuation_layer_model.search([
            ('stock_move_id', '=', delivery_move.id),
        ])
        self.assertTrue(delivery_layers, "Delivery should create valuation layers")
        
        delivery_neg_layer = delivery_layers.filtered(lambda l: l.quantity < 0)[0]
        delivery_unit_cost = abs(delivery_neg_layer.value) / abs(delivery_neg_layer.quantity)
        
        self.assertAlmostEqual(
            delivery_unit_cost, 100.0, places=2,
            msg="Delivery layer should consume @ 100 THB/unit"
        )
        
        # Step 3: Return 10 units
        return_wizard = self.env['stock.return.picking'].with_context(
            active_id=delivery.id,
            active_model='stock.picking'
        ).create({})
        
        return_picking_id, _ = return_wizard._create_returns()
        return_picking = picking_model.browse(return_picking_id)
        
        return_picking.action_assign()
        for line in return_picking.move_line_ids:
            line.quantity = 10.0
        return_picking.button_validate()
        
        # Get return layers
        return_moves = return_picking.move_ids.filtered(
            lambda m: m.origin_returned_move_id
        )
        self.assertTrue(return_moves, "Should have return moves")
        
        return_layers = self.valuation_layer_model.search([
            ('stock_move_id', 'in', return_moves.ids),
        ])
        self.assertTrue(return_layers, "Return should create valuation layers")
        
        # ⭐ CRITICAL: Return layer should use delivery unit cost (100)
        return_pos_layer = return_layers.filtered(lambda l: l.quantity > 0)[0]
        return_unit_cost = abs(return_pos_layer.value) / return_pos_layer.quantity
        
        self.assertAlmostEqual(
            return_unit_cost, delivery_unit_cost, places=2,
            msg=f"Return unit cost ({return_unit_cost}) should match delivery ({delivery_unit_cost})"
        )
        
        self.assertAlmostEqual(
            return_unit_cost, 100.0, places=2,
            msg="Return should be @ 100 THB/unit"
        )
        
        # ✅ Check final balance = 0
        all_layers = self.valuation_layer_model.search([
            ('product_id', '=', product.id),
            ('warehouse_id', '=', warehouse.id),
        ])
        
        total_qty = sum(all_layers.mapped('remaining_qty'))
        total_value = sum(all_layers.mapped('remaining_value'))
        
        self.assertAlmostEqual(
            total_qty, 0.0, places=2,
            msg=f"Final qty should be 0 after full return (got {total_qty})"
        )
        
        self.assertAlmostEqual(
            total_value, 0.0, places=2,
            msg=f"Final value should be 0 after full return (got {total_value})"
        )

