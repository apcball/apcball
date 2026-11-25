# -*- coding: utf-8 -*-
"""
Landed cost posted AFTER part of the receipt was sold.

button_validate books only (in-stock qty / move qty) of the cost in the SVL, but
origin_remaining_value used to get the FULL cost. calculate_fifo_cost prices later
issues at origin_remaining_value / origin_remaining_qty, so the next sale was costed
too high (the sold unit's share of the cost is not in stock).
"""

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestLandedCostAfterSaleOriginValue(TransactionCase):

    def setUp(self):
        super().setUp()
        self.wh = self.env['stock.warehouse'].search(
            [('company_id', '=', self.env.company.id)], limit=1)
        categ = self.env['product.category'].create({
            'name': 'LC After Sale',
            'property_cost_method': 'fifo',
            'property_valuation': 'manual_periodic',
        })
        self.product = self.env['product.product'].create({
            'name': 'LC After Sale Product', 'type': 'product',
            'categ_id': categ.id, 'standard_price': 100.0,
        })
        self.cost_product = self.env['product.product'].create({
            'name': 'LC After Sale Freight', 'type': 'service',
            'landed_cost_ok': True, 'split_method_landed_cost': 'equal',
        })
        supplier = self.env.ref('stock.stock_location_suppliers')
        customer = self.env.ref('stock.stock_location_customers')
        self.receipt = self._picking(self.wh.in_type_id, supplier, self.wh.lot_stock_id, 2)
        self.receipt.move_ids.price_unit = 100.0
        self.receipt.button_validate()
        self.move = self.receipt.move_ids
        sale = self._picking(self.wh.out_type_id, self.wh.lot_stock_id, customer, 1)
        sale.button_validate()

    def _picking(self, ptype, src, dest, qty):
        picking = self.env['stock.picking'].create({
            'picking_type_id': ptype.id,
            'location_id': src.id,
            'location_dest_id': dest.id,
            'move_ids': [(0, 0, {
                'name': self.product.name, 'product_id': self.product.id,
                'product_uom_qty': qty, 'product_uom': self.product.uom_id.id,
                'location_id': src.id, 'location_dest_id': dest.id,
            })],
        })
        picking.action_confirm()
        picking.move_ids.quantity = qty
        return picking

    def test_origin_value_gets_only_the_in_stock_share(self):
        lc = self.env['stock.landed.cost'].create({
            'picking_ids': [(4, self.receipt.id)],
            'cost_lines': [(0, 0, {
                'product_id': self.cost_product.id, 'name': 'freight',
                'price_unit': 100.0, 'split_method': 'equal',
            })],
        })
        lc.compute_landed_cost()
        lc.button_validate()

        layer = self.move.stock_valuation_layer_ids.filtered(lambda l: l.quantity > 0)
        booked = sum(self.env['stock.valuation.layer'].search([
            ('stock_landed_cost_id', '=', lc.id)]).mapped('value'))
        self.assertAlmostEqual(booked, 50.0, places=2)            # 1 of 2 units in stock
        layer.invalidate_recordset()
        self.assertAlmostEqual(layer.remaining_value, 150.0, places=2)   # 100 + 50
        self.assertAlmostEqual(layer.origin_remaining_value, layer.remaining_value, places=2,
                               msg='origin value must carry the same landed cost as the SVL')
        # per-warehouse table follows what was booked, not the full 100
        by_wh = sum(self.env['stock.valuation.layer.landed.cost'].search([
            ('landed_cost_id', '=', lc.id)]).mapped('landed_cost_value'))
        self.assertAlmostEqual(by_wh, 50.0, places=2)
