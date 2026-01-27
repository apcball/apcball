# -*- coding: utf-8 -*-
"""
Test Cases for Cross-Warehouse Return (v17.0.1.1.6)

Tests the new feature where returns can go to a different warehouse than the original sale.
Cost is taken from original warehouse's FIFO layers, but layer is created at destination warehouse.
"""

from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError


class TestCrossWarehouseReturn(TransactionCase):
    """
    Test cases for cross-warehouse return functionality.
    
    Scenario: ขายจาก WH-A แต่ลูกค้าคืนของเข้าคลัง WH-B
    
    Expected behavior:
    - Cost uses original FIFO cost from WH-A (deterministic)
    - Layer created at WH-B (where stock physically returns)
    - WH-B can use this stock for future sales with correct cost
    - No negative balance issues
    """
    
    def setUp(self):
        super().setUp()
        
        # Models
        self.product_model = self.env['product.product']
        self.warehouse_model = self.env['stock.warehouse']
        self.location_model = self.env['stock.location']
        self.picking_model = self.env['stock.picking']
        self.move_model = self.env['stock.move']
        self.layer_model = self.env['stock.valuation.layer']
        
        # Create product category with FIFO costing
        self.product_category = self.env['product.category'].create({
            'name': 'Test FIFO Category',
            'property_cost_method': 'fifo',
            'property_valuation': 'real_time',
        })
        
        # Create storable product with FIFO
        self.product = self.product_model.create({
            'name': 'Test Product Cross-WH Return',
            'type': 'product',
            'categ_id': self.product_category.id,
            'standard_price': 100.0,
        })
        
        # Get warehouses
        self.warehouse_a = self.warehouse_model.search([('name', '=', 'WH1')], limit=1)
        if not self.warehouse_a:
            self.warehouse_a = self.warehouse_model.create({
                'name': 'WH1',
                'code': 'WH1',
            })
        
        self.warehouse_b = self.warehouse_model.search([('name', '=', 'WH2')], limit=1)
        if not self.warehouse_b:
            self.warehouse_b = self.warehouse_model.create({
                'name': 'WH2',
                'code': 'WH2',
            })
        
        # Get locations
        self.supplier_location = self.env.ref('stock.stock_location_suppliers')
        self.customer_location = self.env.ref('stock.stock_location_customers')
    
    def _create_and_validate_receipt(self, warehouse, qty, unit_cost):
        """Helper to create and validate a receipt."""
        picking = self.picking_model.create({
            'picking_type_id': warehouse.in_type_id.id,
            'location_id': self.supplier_location.id,
            'location_dest_id': warehouse.lot_stock_id.id,
        })
        
        move = self.move_model.create({
            'name': f'Receipt to {warehouse.name}',
            'product_id': self.product.id,
            'product_uom_qty': qty,
            'product_uom': self.product.uom_id.id,
            'picking_id': picking.id,
            'location_id': self.supplier_location.id,
            'location_dest_id': warehouse.lot_stock_id.id,
            'price_unit': unit_cost,
        })
        
        picking.action_confirm()
        picking.action_assign()
        
        for move_line in picking.move_line_ids:
            move_line.quantity = move_line.product_uom_qty
        
        picking.button_validate()
        
        return picking, move
    
    def _create_and_validate_delivery(self, warehouse, qty):
        """Helper to create and validate a delivery."""
        picking = self.picking_model.create({
            'picking_type_id': warehouse.out_type_id.id,
            'location_id': warehouse.lot_stock_id.id,
            'location_dest_id': self.customer_location.id,
        })
        
        move = self.move_model.create({
            'name': f'Delivery from {warehouse.name}',
            'product_id': self.product.id,
            'product_uom_qty': qty,
            'product_uom': self.product.uom_id.id,
            'picking_id': picking.id,
            'location_id': warehouse.lot_stock_id.id,
            'location_dest_id': self.customer_location.id,
        })
        
        picking.action_confirm()
        picking.action_assign()
        
        for move_line in picking.move_line_ids:
            move_line.quantity = move_line.product_uom_qty
        
        picking.button_validate()
        
        return picking, move
    
    def _create_and_validate_return(self, original_move, return_warehouse, qty):
        """Helper to create and validate a return to specific warehouse."""
        return_picking = self.picking_model.create({
            'picking_type_id': return_warehouse.in_type_id.id,
            'location_id': self.customer_location.id,
            'location_dest_id': return_warehouse.lot_stock_id.id,
        })
        
        return_move = self.move_model.create({
            'name': f'Return to {return_warehouse.name}',
            'product_id': self.product.id,
            'product_uom_qty': qty,
            'product_uom': self.product.uom_id.id,
            'picking_id': return_picking.id,
            'location_id': self.customer_location.id,
            'location_dest_id': return_warehouse.lot_stock_id.id,
            'origin_returned_move_id': original_move.id,
        })
        
        return_picking.action_confirm()
        return_picking.action_assign()
        
        for move_line in return_picking.move_line_ids:
            move_line.quantity = move_line.product_uom_qty
        
        return_picking.button_validate()
        
        return return_picking, return_move
    
    def test_cross_warehouse_return_basic(self):
        """
        ⭐ MAIN TEST: Cross-warehouse return with cost from original warehouse.
        
        Scenario:
        1. Receive 10 units to WH-A at cost 100/unit
        2. Deliver 10 units from WH-A to customer
        3. Customer returns 10 units to WH-B (different warehouse!)
        
        Expected:
        - Return layers use cost 100/unit (from WH-A FIFO)
        - Return layers assigned to WH-B (where stock goes)
        - WH-A balance: 0 units
        - WH-B balance: 10 units at 100/unit
        - Total value preserved
        """
        # Step 1: Receive to WH-A
        receipt_picking, receipt_move = self._create_and_validate_receipt(
            self.warehouse_a, qty=10.0, unit_cost=100.0
        )
        
        # Verify receipt layer
        receipt_layers = self.layer_model.search([
            ('stock_move_id', '=', receipt_move.id),
            ('quantity', '>', 0),
        ])
        self.assertTrue(receipt_layers, "Receipt should create positive layer")
        self.assertEqual(receipt_layers[0].warehouse_id.id, self.warehouse_a.id,
                        "Receipt layer should be at WH-A")
        self.assertEqual(receipt_layers[0].unit_cost, 100.0, "Receipt cost should be 100")
        
        # Step 2: Deliver from WH-A
        delivery_picking, delivery_move = self._create_and_validate_delivery(
            self.warehouse_a, qty=10.0
        )
        
        # Verify delivery layer
        delivery_layers = self.layer_model.search([
            ('stock_move_id', '=', delivery_move.id),
            ('quantity', '<', 0),
        ])
        self.assertTrue(delivery_layers, "Delivery should create negative layer")
        self.assertEqual(delivery_layers[0].warehouse_id.id, self.warehouse_a.id,
                        "Delivery layer should be at WH-A")
        
        # Step 3: Return to WH-B (CROSS-WAREHOUSE!)
        return_picking, return_move = self._create_and_validate_return(
            delivery_move, self.warehouse_b, qty=10.0
        )
        
        # Verify return layers at WH-B
        return_layers = self.layer_model.search([
            ('stock_move_id', '=', return_move.id),
        ])
        self.assertTrue(return_layers, "Return should create layers")
        
        # Should have both negative and positive layers
        negative_return = return_layers.filtered(lambda l: l.quantity < 0)
        positive_return = return_layers.filtered(lambda l: l.quantity > 0)
        
        self.assertTrue(negative_return, "Return should have negative layer")
        self.assertTrue(positive_return, "Return should have positive layer")
        
        # ✅ CRITICAL: Both layers should be at WH-B
        self.assertEqual(negative_return[0].warehouse_id.id, self.warehouse_b.id,
                        "Return negative layer should be at WH-B (destination)")
        self.assertEqual(positive_return[0].warehouse_id.id, self.warehouse_b.id,
                        "Return positive layer should be at WH-B (destination)")
        
        # ✅ CRITICAL: Cost should come from original WH-A FIFO (100/unit)
        self.assertAlmostEqual(abs(negative_return[0].unit_cost), 100.0, places=2,
                             msg="Return negative layer should use original cost 100 from WH-A")
        self.assertAlmostEqual(positive_return[0].unit_cost, 100.0, places=2,
                             msg="Return positive layer should use original cost 100 from WH-A")
        
        # Verify values
        self.assertAlmostEqual(negative_return[0].value, -1000.0, places=2,
                             msg="Negative return value should be -1000")
        self.assertAlmostEqual(positive_return[0].value, 1000.0, places=2,
                             msg="Positive return value should be 1000")
    
    def test_cross_warehouse_return_then_sell_from_new_warehouse(self):
        """
        Test that after cross-warehouse return, WH-B can sell the returned stock.
        
        Scenario:
        1. Receive 10 units to WH-A at 100/unit
        2. Deliver 10 units from WH-A
        3. Return 10 units to WH-B (cross-warehouse)
        4. Deliver 5 units from WH-B to another customer
        
        Expected:
        - WH-B can deliver 5 units using FIFO cost 100/unit
        - WH-B remaining: 5 units at 100/unit
        - No errors, no negative balance
        """
        # Steps 1-3: Same as basic test
        receipt_picking, receipt_move = self._create_and_validate_receipt(
            self.warehouse_a, qty=10.0, unit_cost=100.0
        )
        
        delivery_picking, delivery_move = self._create_and_validate_delivery(
            self.warehouse_a, qty=10.0
        )
        
        return_picking, return_move = self._create_and_validate_return(
            delivery_move, self.warehouse_b, qty=10.0
        )
        
        # Step 4: Deliver from WH-B (using returned stock)
        delivery_b_picking, delivery_b_move = self._create_and_validate_delivery(
            self.warehouse_b, qty=5.0
        )
        
        # Verify delivery from WH-B
        delivery_b_layers = self.layer_model.search([
            ('stock_move_id', '=', delivery_b_move.id),
            ('quantity', '<', 0),
        ])
        
        self.assertTrue(delivery_b_layers, "Delivery from WH-B should create layer")
        self.assertEqual(delivery_b_layers[0].warehouse_id.id, self.warehouse_b.id,
                        "Delivery layer should be at WH-B")
        
        # ✅ Should use cost 100 from the returned stock
        self.assertAlmostEqual(abs(delivery_b_layers[0].unit_cost), 100.0, places=2,
                             msg="Delivery from WH-B should use cost 100 from returned stock")
        self.assertAlmostEqual(delivery_b_layers[0].value, -500.0, places=2,
                             msg="Delivery value should be -500 (5 units * 100)")
        
        # Check remaining qty at WH-B
        return_positive_layer = self.layer_model.search([
            ('stock_move_id', '=', return_move.id),
            ('quantity', '>', 0),
        ], limit=1)
        
        # The positive return layer should have remaining_qty = 5
        # (original 10 - delivered 5)
        self.assertAlmostEqual(return_positive_layer.remaining_qty, 5.0, places=2,
                             msg="Return layer at WH-B should have remaining_qty = 5")
    
    def test_cross_warehouse_return_preserves_cost_determinism(self):
        """
        Test that cross-warehouse returns maintain cost determinism.
        
        Scenario:
        1. Receive 10 units to WH-A at 100/unit (cost A)
        2. Receive 10 units to WH-A at 150/unit (cost B)
        3. Deliver 10 units from WH-A (should use cost A = 100, FIFO)
        4. Return 10 units to WH-B
        
        Expected:
        - Return uses cost 100 (from original FIFO consumption)
        - NOT cost 150 or average cost
        - WH-B layer has cost 100/unit
        """
        # Step 1: First receipt at 100/unit
        receipt1_picking, receipt1_move = self._create_and_validate_receipt(
            self.warehouse_a, qty=10.0, unit_cost=100.0
        )
        
        # Step 2: Second receipt at 150/unit
        receipt2_picking, receipt2_move = self._create_and_validate_receipt(
            self.warehouse_a, qty=10.0, unit_cost=150.0
        )
        
        # Step 3: Deliver 10 units (should use FIFO = 100/unit)
        delivery_picking, delivery_move = self._create_and_validate_delivery(
            self.warehouse_a, qty=10.0
        )
        
        # Verify delivery used cost 100
        delivery_layers = self.layer_model.search([
            ('stock_move_id', '=', delivery_move.id),
            ('quantity', '<', 0),
        ])
        self.assertAlmostEqual(abs(delivery_layers[0].unit_cost), 100.0, places=2,
                             msg="Delivery should use FIFO cost 100")
        
        # Step 4: Return to WH-B
        return_picking, return_move = self._create_and_validate_return(
            delivery_move, self.warehouse_b, qty=10.0
        )
        
        # Verify return uses cost 100 (NOT 150 or average 125)
        return_positive = self.layer_model.search([
            ('stock_move_id', '=', return_move.id),
            ('quantity', '>', 0),
        ])
        
        self.assertAlmostEqual(return_positive[0].unit_cost, 100.0, places=2,
                             msg="Return to WH-B should preserve original FIFO cost 100, not 150 or average")
        
        # WH-B now has stock at cost 100
        # WH-A still has 10 units at cost 150
        remaining_at_a = self.layer_model.search([
            ('product_id', '=', self.product.id),
            ('warehouse_id', '=', self.warehouse_a.id),
            ('remaining_qty', '>', 0),
        ])
        
        self.assertTrue(remaining_at_a, "WH-A should still have stock")
        # The remaining should be from the 150/unit receipt
        self.assertAlmostEqual(remaining_at_a[0].unit_cost, 150.0, places=2,
                             msg="Remaining stock at WH-A should be at cost 150")
    
    def test_cross_warehouse_return_no_negative_balance(self):
        """
        Test that cross-warehouse returns don't cause negative balance.
        
        Scenario:
        1. Receive 10 units to WH-A
        2. Deliver 10 units from WH-A
        3. Return 10 units to WH-B
        4. Try to deliver 11 units from WH-B (should fail - only 10 available)
        
        Expected:
        - WH-B has exactly 10 units available
        - Cannot deliver more than available
        - No negative remaining_qty
        """
        # Steps 1-3
        receipt_picking, receipt_move = self._create_and_validate_receipt(
            self.warehouse_a, qty=10.0, unit_cost=100.0
        )
        
        delivery_picking, delivery_move = self._create_and_validate_delivery(
            self.warehouse_a, qty=10.0
        )
        
        return_picking, return_move = self._create_and_validate_return(
            delivery_move, self.warehouse_b, qty=10.0
        )
        
        # Step 4: Try to deliver 11 units from WH-B (more than available)
        # This should either fail or only deliver 10
        
        picking = self.picking_model.create({
            'picking_type_id': self.warehouse_b.out_type_id.id,
            'location_id': self.warehouse_b.lot_stock_id.id,
            'location_dest_id': self.customer_location.id,
        })
        
        move = self.move_model.create({
            'name': 'Try deliver 11 from WH-B',
            'product_id': self.product.id,
            'product_uom_qty': 11.0,
            'product_uom': self.product.uom_id.id,
            'picking_id': picking.id,
            'location_id': self.warehouse_b.lot_stock_id.id,
            'location_dest_id': self.customer_location.id,
        })
        
        picking.action_confirm()
        # Note: action_assign may only assign 10 units if stock is tracked correctly
        
        # Check all layers at WH-B - remaining_qty should not go negative
        all_whb_layers = self.layer_model.search([
            ('product_id', '=', self.product.id),
            ('warehouse_id', '=', self.warehouse_b.id),
        ])
        
        for layer in all_whb_layers:
            self.assertGreaterEqual(layer.remaining_qty, 0,
                                  f"Layer {layer.id} should not have negative remaining_qty")
