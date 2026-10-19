# -*- coding: utf-8 -*-
"""
A transfer that consumes several origin layers must create one position layer per
origin, so landed cost on each receipt sees its own remaining stock.

Bug: the destination position layer took a single origin (the "latest consumed layer
at source", limit=1) for the whole transferred qty. The other receipts lost their
share of the transfer (landed cost under-booked) and the chosen origin was credited
with stock it never had (landed cost over-booked).
"""

import json

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

    def test_transfer_is_value_neutral_and_layers_carry_consumed_cost(self):
        """in == out for the transfer, and each destination layer carries the FIFO cost
        actually taken from its origin, not the standard / location-history price that
        stock_by_locations books the standard position layer with."""
        product = self._new_product('Origin Split Cost')
        r1 = self._receipt(10.0, 10.0, product)
        r2 = self._receipt(10.0, 30.0, product)
        self._receipt(20.0, 50.0, product)  # stays in stock
        # make the FIFO cost of each receipt explicit: r1 @10, r2 @30
        for receipt, unit in ((r1, 10.0), (r2, 30.0)):
            layer = self._base_layer(receipt)
            layer.write({'value': 10.0 * unit, 'remaining_value': 10.0 * unit})
        product.standard_price = 7.0  # price the standard in-layer would be booked at
        picking = self._transfer(15.0, product)  # FIFO: 10 @10 from r1 + 5 @30 from r2

        out_layers = self.layer_model.search([
            ('stock_move_id', 'in', picking.move_ids.ids), ('quantity', '<', 0)])
        consumed = {}  # origin layer id -> cost taken from it, as recorded on the out layer
        for item in json.loads(out_layers.consumed_origin_splits):
            consumed[item[0]] = item[2]
        self.assertEqual(
            set(consumed), {self._base_layer(r1).id, self._base_layer(r2).id})
        pos = self.layer_model.search([
            ('product_id', '=', product.id), ('warehouse_id', '=', self.wh2.id),
            ('quantity', '>', 0)])
        self.assertEqual(len(pos), 2)
        # value-neutral, and the cost ratio between origins is the consumed one
        self.assertAlmostEqual(self._transfer_net_value(picking), 0.0, places=2)
        pos_total = sum(pos.mapped('value'))
        consumed_total = sum(consumed.values())
        for layer in pos:
            self.assertAlmostEqual(
                layer.value / pos_total,
                consumed[layer.origin_valuation_layer_id.id] / consumed_total, places=4)
            self.assertAlmostEqual(layer.remaining_value, layer.value, places=2)

    def test_allocate_split_values(self):
        move = self.env['stock.move']
        rounding = self.product.uom_id.rounding
        origin = self.layer_model  # only the tuple shape matters
        # known costs: used as is, remainder takes what is left of the out value
        values, rest = move._allocate_split_values(
            [(origin, 10.0, 100.0), (origin, 5.0, 150.0)], 2.0, 17.0, 300.0, 999.0, rounding)
        self.assertEqual(values, [100.0, 150.0])
        self.assertAlmostEqual(rest, 50.0)
        # known costs, no remainder, out differs: scaled to keep the ratio, in == out
        values, rest = move._allocate_split_values(
            [(origin, 10.0, 100.0), (origin, 5.0, 150.0)], 0.0, 15.0, 500.0, 999.0, rounding)
        self.assertAlmostEqual(sum(values), 500.0)
        self.assertAlmostEqual(values[0] / values[1], 100.0 / 150.0)
        self.assertEqual(rest, 0.0)
        # unknown cost for one origin: fall back to spreading the fallback total by qty
        values, rest = move._allocate_split_values(
            [(origin, 10.0, None), (origin, 5.0, 150.0)], 0.0, 15.0, 250.0, 150.0, rounding)
        self.assertAlmostEqual(values[0], 100.0)
        self.assertAlmostEqual(values[1], 50.0)
        self.assertEqual(rest, 0.0)
