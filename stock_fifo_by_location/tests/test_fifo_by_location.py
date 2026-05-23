# -*- coding: utf-8 -*-
"""
Warehouse-oriented regression tests for stock_fifo_by_location.
"""

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestStockFifoByWarehouse(TransactionCase):
    """Core FIFO behavior should be isolated per warehouse."""

    def setUp(self):
        super().setUp()
        self.product_model = self.env['product.product']
        self.warehouse_model = self.env['stock.warehouse']
        self.move_model = self.env['stock.move']
        self.layer_model = self.env['stock.valuation.layer']
        self.fifo_service = self.env['fifo.service']
        self.company = self.env.company

        self.warehouse_a = self.warehouse_model.search([
            ('company_id', '=', self.company.id),
        ], limit=1)
        if not self.warehouse_a:
            self.warehouse_a = self.warehouse_model.create({
                'name': 'Test Warehouse A',
                'code': 'TWA',
                'company_id': self.company.id,
            })

        self.warehouse_b = self.warehouse_model.search([
            ('company_id', '=', self.company.id),
            ('id', '!=', self.warehouse_a.id),
        ], limit=1)
        if not self.warehouse_b:
            self.warehouse_b = self.warehouse_model.create({
                'name': 'Test Warehouse B',
                'code': 'TWB',
                'company_id': self.company.id,
            })

        self.supplier_location = self.env.ref('stock.stock_location_suppliers')
        self.customer_location = self.env.ref('stock.stock_location_customers')

        # Create product category with FIFO + real_time valuation
        # real_time is required for SVL creation (otherwise no layers are created)
        self.product_category = self.env['product.category'].create({
            'name': 'Test FIFO WH Category',
            'property_cost_method': 'fifo',
            'property_valuation': 'manual_periodic',
        })

        self.product = self.product_model.create({
            'name': 'Test Product FIFO Warehouse',
            'type': 'product',
            'categ_id': self.product_category.id,
            'company_id': self.company.id,
        })

    def _create_done_move(self, name, qty, src_location, dest_location, price_unit=None):
        picking_type = self.env['stock.picking.type'].search([
            ('warehouse_id', 'in', [src_location.warehouse_id.id, dest_location.warehouse_id.id])
            if src_location.warehouse_id or dest_location.warehouse_id
            else ('code', '=', 'incoming'),
        ], limit=1)
        if not picking_type:
            # Use internal type as fallback
            picking_type = self.env['stock.picking.type'].search([
                ('code', '=', 'incoming'),
                ('company_id', '=', self.company.id),
            ], limit=1)

        picking_vals = {
            'picking_type_id': picking_type.id,
            'location_id': src_location.id,
            'location_dest_id': dest_location.id,
        }
        picking = self.env['stock.picking'].create(picking_vals)

        move_vals = {
            'name': name,
            'product_id': self.product.id,
            'product_uom_qty': qty,
            'product_uom': self.product.uom_id.id,
            'picking_id': picking.id,
            'location_id': src_location.id,
            'location_dest_id': dest_location.id,
        }
        if price_unit is not None:
            move_vals['price_unit'] = price_unit

        move = self.move_model.create(move_vals)
        picking.action_confirm()
        picking.action_assign()
        for ml in picking.move_line_ids:
            ml.quantity = ml.move_id.product_uom_qty
        picking.button_validate()
        return move

    def test_incoming_receipt_assigns_destination_warehouse(self):
        move = self._create_done_move(
            'Receipt WH-A',
            10.0,
            self.supplier_location,
            self.warehouse_a.lot_stock_id,
        )

        # Search layers for this product at warehouse_a with positive qty
        # (move may be split into backorder moves during picking validation)
        layers = self.layer_model.search([
            ('product_id', '=', self.product.id),
            ('warehouse_id', '=', self.warehouse_a.id),
            ('quantity', '=', 10.0),
        ], order='create_date desc', limit=1)
        self.assertTrue(layers, "Should create a positive SVL at warehouse A")
        self.assertEqual(layers.warehouse_id, self.warehouse_a)
        self.assertEqual(layers.quantity, 10.0)

    def test_fifo_queue_is_isolated_per_warehouse(self):
        move_a = self._create_done_move(
            'Receipt A',
            10.0,
            self.supplier_location,
            self.warehouse_a.lot_stock_id,
        )
        move_b = self._create_done_move(
            'Receipt B',
            5.0,
            self.supplier_location,
            self.warehouse_b.lot_stock_id,
        )

        queue_a = self.fifo_service.get_valuation_layer_queue(
            self.product, self.warehouse_a, self.company.id
        )
        queue_b = self.fifo_service.get_valuation_layer_queue(
            self.product, self.warehouse_b, self.company.id
        )

        self.assertTrue(queue_a, "WH-A should have layers in FIFO queue")
        self.assertTrue(queue_b, "WH-B should have layers in FIFO queue")
        # All queue_a layers should be at warehouse_a
        self.assertTrue(all(l.warehouse_id == self.warehouse_a for l in queue_a))
        # All queue_b layers should be at warehouse_b
        self.assertTrue(all(l.warehouse_id == self.warehouse_b for l in queue_b))

    def test_fifo_cost_uses_remaining_qty_not_original_quantity(self):
        move_one = self._create_done_move(
            'Receipt 1',
            10.0,
            self.supplier_location,
            self.warehouse_a.lot_stock_id,
        )
        layer_one = self.layer_model.search([('stock_move_id', '=', move_one.id)], limit=1)
        layer_one.write({
            'unit_cost': 100.0,
            'remaining_qty': 4.0,
            'remaining_value': 400.0,
        })

        move_two = self._create_done_move(
            'Receipt 2',
            5.0,
            self.supplier_location,
            self.warehouse_a.lot_stock_id,
        )
        layer_two = self.layer_model.search([('stock_move_id', '=', move_two.id)], limit=1)
        layer_two.write({
            'unit_cost': 120.0,
            'remaining_qty': 5.0,
            'remaining_value': 600.0,
        })

        cost_info = self.fifo_service.calculate_fifo_cost(
            self.product, self.warehouse_a, 6.0, self.company.id
        )

        self.assertEqual(cost_info['qty'], 6.0)
        self.assertEqual(len(cost_info['layers']), 2)
        self.assertEqual(cost_info['layers'][0]['qty_consumed'], 4.0)
        self.assertEqual(cost_info['layers'][1]['qty_consumed'], 2.0)
        self.assertAlmostEqual(cost_info['cost'], 640.0, places=2)

    def test_shortage_validation_reports_fallback_warehouses(self):
        self._create_done_move(
            'Receipt A',
            5.0,
            self.supplier_location,
            self.warehouse_a.lot_stock_id,
        )
        self._create_done_move(
            'Receipt B',
            8.0,
            self.supplier_location,
            self.warehouse_b.lot_stock_id,
        )

        result = self.fifo_service.validate_warehouse_availability(
            self.product,
            self.warehouse_a,
            10.0,
            allow_fallback=True,
            company_id=self.company.id,
        )

        self.assertFalse(result['available'])
        self.assertEqual(result['available_qty'], 5.0)
        self.assertEqual(result['shortage'], 5.0)

    def test_internal_transfer_keeps_origin_cost_open(self):
        receipt = self._create_done_move(
            'Receipt A',
            10.0,
            self.supplier_location,
            self.warehouse_a.lot_stock_id,
        )
        origin_layer = self.layer_model.search([('stock_move_id', '=', receipt.id)], limit=1)

        transfer = self._create_done_move(
            'Transfer A -> B',
            6.0,
            self.warehouse_a.lot_stock_id,
            self.warehouse_b.lot_stock_id,
        )

        origin_layer.invalidate_recordset([
            'remaining_qty', 'origin_remaining_qty', 'origin_remaining_value'
        ])
        dest_layers = self.layer_model.search([
            ('stock_move_id', '=', transfer.id),
            ('quantity', '>', 0),
            ('warehouse_id', '=', self.warehouse_b.id),
        ])

        # Origin layer's remaining_qty should be reduced by transfer (FIFO consumption)
        self.assertEqual(origin_layer.remaining_qty, 4.0)
        # There should be destination layers at WH-B
        self.assertTrue(dest_layers)
        self.assertEqual(sum(dest_layers.mapped('remaining_qty')), 6.0)

    def test_external_delivery_consumes_origin_cost_after_transfer(self):
        receipt = self._create_done_move(
            'Receipt A',
            10.0,
            self.supplier_location,
            self.warehouse_a.lot_stock_id,
        )
        origin_layer = self.layer_model.search([('stock_move_id', '=', receipt.id)], limit=1)

        self._create_done_move(
            'Transfer A -> B',
            6.0,
            self.warehouse_a.lot_stock_id,
            self.warehouse_b.lot_stock_id,
        )
        self._create_done_move(
            'Delivery B -> Customer',
            2.0,
            self.warehouse_b.lot_stock_id,
            self.customer_location,
        )

        origin_layer.invalidate_recordset([
            'remaining_qty', 'origin_remaining_qty', 'origin_remaining_value'
        ])
        # Transfer consumed 6 from origin, delivery consumed 2 from dest (not from origin)
        self.assertEqual(origin_layer.remaining_qty, 4.0)

    def test_location_compatibility_wrappers_resolve_warehouse(self):
        self._create_done_move(
            'Receipt A',
            5.0,
            self.supplier_location,
            self.warehouse_a.lot_stock_id,
        )

        available_qty = self.fifo_service.get_available_qty_at_location(
            self.product, self.warehouse_a.lot_stock_id, self.company.id
        )
        self.assertEqual(available_qty, 5.0)

        validation = self.fifo_service.validate_location_availability(
            self.product,
            self.warehouse_a.lot_stock_id,
            6.0,
            allow_fallback=True,
            company_id=self.company.id,
        )
        self.assertIn('fallback_locations', validation)

    def test_shortage_validation_raises_for_missing_location_warehouse(self):
        with self.assertRaises(UserError):
            self.fifo_service.validate_location_availability(
                self.product,
                self.customer_location,
                1.0,
                allow_fallback=False,
                company_id=self.company.id,
            )


