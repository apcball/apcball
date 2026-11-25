# -*- coding: utf-8 -*-
"""
A vendor bill whose price differs from the receipt books a value-only layer (quantity 0,
linked to the corrected layer, no landed cost) that purchase_stock adds to that layer's
remaining_value. origin_remaining_value (used by calculate_fifo_cost to price the next
issue) must carry the same amount.

The layer is created directly (as purchase_stock's _prepare_pdiff_svl_vals does) so the
test does not depend on purchase / budget configuration.
"""

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestPriceDifferenceOriginValue(TransactionCase):

    def setUp(self):
        super().setUp()
        self.aml = self.env['account.move.line'].search([], limit=1)
        if not self.aml:
            self.skipTest('no journal item to link the price difference to')
        wh = self.env['stock.warehouse'].search(
            [('company_id', '=', self.env.company.id)], limit=1)
        categ = self.env['product.category'].create({
            'name': 'PD Origin Value',
            'property_cost_method': 'fifo',
            'property_valuation': 'manual_periodic',
        })
        self.product = self.env['product.product'].create({
            'name': 'PD Origin Value Product', 'type': 'product',
            'categ_id': categ.id, 'standard_price': 100.0,
        })
        supplier = self.env.ref('stock.stock_location_suppliers')
        picking = self.env['stock.picking'].create({
            'picking_type_id': wh.in_type_id.id,
            'location_id': supplier.id,
            'location_dest_id': wh.lot_stock_id.id,
            'move_ids': [(0, 0, {
                'name': self.product.name, 'product_id': self.product.id,
                'product_uom_qty': 2, 'product_uom': self.product.uom_id.id,
                'location_id': supplier.id, 'location_dest_id': wh.lot_stock_id.id,
                'price_unit': 100.0,
            })],
        })
        picking.action_confirm()
        picking.move_ids.quantity = 2
        picking.button_validate()
        self.layer = picking.move_ids.stock_valuation_layer_ids.filtered(lambda l: l.quantity > 0)

    def _value_only(self, value, **extra):
        vals = {
            'product_id': self.product.id, 'company_id': self.env.company.id,
            'quantity': 0, 'value': value, 'stock_valuation_layer_id': self.layer.id,
            'description': 'test', 'warehouse_id': self.layer.warehouse_id.id,
        }
        vals.update(extra)
        return self.env['stock.valuation.layer'].create(vals)

    def test_bill_price_difference_reaches_origin_value(self):
        self.assertAlmostEqual(self.layer.origin_remaining_value, 200.0, places=2)
        # what purchase_stock does: add to the layer, then create the value-only layer
        self.layer.remaining_value += -40.0
        self._value_only(-40.0, account_move_line_id=self.aml.id)
        self.layer.invalidate_recordset()
        self.assertAlmostEqual(self.layer.remaining_value, 160.0, places=2)
        self.assertAlmostEqual(self.layer.origin_remaining_value, self.layer.remaining_value,
                               places=2, msg='origin value must follow the bill price difference')

    def test_value_only_layer_without_bill_line_is_left_alone(self):
        # landed-cost / revaluation layers are handled elsewhere
        self._value_only(10.0)
        self.layer.invalidate_recordset()
        self.assertAlmostEqual(self.layer.origin_remaining_value, 200.0, places=2)

    def test_no_stock_left_in_origin_is_left_alone(self):
        self.layer.origin_remaining_qty = 0.0
        self._value_only(-40.0, account_move_line_id=self.aml.id)
        self.layer.invalidate_recordset()
        self.assertAlmostEqual(self.layer.origin_remaining_value, 200.0, places=2)
