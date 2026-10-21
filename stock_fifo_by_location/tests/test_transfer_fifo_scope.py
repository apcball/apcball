# -*- coding: utf-8 -*-
"""
An inter-warehouse transfer must consume the FIFO queue of its SOURCE warehouse only.

stock_by_locations builds the transfer-out layer through _prepare_internal_out_svl_vals ->
_run_fifo -> _get_fifo_candidates. That override filters by the 'fifo_warehouse_id'
context key; when the key is missing it falls back to every warehouse, so the transfer is
costed from (and decrements) layers that are physically somewhere else.
"""

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestTransferFifoScope(TransactionCase):

    def setUp(self):
        super().setUp()
        # the transfer-out layer is built by stock_by_locations; without it there is
        # no _prepare_internal_out_svl_vals path to scope
        if 'stock_by_locations' not in self.env.registry._init_modules and \
                not self.env['ir.module.module'].search_count(
                    [('name', '=', 'stock_by_locations'), ('state', '=', 'installed')]):
            self.skipTest('stock_by_locations is not installed')
        self.layer_model = self.env['stock.valuation.layer']
        company = self.env.company
        categ = self.env['product.category'].create({
            'name': 'FIFO Scope', 'property_cost_method': 'fifo',
            'property_valuation': 'manual_periodic',
        })
        self.product = self.env['product.product'].create({
            'name': 'FIFO Scope Product', 'type': 'product',
            'categ_id': categ.id, 'standard_price': 100.0,
        })
        whs = self.env['stock.warehouse'].search([('company_id', '=', company.id)], limit=3)
        # a fresh test database may hold fewer than three warehouses
        for i in range(len(whs) + 1, 4):
            whs |= self.env['stock.warehouse'].create(
                {'name': 'Scope WH%d' % i, 'code': 'SCW%d' % i, 'company_id': company.id})
        self.wh1, self.wh2, self.wh3 = whs[0], whs[1], whs[2]
        self.supplier = self.env.ref('stock.stock_location_suppliers')

    def _validate(self, picking):
        picking.action_confirm()
        picking.action_assign()
        for ml in picking.move_line_ids:
            ml.quantity = ml.move_id.product_uom_qty
        picking.button_validate()

    def _receipt(self, wh, qty):
        picking = self.env['stock.picking'].create({
            'picking_type_id': wh.in_type_id.id, 'location_id': self.supplier.id,
            'location_dest_id': wh.lot_stock_id.id,
        })
        self.env['stock.move'].create({
            'name': 'receipt', 'product_id': self.product.id, 'product_uom_qty': qty,
            'product_uom': self.product.uom_id.id, 'picking_id': picking.id,
            'location_id': self.supplier.id, 'location_dest_id': wh.lot_stock_id.id,
        })
        self._validate(picking)
        return self.layer_model.search([
            ('stock_move_id', '=', picking.move_ids.id), ('quantity', '>', 0)], limit=1)

    def _transfer(self, src, dst, qty):
        picking = self.env['stock.picking'].create({
            'picking_type_id': src.int_type_id.id, 'location_id': src.lot_stock_id.id,
            'location_dest_id': dst.lot_stock_id.id,
        })
        self.env['stock.move'].create({
            'name': 'transfer', 'product_id': self.product.id, 'product_uom_qty': qty,
            'product_uom': self.product.uom_id.id, 'picking_id': picking.id,
            'location_id': src.lot_stock_id.id, 'location_dest_id': dst.lot_stock_id.id,
        })
        self._validate(picking)
        return picking

    def test_transfer_consumes_only_the_source_warehouse_queue(self):
        # older layer in wh2 @10, newer layer in wh1 @30
        layer_wh2 = self._receipt(self.wh2, 10.0)
        layer_wh1 = self._receipt(self.wh1, 10.0)
        layer_wh2.write({'value': 100.0, 'remaining_value': 100.0})
        layer_wh1.write({'value': 300.0, 'remaining_value': 300.0})
        self.assertEqual((layer_wh2.warehouse_id, layer_wh1.warehouse_id), (self.wh2, self.wh1))
        picking = self._transfer(self.wh1, self.wh3, 5.0)  # 5 units physically leave wh1

        out_layer = self.layer_model.search([
            ('stock_move_id', '=', picking.move_ids.id), ('quantity', '<', 0)])
        self.assertAlmostEqual(
            out_layer.value, -150.0, places=2,
            msg="priced from the wh1 layer (@30), not from the older wh2 layer (@10)")
        layer_wh2.invalidate_recordset(['remaining_qty'])
        layer_wh1.invalidate_recordset(['remaining_qty'])
        self.assertEqual(layer_wh2.remaining_qty, 10.0, "wh2 stock was not touched")
        self.assertEqual(layer_wh1.remaining_qty, 5.0, "the 5 units left wh1's queue")

    def test_transferring_the_last_units_does_not_report_an_empty_queue(self):
        # the transfer drains wh1's queue; costing it again afterwards must not find
        # "nothing to cost against" and fall back to the standard price
        layer = self._receipt(self.wh1, 4.0)
        layer.write({'value': 480.0, 'remaining_value': 480.0})  # 120/unit, std price is 100
        with self.assertNoLogs('odoo.addons.stock_fifo_by_location.models.fifo_service', 'ERROR'):
            picking = self._transfer(self.wh1, self.wh2, 4.0)

        layers = self.layer_model.search([('stock_move_id', '=', picking.move_ids.id)])
        out_layer = layers.filtered(lambda l: l.quantity < 0)
        in_layers = layers.filtered(lambda l: l.quantity > 0)
        self.assertAlmostEqual(out_layer.value, -480.0, places=2)
        self.assertAlmostEqual(sum(in_layers.mapped('value')), 480.0, places=2,
                               msg="destination carries the cost the source layer was booked at")
