# -*- coding: utf-8 -*-
"""
Landed cost booked in SVL must never exceed the allocation of the move.

Bug: button_validate used (remaining_qty / move_qty) with remaining_qty summed over
the whole origin chain, so a chain holding more stock than the move itself (e.g. a
transfer of 70 units attributed to a 16-unit receipt) booked up to 6x the allocation.
"""

from unittest import mock

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestLandedCostRatioCap(TransactionCase):

    def setUp(self):
        super().setUp()
        self.wh = self.env['stock.warehouse'].search(
            [('company_id', '=', self.env.company.id)], limit=1)
        categ = self.env['product.category'].create({
            'name': 'LC Ratio Cap',
            'property_cost_method': 'fifo',
            'property_valuation': 'manual_periodic',
        })
        self.product = self.env['product.product'].create({
            'name': 'LC Ratio Cap Product', 'type': 'product',
            'categ_id': categ.id, 'standard_price': 10.0,
        })
        self.cost_product = self.env['product.product'].create({
            'name': 'LC Ratio Cap Freight', 'type': 'service',
            'landed_cost_ok': True, 'split_method_landed_cost': 'equal',
        })
        supplier = self.env.ref('stock.stock_location_suppliers')
        self.picking = self.env['stock.picking'].create({
            'picking_type_id': self.wh.in_type_id.id,
            'location_id': supplier.id,
            'location_dest_id': self.wh.lot_stock_id.id,
            'move_ids': [(0, 0, {
                'name': self.product.name,
                'product_id': self.product.id,
                'product_uom_qty': 5,
                'product_uom': self.product.uom_id.id,
                'location_id': supplier.id,
                'location_dest_id': self.wh.lot_stock_id.id,
                'price_unit': 10.0,
            })],
        })
        self.picking.action_confirm()
        self.picking.move_ids.quantity = 5
        self.picking.button_validate()
        self.move = self.picking.move_ids

    def _lc_booked(self, inflate):
        lc = self.env['stock.landed.cost'].create({
            'picking_ids': [(4, self.picking.id)],
            'cost_lines': [(0, 0, {
                'product_id': self.cost_product.id, 'name': 'freight',
                'price_unit': 100.0, 'split_method': 'equal',
            })],
        })
        lc.compute_landed_cost()
        if inflate:
            orig = type(lc)._get_landed_cost_targets

            def inflated(rec, move):
                origin, pos, rem, qty = orig(rec, move)
                return origin, pos, rem * inflate, qty

            with mock.patch.object(type(lc), '_get_landed_cost_targets', inflated):
                lc.button_validate()
        else:
            lc.button_validate()
        layers = self.env['stock.valuation.layer'].search([
            ('stock_move_id', '=', self.move.id),
            ('stock_landed_cost_id', '=', lc.id),
        ])
        return sum(layers.mapped('value'))

    def test_booked_equals_allocation_when_all_in_stock(self):
        self.assertAlmostEqual(self._lc_booked(inflate=0), 100.0, places=2)

    def test_booked_capped_when_chain_remaining_exceeds_move_qty(self):
        # chain reports 3x the move qty -> before the fix this booked 300
        self.assertAlmostEqual(self._lc_booked(inflate=3), 100.0, places=2)
