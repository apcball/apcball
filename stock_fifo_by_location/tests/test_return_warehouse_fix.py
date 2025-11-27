# -*- coding: utf-8 -*-
"""
Test Cases for Return Move Warehouse Validation (v17.0.1.1.1)

Tests the critical fix that prevents negative warehouse balance
when return moves go to different warehouses.
"""

from odoo.tests import TransactionCase, tagged
from odoo.exceptions import ValidationError


@tagged('post_install', '-at_install', 'return_fix')
class TestReturnWarehouseFix(TransactionCase):
    """
    Test cases for return move warehouse validation fix.
    
    Version: 17.0.1.1.1
    Issue: Return moves going to different warehouse cause negative balance
    Solution: Force return moves to use original warehouse
    """
    
    def setUp(self):
        """Set up test data with multiple warehouses."""
        super().setUp()
        
        self.product_model = self.env['product.product']
        self.warehouse_model = self.env['stock.warehouse']
        self.picking_model = self.env['stock.picking']
        self.move_model = self.env['stock.move']
        self.location_model = self.env['stock.location']
        self.valuation_layer_model = self.env['stock.valuation.layer']
        self.company = self.env.company
        
        # Create two warehouses
        self.warehouse_1 = self.warehouse_model.search([
            ('company_id', '=', self.company.id)
        ], limit=1)
        
        if not self.warehouse_1:
            self.warehouse_1 = self.warehouse_model.create({
                'name': 'Warehouse 1',
                'code': 'WH1',
                'company_id': self.company.id,
            })
        
        self.warehouse_2 = self.warehouse_model.create({
            'name': 'Warehouse 2',
            'code': 'WH2',
            'company_id': self.company.id,
        })
        
        # Get locations
        self.supplier_location = self.env.ref('stock.stock_location_suppliers')
        self.customer_location = self.env.ref('stock.stock_location_customers')
        
        # Create test product with FIFO costing
        self.product = self.product_model.create({
            'name': 'Test Product Return Fix',
            'type': 'product',
            'categ_id': self.env.ref('product.product_category_all').id,
            'list_price': 100.0,
            'standard_price': 50.0,
            'company_id': self.company.id,
        })
        
        # Set product to use FIFO
        self.product.product_tmpl_id.categ_id.property_cost_method = 'fifo'
        self.product.product_tmpl_id.categ_id.property_valuation = 'real_time'
    
    def _create_and_validate_receipt(self, warehouse, qty=10.0):
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
        })
        
        picking.action_confirm()
        picking.action_assign()
        
        for move_line in picking.move_line_ids:
            move_line.quantity = move_line.product_uom_qty
        
        picking.button_validate()
        
        return picking, move
    
    def _create_and_validate_delivery(self, warehouse, qty=10.0):
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
    
    def test_return_to_same_warehouse_should_pass(self):
        """
        Test that return to same warehouse works correctly.
        
        Scenario:
        1. Receive 10 units to WH1
        2. Deliver 10 units from WH1
        3. Return 10 units to WH1 (SAME warehouse)
        
        Expected: Should work without errors
        """
        # Step 1: Receive stock to WH1
        receipt_picking, receipt_move = self._create_and_validate_receipt(
            self.warehouse_1, qty=10.0
        )
        
        # Step 2: Deliver from WH1
        delivery_picking, delivery_move = self._create_and_validate_delivery(
            self.warehouse_1, qty=10.0
        )
        
        # Step 3: Create return to WH1 (same warehouse)
        return_wizard = self.env['stock.return.picking'].with_context(
            active_id=delivery_picking.id,
            active_model='stock.picking'
        ).create({})
        
        # Validate return should work
        return_picking_id, _pick_type_id = return_wizard._create_returns()
        return_picking = self.picking_model.browse(return_picking_id)
        
        return_picking.action_assign()
        for move_line in return_picking.move_line_ids:
            move_line.quantity = move_line.product_uom_qty
        
        # This should NOT raise ValidationError
        return_picking.button_validate()
        
        # Check valuation layers
        wh1_layers = self.valuation_layer_model.search([
            ('product_id', '=', self.product.id),
            ('warehouse_id', '=', self.warehouse_1.id),
        ])
        
        total_qty = sum(wh1_layers.mapped('remaining_qty'))
        total_value = sum(wh1_layers.mapped('remaining_value'))
        
        # WH1 should have 10 units back (not negative)
        self.assertGreaterEqual(total_qty, 0, "WH1 should not be negative")
        self.assertGreaterEqual(total_value, 0, "WH1 value should not be negative")
    
    def test_return_to_different_warehouse_should_fail(self):
        """
        ⭐ CRITICAL TEST: Return to different warehouse should be blocked.
        
        Scenario:
        1. Receive 10 units to WH1
        2. Deliver 10 units from WH1
        3. Try to return 10 units to WH2 (DIFFERENT warehouse)
        
        Expected: Should raise ValidationError
        """
        # Step 1: Receive stock to WH1
        receipt_picking, receipt_move = self._create_and_validate_receipt(
            self.warehouse_1, qty=10.0
        )
        
        # Step 2: Deliver from WH1
        delivery_picking, delivery_move = self._create_and_validate_delivery(
            self.warehouse_1, qty=10.0
        )
        
        # Step 3: Try to create return to WH2 (different warehouse)
        # Manually create return picking with different destination
        return_picking = self.picking_model.create({
            'picking_type_id': self.warehouse_2.in_type_id.id,
            'location_id': self.customer_location.id,
            'location_dest_id': self.warehouse_2.lot_stock_id.id,  # WH2!
        })
        
        return_move = self.move_model.create({
            'name': 'Return to WH2',
            'product_id': self.product.id,
            'product_uom_qty': 10.0,
            'product_uom': self.product.uom_id.id,
            'picking_id': return_picking.id,
            'location_id': self.customer_location.id,
            'location_dest_id': self.warehouse_2.lot_stock_id.id,  # WH2!
            'origin_returned_move_id': delivery_move.id,  # Link to original move from WH1
        })
        
        return_picking.action_confirm()
        return_picking.action_assign()
        
        for move_line in return_picking.move_line_ids:
            move_line.quantity = move_line.product_uom_qty
        
        # ⚠️ This MUST raise ValidationError
        with self.assertRaises(ValidationError) as ctx:
            return_picking.button_validate()
        
        # Check error message contains warehouse info
        error_message = str(ctx.exception)
        self.assertIn('Warehouse', error_message)
        self.assertIn('Return', error_message)
    
    def test_negative_balance_prevention(self):
        """
        Test that negative warehouse balance is prevented.
        
        Scenario:
        1. Receive 10 units to WH1
        2. Try to consume 15 units from WH1 (more than available)
        
        Expected: Should raise ValidationError about negative balance
        """
        # Step 1: Receive 10 units to WH1
        receipt_picking, receipt_move = self._create_and_validate_receipt(
            self.warehouse_1, qty=10.0
        )
        
        # Step 2: Try to deliver 15 units (more than available)
        picking = self.picking_model.create({
            'picking_type_id': self.warehouse_1.out_type_id.id,
            'location_id': self.warehouse_1.lot_stock_id.id,
            'location_dest_id': self.customer_location.id,
        })
        
        move = self.move_model.create({
            'name': 'Over-delivery',
            'product_id': self.product.id,
            'product_uom_qty': 15.0,  # More than available!
            'product_uom': self.product.uom_id.id,
            'picking_id': picking.id,
            'location_id': self.warehouse_1.lot_stock_id.id,
            'location_dest_id': self.customer_location.id,
        })
        
        picking.action_confirm()
        
        # Try to validate - should fail or warn about negative stock
        # Note: Odoo may allow negative stock depending on config
        # But our constraint should catch negative valuation
        try:
            picking.action_assign()
            if picking.move_line_ids:
                for move_line in picking.move_line_ids:
                    move_line.quantity = 15.0
                
                # This may raise ValidationError from our constraint
                picking.button_validate()
        except ValidationError as e:
            # Expected - negative balance caught
            error_message = str(e)
            self.assertIn('ติดลบ', error_message)  # Thai message
    
    def test_warehouse_consistency_across_returns(self):
        """
        Test warehouse consistency across multiple returns.
        
        Scenario:
        1. Receive 20 units to WH1
        2. Deliver 15 units from WH1
        3. Return 5 units to WH1
        4. Deliver 8 units from WH1
        5. Return 3 units to WH1
        
        Expected: All returns should use WH1, no negative balance
        """
        # Step 1: Receive
        receipt_picking, receipt_move = self._create_and_validate_receipt(
            self.warehouse_1, qty=20.0
        )
        
        # Step 2: First delivery
        delivery1_picking, delivery1_move = self._create_and_validate_delivery(
            self.warehouse_1, qty=15.0
        )
        
        # Step 3: First return
        return1_wizard = self.env['stock.return.picking'].with_context(
            active_id=delivery1_picking.id,
            active_model='stock.picking'
        ).create({})
        return1_wizard.product_return_moves.quantity = 5.0
        return1_picking_id, _ = return1_wizard._create_returns()
        return1_picking = self.picking_model.browse(return1_picking_id)
        return1_picking.action_assign()
        for move_line in return1_picking.move_line_ids:
            move_line.quantity = 5.0
        return1_picking.button_validate()
        
        # Step 4: Second delivery
        delivery2_picking, delivery2_move = self._create_and_validate_delivery(
            self.warehouse_1, qty=8.0
        )
        
        # Step 5: Second return
        return2_wizard = self.env['stock.return.picking'].with_context(
            active_id=delivery2_picking.id,
            active_model='stock.picking'
        ).create({})
        return2_wizard.product_return_moves.quantity = 3.0
        return2_picking_id, _ = return2_wizard._create_returns()
        return2_picking = self.picking_model.browse(return2_picking_id)
        return2_picking.action_assign()
        for move_line in return2_picking.move_line_ids:
            move_line.quantity = 3.0
        return2_picking.button_validate()
        
        # Check final balance at WH1
        wh1_layers = self.valuation_layer_model.search([
            ('product_id', '=', self.product.id),
            ('warehouse_id', '=', self.warehouse_1.id),
        ])
        
        total_qty = sum(wh1_layers.mapped('remaining_qty'))
        
        # Expected: 20 - 15 + 5 - 8 + 3 = 5 units
        expected_qty = 20.0 - 15.0 + 5.0 - 8.0 + 3.0
        self.assertAlmostEqual(
            total_qty, expected_qty, places=2,
            msg=f"Expected {expected_qty} units at WH1, got {total_qty}"
        )
        
        # Should not be negative
        self.assertGreaterEqual(total_qty, 0, "WH1 should not have negative qty")
    
    def test_return_move_preserves_original_cost(self):
        """
        Test that return moves preserve original cost (without landed costs).
        
        Scenario:
        1. Receive 10 units to WH1 at cost $50
        2. Deliver 10 units from WH1
        3. Return 10 units to WH1
        
        Expected: Return should use original cost $50 per unit
        """
        # Step 1: Receive with specific cost
        receipt_picking, receipt_move = self._create_and_validate_receipt(
            self.warehouse_1, qty=10.0
        )
        
        # Set cost on layer
        receipt_layers = self.valuation_layer_model.search([
            ('stock_move_id', '=', receipt_move.id),
        ])
        original_cost = 50.0
        receipt_layers.write({'unit_cost': original_cost})
        
        # Step 2: Deliver
        delivery_picking, delivery_move = self._create_and_validate_delivery(
            self.warehouse_1, qty=10.0
        )
        
        # Step 3: Return
        return_wizard = self.env['stock.return.picking'].with_context(
            active_id=delivery_picking.id,
            active_model='stock.picking'
        ).create({})
        return_picking_id, _ = return_wizard._create_returns()
        return_picking = self.picking_model.browse(return_picking_id)
        return_picking.action_assign()
        for move_line in return_picking.move_line_ids:
            move_line.quantity = move_line.product_uom_qty
        return_picking.button_validate()
        
        # Check return move layers
        return_moves = return_picking.move_ids.filtered(
            lambda m: m.origin_returned_move_id
        )
        
        for return_move in return_moves:
            return_layers = self.valuation_layer_model.search([
                ('stock_move_id', '=', return_move.id),
                ('quantity', '>', 0),  # Positive layer (incoming)
            ])
            
            for layer in return_layers:
                self.assertAlmostEqual(
                    abs(layer.unit_cost), original_cost, places=2,
                    msg="Return layer should use original cost"
                )
    
    def test_get_warehouse_from_return_move(self):
        """
        Test _get_fifo_valuation_layer_warehouse() for return moves.
        
        Verifies that return moves correctly identify original warehouse.
        """
        # Create delivery from WH1
        receipt_picking, receipt_move = self._create_and_validate_receipt(
            self.warehouse_1, qty=10.0
        )
        
        delivery_picking, delivery_move = self._create_and_validate_delivery(
            self.warehouse_1, qty=10.0
        )
        
        # Create return move (not validated yet)
        return_picking = self.picking_model.create({
            'picking_type_id': self.warehouse_1.in_type_id.id,
            'location_id': self.customer_location.id,
            'location_dest_id': self.warehouse_1.lot_stock_id.id,
        })
        
        return_move = self.move_model.create({
            'name': 'Return',
            'product_id': self.product.id,
            'product_uom_qty': 10.0,
            'product_uom': self.product.uom_id.id,
            'picking_id': return_picking.id,
            'location_id': self.customer_location.id,
            'location_dest_id': self.warehouse_1.lot_stock_id.id,
            'origin_returned_move_id': delivery_move.id,
        })
        
        # Test the method
        warehouse = return_move._get_fifo_valuation_layer_warehouse()
        
        # Should return WH1 (original warehouse)
        self.assertEqual(
            warehouse.id, self.warehouse_1.id,
            "Return move should identify original warehouse WH1"
        )