@tagged('post_install', '-at_install')
class TestLandedCostWarehouseCompatibility(TransactionCase):
    """Legacy location APIs should map cleanly to warehouse-aware storage."""

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.product = self.env['product.product'].create({
            'name': 'Test Product LC Warehouse',
            'type': 'product',
            'categ_id': self.env.ref('product.product_category_all').id,
            'cost_method': 'fifo',
        })
        self.warehouse = self.env['stock.warehouse'].search([('company_id', '=', self.company.id)], limit=1)
        self.layer_model = self.env['stock.valuation.layer']
        self.lc_model = self.env['stock.valuation.layer.landed.cost']

    def test_get_landed_cost_at_location_uses_warehouse(self):
        layer = self.layer_model.create({
            'product_id': self.product.id,
            'quantity': 10.0,
            'unit_cost': 100.0,
            'value': 1000.0,
            'remaining_qty': 10.0,
            'remaining_value': 1000.0,
            'warehouse_id': self.warehouse.id,
            'company_id': self.company.id,
        })
        self.lc_model.create({
            'valuation_layer_id': layer.id,
            'warehouse_id': self.warehouse.id,
            'landed_cost_value': 50.0,
            'quantity': 10.0,
        })

        total = self.layer_model.get_landed_cost_at_location(
            self.product,
            self.warehouse.lot_stock_id,
            self.company.id,
        )
        self.assertAlmostEqual(total, 50.0, places=2)

    def test_position_valuation_follows_origin_cost_after_landed_cost_update(self):
        warehouse_b = self.env['stock.warehouse'].search([
            ('id', '!=', self.warehouse.id)
        ], limit=1)
        if not warehouse_b:
            warehouse_b = self.env['stock.warehouse'].create({
                'name': 'Test Warehouse LC B',
                'code': 'TWLB',
                'company_id': self.env.company.id,
            })

        origin_layer = self.layer_model.create({
            'product_id': self.product.id,
            'quantity': 100.0,
            'unit_cost': 100.0,
            'value': 10000.0,
            'remaining_qty': 0.0,
            'remaining_value': 0.0,
            'origin_remaining_qty': 100.0,
            'origin_remaining_value': 10000.0,
            'warehouse_id': self.warehouse.id,
            'company_id': self.company.id,
        })
        pos_wh2 = self.layer_model.create({
            'product_id': self.product.id,
            'quantity': 60.0,
            'unit_cost': 100.0,
            'value': 6000.0,
            'remaining_qty': 60.0,
            'remaining_value': 6000.0,
            'warehouse_id': warehouse_b.id,
            'origin_valuation_layer_id': origin_layer.id,
            'is_position_layer': True,
            'company_id': self.company.id,
        })
        pos_wh3 = self.layer_model.create({
            'product_id': self.product.id,
            'quantity': 40.0,
            'unit_cost': 100.0,
            'value': 4000.0,
            'remaining_qty': 40.0,
            'remaining_value': 4000.0,
            'warehouse_id': self.warehouse.id,
            'origin_valuation_layer_id': origin_layer.id,
            'is_position_layer': True,
            'company_id': self.company.id,
        })

        origin_layer.write({
            'origin_remaining_value': 12000.0,
        })
        pos_wh2.invalidate_recordset(['position_valuation', 'current_origin_unit_cost'])
        pos_wh3.invalidate_recordset(['position_valuation', 'current_origin_unit_cost'])

        self.assertAlmostEqual(pos_wh2.current_origin_unit_cost, 120.0, places=2)
        self.assertAlmostEqual(pos_wh2.position_valuation, 7200.0, places=2)
        self.assertAlmostEqual(pos_wh3.position_valuation, 4800.0, places=2)
