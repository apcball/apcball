# -*- coding: utf-8 -*-
"""
Inter-warehouse return: the returned stock must keep its real cost origin.

Bug (prod, RM-NI <-> RM01, Nov 2026): the position layer created by a return took the
original transfer's NEGATIVE out layer as its origin_valuation_layer_id (an out layer
keeps its origin only in consumed_origin_splits). A negative layer has origin_remaining_qty
0 and value 0, so the next transfer/sale of that stock was costed at 0 on the out leg while
the in leg carried the full value (one-sided legs, value created or lost).

Sequence: receipt -> transfer WH1 -> WH2 -> return (WH2 -> WH1) -> transfer WH1 -> WH2 again.
"""

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestReturnOriginNotNegativeLayer(TransactionCase):

    def setUp(self):
        super().setUp()
        self.layer_model = self.env['stock.valuation.layer']
        company = self.env.company
        categ = self.env['product.category'].create({
            'name': 'Return Origin',
            'property_cost_method': 'fifo',
            'property_valuation': 'manual_periodic',
        })
        self.product = self.env['product.product'].create({
            'name': 'Return Origin Product', 'type': 'product',
            'categ_id': categ.id, 'standard_price': 10.0,
        })
        self.wh1 = self.env['stock.warehouse'].search(
            [('company_id', '=', company.id)], limit=1)
        self.wh2 = self.env['stock.warehouse'].search(
            [('company_id', '=', company.id), ('id', '!=', self.wh1.id)], limit=1)
        if not self.wh2:
            self.wh2 = self.env['stock.warehouse'].create(
                {'name': 'Return WH2', 'code': 'RTW2', 'company_id': company.id})
        self.supplier = self.env.ref('stock.stock_location_suppliers')

    def _validate(self, picking):
        picking.action_confirm()
        picking.action_assign()
        for ml in picking.move_line_ids:
            ml.quantity = ml.move_id.product_uom_qty
        picking.button_validate()

    def _receipt(self, qty, price):
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.wh1.in_type_id.id,
            'location_id': self.supplier.id,
            'location_dest_id': self.wh1.lot_stock_id.id,
        })
        self.env['stock.move'].create({
            'name': 'receipt', 'product_id': self.product.id,
            'product_uom_qty': qty, 'product_uom': self.product.uom_id.id,
            'picking_id': picking.id, 'location_id': self.supplier.id,
            'location_dest_id': self.wh1.lot_stock_id.id, 'price_unit': price,
        })
        self._validate(picking)
        return picking

    def _transfer(self, qty, src, dest):
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.wh1.int_type_id.id,
            'location_id': src.id, 'location_dest_id': dest.id,
        })
        self.env['stock.move'].create({
            'name': 'transfer', 'product_id': self.product.id,
            'product_uom_qty': qty, 'product_uom': self.product.uom_id.id,
            'picking_id': picking.id, 'location_id': src.id, 'location_dest_id': dest.id,
        })
        self._validate(picking)
        return picking

    def _return(self, picking):
        wizard = self.env['stock.return.picking'].with_context(
            active_id=picking.id, active_model='stock.picking').create({})
        res = wizard.create_returns()
        ret = self.env['stock.picking'].browse(res['res_id'])
        self._validate(ret)
        return ret

    def _legs(self, picking):
        layers = self.layer_model.search([('stock_move_id', 'in', picking.move_ids.ids)])
        pos = layers.filtered(lambda l: l.quantity > 0)
        neg = layers.filtered(lambda l: l.quantity < 0)
        return pos, neg

    def test_return_in_leg_keeps_real_origin_and_value(self):
        receipt = self._receipt(10.0, 100.0)
        base = self.layer_model.search([
            ('stock_move_id', '=', receipt.move_ids.id), ('quantity', '>', 0)], limit=1)
        out = self._transfer(10.0, self.wh1.lot_stock_id, self.wh2.lot_stock_id)
        ret = self._return(out)

        pos, neg = self._legs(ret)
        self.assertTrue(pos and neg)
        for layer in pos:
            self.assertGreaterEqual(
                layer.origin_valuation_layer_id.quantity, 0,
                'a return position layer must not take a negative out layer as its origin')
        self.assertEqual(pos.mapped('origin_valuation_layer_id'), base,
                         'the returned stock goes back to its receipt as cost origin')
        self.assertAlmostEqual(sum(pos.mapped('value')), base.value, places=2)
        self.assertAlmostEqual(-sum(neg.mapped('value')), base.value, places=2)

    def test_transfer_after_return_has_equal_legs(self):
        receipt = self._receipt(10.0, 100.0)
        base = self.layer_model.search([
            ('stock_move_id', '=', receipt.move_ids.id), ('quantity', '>', 0)], limit=1)
        self.assertTrue(base.value > 0)
        out = self._transfer(10.0, self.wh1.lot_stock_id, self.wh2.lot_stock_id)
        self._return(out)
        again = self._transfer(10.0, self.wh1.lot_stock_id, self.wh2.lot_stock_id)

        pos, neg = self._legs(again)
        self.assertAlmostEqual(-sum(neg.mapped('value')), base.value, places=2,
                               msg='out leg must not be costed at 0')
        self.assertAlmostEqual(sum(pos.mapped('value')), base.value, places=2)

