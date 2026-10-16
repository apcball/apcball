# -*- coding: utf-8 -*-
"""
A transfer that consumes several origin layers must create one position layer per
origin, so landed cost on each receipt sees its own remaining stock.

Bug: the destination position layer took a single origin (the "latest consumed layer
at source", limit=1) for the whole transferred qty. The other receipts lost their
share of the transfer (landed cost under-booked) and the chosen origin was credited
with stock it never had (landed cost over-booked).
"""

from unittest import mock

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestTransferOriginSplit(TransactionCase):

    def setUp(self):
        super().setUp()
        self.layer_model = self.env['stock.valuation.layer']
        company = self.env.company
        categ = self.env['product.category'].create({
            'name': 'Origin Split',
            'property_cost_method': 'fifo',
            'property_valuation': 'manual_periodic',
        })
        self.product = self.env['product.product'].create({
            'name': 'Origin Split Product', 'type': 'product',
            'categ_id': categ.id, 'standard_price': 10.0,
        })
        self.cost_product = self.env['product.product'].create({
            'name': 'Origin Split Freight', 'type': 'service',
            'landed_cost_ok': True, 'split_method_landed_cost': 'equal',
        })
        self.wh1 = self.env['stock.warehouse'].search(
            [('company_id', '=', company.id)], limit=1)
        self.wh2 = self.env['stock.warehouse'].search(
            [('company_id', '=', company.id), ('id', '!=', self.wh1.id)], limit=1)
        if not self.wh2:
            self.wh2 = self.env['stock.warehouse'].create(
                {'name': 'Split WH2', 'code': 'SPW2', 'company_id': company.id})
        self.supplier = self.env.ref('stock.stock_location_suppliers')

    def _validate(self, picking):
        picking.action_confirm()
        picking.action_assign()
        for ml in picking.move_line_ids:
            ml.quantity = ml.move_id.product_uom_qty
        picking.button_validate()

    def _receipt(self, qty, price=10.0, product=None):
        product = product or self.product
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.wh1.in_type_id.id,
            'location_id': self.supplier.id,
            'location_dest_id': self.wh1.lot_stock_id.id,
        })
        self.env['stock.move'].create({
            'name': 'receipt', 'product_id': product.id,
            'product_uom_qty': qty, 'product_uom': product.uom_id.id,
            'picking_id': picking.id, 'location_id': self.supplier.id,
            'location_dest_id': self.wh1.lot_stock_id.id, 'price_unit': price,
        })
        self._validate(picking)
        return picking

    def _transfer(self, qty, product=None):
        product = product or self.product
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.wh1.int_type_id.id,
            'location_id': self.wh1.lot_stock_id.id,
            'location_dest_id': self.wh2.lot_stock_id.id,
        })
        self.env['stock.move'].create({
            'name': 'transfer', 'product_id': product.id,
            'product_uom_qty': qty, 'product_uom': product.uom_id.id,
            'picking_id': picking.id, 'location_id': self.wh1.lot_stock_id.id,
            'location_dest_id': self.wh2.lot_stock_id.id,
        })
        self._validate(picking)
        return picking

    def _base_layer(self, receipt):
        return self.layer_model.search([
            ('stock_move_id', '=', receipt.move_ids.id),
            ('quantity', '>', 0), ('stock_landed_cost_id', '=', False),
        ], limit=1)

    def _lc_booked(self, receipt, amount=100.0):
        lc = self.env['stock.landed.cost'].create({
            'picking_ids': [(4, receipt.id)],
            'cost_lines': [(0, 0, {
                'product_id': self.cost_product.id, 'name': 'freight',
                'price_unit': amount, 'split_method': 'equal',
            })],
        })
        lc.compute_landed_cost()
        lc.button_validate()
        layers = self.layer_model.search([
            ('stock_move_id', '=', receipt.move_ids.id),
            ('stock_landed_cost_id', '=', lc.id),
        ])
        return sum(layers.mapped('value'))

    def test_transfer_over_two_receipts_splits_position_layers(self):
        r1 = self._receipt(10.0)
        r2 = self._receipt(10.0)
        self._transfer(15.0)  # FIFO: 10 from r1 + 5 from r2

        pos = self.layer_model.search([
            ('product_id', '=', self.product.id),
            ('warehouse_id', '=', self.wh2.id),
            ('quantity', '>', 0),
        ])
        by_origin = {}
        for lay in pos:
            origin = lay.origin_valuation_layer_id
            by_origin[origin.id] = by_origin.get(origin.id, 0.0) + lay.quantity
        self.assertEqual(by_origin, {
            self._base_layer(r1).id: 10.0,
            self._base_layer(r2).id: 5.0,
        })
        # value preserved
        self.assertAlmostEqual(sum(pos.mapped('value')), 15 * 10.0, places=2)

    def test_landed_cost_on_second_receipt_sees_transferred_stock(self):
        r1 = self._receipt(10.0)
        r2 = self._receipt(10.0)
        self._transfer(15.0)
        # all 10 units of r2 are still in stock (5 at WH1, 5 at WH2) -> full 100
        self.assertAlmostEqual(self._lc_booked(r2), 100.0, places=2)
        # all 10 units of r1 are still in stock (all moved to WH2) -> full 100
        self.assertAlmostEqual(self._lc_booked(r1), 100.0, places=2)

    def _new_product(self, name):
        return self.env['product.product'].create({
            'name': name, 'type': 'product',
            'categ_id': self.product.categ_id.id, 'standard_price': 100.0,
        })

    def _dest_value(self, product):
        pos = self.layer_model.search([
            ('product_id', '=', product.id),
            ('warehouse_id', '=', self.wh2.id),
            ('quantity', '>', 0),
        ])
        return sum(pos.mapped('value')), sum(pos.mapped('remaining_value'))

    def _transfer_net_value(self, picking):
        layers = self.layer_model.search([('stock_move_id', 'in', picking.move_ids.ids)])
        return sum(layers.mapped('value'))

    def test_split_does_not_change_the_transfer_net_value(self):
        """Splitting by origin must only re-attribute the destination layer: the value
        the transfer was booked with (in minus out) stays what the unsplit flow gives,
        even when a FIFO estimate taken after the queue was consumed is different."""
        layer_cls = type(self.layer_model)
        # A: split disabled -> legacy flow, the reference net value of the transfer.
        prod_a = self._new_product('Origin Split Value A')
        self._receipt(10.0, 10.0, prod_a)
        self._receipt(10.0, 30.0, prod_a)
        self._receipt(20.0, 50.0, prod_a)  # stays in stock: skews a post-transfer estimate
        with mock.patch.object(layer_cls, '_get_consumed_origin_splits', lambda recs: []):
            picking_a = self._transfer(15.0, prod_a)
        net_a = self._transfer_net_value(picking_a)

        # B: same scenario, split enabled. Production-like: the FIFO estimate taken after
        # the queue was consumed is not the value the position layer was booked with.
        prod_b = self._new_product('Origin Split Value B')
        self._receipt(10.0, 10.0, prod_b)
        self._receipt(10.0, 30.0, prod_b)
        self._receipt(20.0, 50.0, prod_b)
        fifo_cls = type(self.env['fifo.service'])
        estimate = {'unit_cost': 650.0 / 15.0, 'cost': 650.0, 'layers': []}
        with mock.patch.object(
            fifo_cls, 'calculate_fifo_cost_with_landed_cost',
            lambda *args, **kwargs: dict(estimate),
        ):
            picking_b = self._transfer(15.0, prod_b)
        net_b = self._transfer_net_value(picking_b)

        pos_b = self.layer_model.search([
            ('product_id', '=', prod_b.id), ('warehouse_id', '=', self.wh2.id),
            ('quantity', '>', 0)])
        self.assertEqual(len(pos_b), 2, "transfer spans two receipts -> two layers")
        self.assertAlmostEqual(net_b, net_a, places=2)
        # value follows quantity (10 : 5)
        by_qty = sorted(pos_b, key=lambda l: -l.quantity)
        self.assertAlmostEqual(by_qty[0].value / 10.0, by_qty[1].value / 5.0, places=2)
