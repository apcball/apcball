# -*- coding: utf-8 -*-
"""
Test Cases for Warehouse-Aware Inventory Adjustments (v17.0.1.1.7)

Tests the inventory adjustment functionality with warehouse-specific cost rules.
"""

from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


class TestInventoryAdjustmentWarehouse(TransactionCase):
    """
    Test cases for warehouse-aware inventory adjustment functionality.
    
    Covers:
    - Stock increases with different cost rules
    - Stock decreases using warehouse FIFO
    - Valuation layer creation with correct warehouse_id
    """
    
    def setUp(self):
        super().setUp()
        
        # Models
        self.product_model = self.env['product.product']
        self.warehouse_model = self.env['stock.warehouse']
        self.location_model = self.env['stock.location']
        self.quant_model = self.env['stock.quant']
        self.layer_model = self.env['stock.valuation.layer']
        self.move_model = self.env['stock.move']
        
        # Create product category with FIFO costing
        self.product_category = self.env['product.category'].create({
            'name': 'Test FIFO Adjustment Category',
            'property_cost_method': 'fifo',
            'property_valuation': 'real_time',
        })
        
        # Create storable product with FIFO
        self.product = self.product_model.create({
            'name': 'Test Product Inventory Adjustment',
            'type': 'product',
            'categ_id': self.product_category.id,
            'standard_price': 100.0,
        })
        
        # Get/Create warehouses
        self.warehouse_a = self.warehouse_model.search([('name', '=', 'WH1')], limit=1)
        if not self.warehouse_a:
            self.warehouse_a = self.warehouse_model.create({
                'name': 'WH1',
                'code': 'WH1',
            })
        
        # Get inventory adjustment location
        self.inventory_location = self.env.ref('stock.location_inventory')
    
    def _create_inventory_adjustment_increase(self, warehouse, qty, cost_rule='standard', manual_cost=0.0):
        """Helper to create and apply inventory adjustment (increase)."""
        # Create quant for adjustment
        quant = self.quant_model.create({
            'product_id': self.product.id,
            'location_id': warehouse.lot_stock_id.id,
            'inventory_quantity': qty,
            'inventory_cost_rule': cost_rule,
            'inventory_manual_cost': manual_cost,
        })
        
        # Apply inventory adjustment
        quant.action_apply_inventory()
        
        return quant
    
    def _create_inventory_adjustment_decrease(self, warehouse, existing_qty, new_qty):
        """Helper to create and apply inventory adjustment (decrease)."""
        # Find existing quant
        quant = self.quant_model.search([
            ('product_id', '=', self.product.id),
            ('location_id', '=', warehouse.lot_stock_id.id),
        ], limit=1)
        
        if not quant:
            # Create quant with existing quantity first
            quant = self.quant_model.create({
                'product_id': self.product.id,
                'location_id': warehouse.lot_stock_id.id,
                'quantity': existing_qty,
            })
        
        # Set inventory quantity lower to trigger decrease
        quant.inventory_quantity = new_qty
        quant.action_apply_inventory()
        
        return quant
    
    def test_inventory_adjustment_increase_standard_price(self):
        """
        Test inventory increase using standard price cost rule.
        
        Scenario:
        1. Product has standard price 100
        2. Adjust inventory +10 units using standard price
        
        Expected:
        - Positive SVL created with cost 100/unit at WH-A
        - Total value = 1000
        """
        # Step 1: Adjust inventory +10 units with standard price
        quant = self._create_inventory_adjustment_increase(
            self.warehouse_a, qty=10, cost_rule='standard'
        )
        
        # Verify SVL created
        layers = self.layer_model.search([
            ('product_id', '=', self.product.id),
            ('warehouse_id', '=', self.warehouse_a.id),
            ('quantity', '>', 0),
        ])
        
        self.assertTrue(layers, "Inventory adjustment should create positive layer")
        self.assertEqual(len(layers), 1, "Should create exactly one layer")
        
        layer = layers[0]
        self.assertEqual(layer.quantity, 10, "Layer quantity should be 10")
        self.assertEqual(layer.unit_cost, 100.0, "Layer unit cost should be standard price 100")
        self.assertEqual(layer.value, 1000.0, "Layer value should be 1000")
        self.assertEqual(layer.warehouse_id.id, self.warehouse_a.id, "Layer should be at WH-A")
    
    def test_inventory_adjustment_increase_manual_cost(self):
        """
        Test inventory increase using manual cost.
        
        Scenario:
        1. Product has standard price 100
        2. Adjust inventory +10 units using manual cost 150
        
        Expected:
        - Positive SVL created with cost 150/unit at WH-A
        - Total value = 1500
        """
        # Step 1: Adjust inventory +10 units with manual cost 150
        quant = self._create_inventory_adjustment_increase(
            self.warehouse_a, qty=10, cost_rule='manual', manual_cost=150.0
        )
        
        # Verify SVL created
        layers = self.layer_model.search([
            ('product_id', '=', self.product.id),
            ('warehouse_id', '=', self.warehouse_a.id),
            ('quantity', '>', 0),
        ])
        
        self.assertTrue(layers, "Inventory adjustment should create positive layer")
        layer = layers[0]
        
        self.assertEqual(layer.quantity, 10, "Layer quantity should be 10")
        self.assertAlmostEqual(layer.unit_cost, 150.0, places=2, 
                              msg="Layer unit cost should be manual cost 150")
        self.assertAlmostEqual(layer.value, 1500.0, places=2, 
                              msg="Layer value should be 1500")
        self.assertEqual(layer.warehouse_id.id, self.warehouse_a.id, "Layer should be at WH-A")
    
    def test_inventory_adjustment_increase_last_purchase_price(self):
        """
        Test inventory increase using last purchase price from warehouse.
        
        Scenario:
        1. Receive 5 units to WH-A at cost 120/unit (purchase)
        2. Adjust inventory +10 units using last purchase price
        
        Expected:
        - Positive SVL created with cost 120/unit (last purchase at WH-A)
        - Total value = 1200
        """
        # Step 1: Create receipt to establish last purchase price
        supplier_location = self.env.ref('stock.stock_location_suppliers')
        
        # Create and validate receipt move
        receipt_move = self.move_model.create({
            'name': 'Test Receipt',
            'product_id': self.product.id,
            'product_uom_qty': 5.0,
            'product_uom': self.product.uom_id.id,
            'location_id': supplier_location.id,
            'location_dest_id': self.warehouse_a.lot_stock_id.id,
            'price_unit': 120.0,
        })
        receipt_move._action_confirm()
        receipt_move._action_assign()
        receipt_move._action_done()
        
        # Step 2: Adjust inventory +10 units with last purchase price
        quant = self._create_inventory_adjustment_increase(
            self.warehouse_a, qty=10, cost_rule='last_purchase'
        )
        
        # Verify SVL created with last purchase price
        adjustment_layers = self.layer_model.search([
            ('product_id', '=', self.product.id),
            ('warehouse_id', '=', self.warehouse_a.id),
            ('stock_move_id.location_id', '=', self.inventory_location.id),
            ('quantity', '>', 0),
        ])
        
        self.assertTrue(adjustment_layers, "Inventory adjustment should create layer")
        layer = adjustment_layers[0]
        
        self.assertEqual(layer.quantity, 10, "Layer quantity should be 10")
        self.assertAlmostEqual(layer.unit_cost, 120.0, places=2,
                              msg="Layer unit cost should be last purchase price 120")
        self.assertAlmostEqual(layer.value, 1200.0, places=2,
                              msg="Layer value should be 1200")
    
    def test_inventory_adjustment_decrease_uses_fifo(self):
        """
        Test inventory decrease consumes from warehouse FIFO.
        
        Scenario:
        1. Adjust inventory +10 units at cost 100/unit to WH-A
        2. Adjust inventory +10 units at cost 150/unit to WH-A
        3. Decrease inventory by 5 units
        
        Expected:
        - Negative SVL created consuming from first layer (FIFO)
        - Cost should be 100/unit (not 150 or average)
        - Value = -500
        """
        # Step 1: First adjustment +10 at 100/unit
        quant1 = self._create_inventory_adjustment_increase(
            self.warehouse_a, qty=10, cost_rule='manual', manual_cost=100.0
        )
        
        # Step 2: Second adjustment +10 at 150/unit
        # Update existing quant
        quant = self.quant_model.search([
            ('product_id', '=', self.product.id),
            ('location_id', '=', self.warehouse_a.lot_stock_id.id),
        ], limit=1)
        
        quant.inventory_quantity = 20  # 10 existing + 10 more
        quant.inventory_cost_rule = 'manual'
        quant.inventory_manual_cost = 150.0
        quant.action_apply_inventory()
        
        # Step 3: Decrease inventory by 5 units (20 -> 15)
        quant.inventory_quantity = 15
        quant.action_apply_inventory()
        
        # Verify negative SVL created with FIFO cost
        negative_layers = self.layer_model.search([
            ('product_id', '=', self.product.id),
            ('warehouse_id', '=', self.warehouse_a.id),
            ('quantity', '<', 0),
        ], order='create_date desc', limit=1)
        
        self.assertTrue(negative_layers, "Inventory decrease should create negative layer")
        layer = negative_layers[0]
        
        self.assertEqual(layer.quantity, -5, "Layer quantity should be -5")
        # Should use FIFO cost from first layer (100, not 150)
        self.assertAlmostEqual(abs(layer.unit_cost), 100.0, places=2,
                              msg="Layer should use FIFO cost 100 from first layer")
        self.assertAlmostEqual(layer.value, -500.0, places=2,
                              msg="Layer value should be -500")
    
    def test_inventory_adjustment_warehouse_isolation(self):
        """
        Test that inventory adjustments respect warehouse boundaries.
        
        Scenario:
        1. Adjust inventory +10 units to WH-A at cost 100/unit
        2. Create WH-B
        3. Adjust inventory +10 units to WH-B at cost 150/unit
        4. Decrease 5 units from WH-A
        
        Expected:
        - WH-A decrease uses cost 100 (from WH-A FIFO)
        - WH-B is not affected
        - Layers have correct warehouse_id
        """
        # Create second warehouse
        warehouse_b = self.warehouse_model.create({
            'name': 'WH-Test-B',
            'code': 'WHTB',
        })
        
        # Step 1: Adjust +10 to WH-A at 100/unit
        quant_a = self._create_inventory_adjustment_increase(
            self.warehouse_a, qty=10, cost_rule='manual', manual_cost=100.0
        )
        
        # Step 2: Adjust +10 to WH-B at 150/unit
        quant_b = self._create_inventory_adjustment_increase(
            warehouse_b, qty=10, cost_rule='manual', manual_cost=150.0
        )
        
        # Step 3: Decrease 5 units from WH-A
        quant_a_updated = self.quant_model.search([
            ('product_id', '=', self.product.id),
            ('location_id', '=', self.warehouse_a.lot_stock_id.id),
        ], limit=1)
        quant_a_updated.inventory_quantity = 5
        quant_a_updated.action_apply_inventory()
        
        # Verify WH-A negative layer uses cost 100
        negative_layers_a = self.layer_model.search([
            ('product_id', '=', self.product.id),
            ('warehouse_id', '=', self.warehouse_a.id),
            ('quantity', '<', 0),
        ])
        
        self.assertTrue(negative_layers_a, "WH-A should have negative layer")
        self.assertAlmostEqual(abs(negative_layers_a[0].unit_cost), 100.0, places=2,
                              msg="WH-A should use its own FIFO cost 100")
        
        # Verify WH-B still has 10 units
        layers_b = self.layer_model.search([
            ('product_id', '=', self.product.id),
            ('warehouse_id', '=', warehouse_b.id),
        ])
        
        positive_b = layers_b.filtered(lambda l: l.quantity > 0)
        self.assertEqual(len(positive_b), 1, "WH-B should have one positive layer")
        self.assertEqual(positive_b[0].remaining_qty, 10.0, "WH-B should still have 10 units")
    
    def test_manual_cost_required_validation(self):
        """
        Test that manual cost is required when cost rule is 'manual'.
        
        Expected:
        - Error raised if manual cost is 0 or negative when rule is 'manual'
        """
        # Try to adjust with manual cost rule but no manual cost
        quant = self.quant_model.create({
            'product_id': self.product.id,
            'location_id': self.warehouse_a.lot_stock_id.id,
            'inventory_quantity': 10,
            'inventory_cost_rule': 'manual',
            'inventory_manual_cost': 0.0,  # Invalid!
        })
        
        # Should raise error when applying
        with self.assertRaises(UserError) as ctx:
            quant.action_apply_inventory()
        
        self.assertIn('Manual cost', str(ctx.exception))
        self.assertIn('greater than zero', str(ctx.exception))
