# -*- coding: utf-8 -*-
"""
Customer returns must not copy the warehouse's landed cost pool.

Production case (MO00790111, 11/2026): every return added a row worth
``all landed cost rows of the product at the original warehouse`` x
``returned qty / queued qty``. Rows of consumed lots stayed in that pool and
each new row joined it, so the values compounded to hundreds of millions, and
an inter-warehouse transfer of such a lot booked them as stock value.
"""

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestReturnDoesNotCopyLandedCostPool(TransactionCase):

    def setUp(self):
        super().setUp()
        company = self.env.company
        self.wh = self.env['stock.warehouse'].search(
            [('company_id', '=', company.id)], limit=1)
        self.wh2 = self.env['stock.warehouse'].create({
            'name': 'Return Pool WH2', 'code': 'RPW2', 'company_id': company.id,
        })
        categ = self.env['product.category'].create({
            'name': 'Return Pool',
            'property_cost_method': 'fifo',
            'property_valuation': 'manual_periodic',
        })
        self.product = self.env['product.product'].create({
            'name': 'Return Pool Product', 'type': 'product',
            'categ_id': categ.id, 'standard_price': 100.0,
        })
        freight = self.env['product.product'].create({
            'name': 'Return Pool Freight', 'type': 'service',
            'landed_cost_ok': True, 'split_method_landed_cost': 'equal',
        })
        supplier = self.env.ref('stock.stock_location_suppliers')
        self.customer = self.env.ref('stock.stock_location_customers')

        # 20 units at 100, landed cost 200 on top, then 18 are sold
        receipt = self._picking(self.wh.in_type_id, supplier, self.wh.lot_stock_id, 20)
        receipt.move_ids.price_unit = 100.0
        receipt.button_validate()
        landed = self.env['stock.landed.cost'].create({
            'picking_ids': [(4, receipt.id)],
            'cost_lines': [(0, 0, {
                'product_id': freight.id, 'name': 'freight',
                'price_unit': 200.0, 'split_method': 'equal',
            })],
        })
        landed.compute_landed_cost()
        landed.button_validate()
        self.sale = self._picking(
            self.wh.out_type_id, self.wh.lot_stock_id, self.customer, 18)
        self.sale.button_validate()

    def _picking(self, ptype, src, dest, qty, origin_move=None):
        move = {
            'name': self.product.name, 'product_id': self.product.id,
            'product_uom_qty': qty, 'product_uom': self.product.uom_id.id,
            'location_id': src.id, 'location_dest_id': dest.id,
        }
        if origin_move:
            move['origin_returned_move_id'] = origin_move.id
        picking = self.env['stock.picking'].create({
            'picking_type_id': ptype.id,
            'location_id': src.id,
            'location_dest_id': dest.id,
            'move_ids': [(0, 0, move)],
        })
        picking.action_confirm()
        picking.move_ids.quantity = qty
        picking.move_ids.picked = True
        return picking

    def _return(self, warehouse, qty):
        picking = self._picking(
            warehouse.in_type_id, self.customer, warehouse.lot_stock_id, qty,
            origin_move=self.sale.move_ids)
        picking.button_validate()
        self.assertEqual(picking.state, 'done')
        return picking.move_ids.stock_valuation_layer_ids.filtered(
            lambda layer: layer.quantity > 0)

    def _side_rows(self):
        return self.env['stock.valuation.layer.landed.cost'].search(
            [('product_id', '=', self.product.id)])

    def test_return_adds_no_landed_cost_row(self):
        before = self._side_rows()
        self.assertTrue(before, 'the landed cost must have created its own row')
        layer = self._return(self.wh2, 10)
        self.assertTrue(layer)
        self.assertEqual(self._side_rows(), before)

    def test_repeated_returns_do_not_grow_the_pool(self):
        pool = sum(self._side_rows().mapped('landed_cost_value'))
        for qty in (6, 6, 6):
            self._return(self.wh2, qty)
        self.assertAlmostEqual(
            sum(self._side_rows().mapped('landed_cost_value')), pool, places=2)

    def test_return_of_a_return_books_the_cost_of_the_returned_lot(self):
        # sending a returned lot back out prices it from that lot; a copied
        # landed cost row on the lot would be added on top
        layer = self._return(self.wh, 10)
        back = self._picking(
            self.wh.out_type_id, self.wh.lot_stock_id, self.customer, 10,
            origin_move=layer.stock_move_id)
        back.button_validate()
        outgoing = back.move_ids.stock_valuation_layer_ids.filtered(
            lambda svl: svl.quantity < 0)
        self.assertAlmostEqual(sum(outgoing.mapped('value')), -layer.value, places=2)
