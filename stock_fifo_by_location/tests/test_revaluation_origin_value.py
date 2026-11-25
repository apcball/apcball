# -*- coding: utf-8 -*-
"""
Inventory Revaluation adds its share to each in-stock layer's remaining_value (standard).
origin_remaining_value, which prices the next issue, must carry the same amount.
"""

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestRevaluationOriginValue(TransactionCase):

    def setUp(self):
        super().setUp()
        self.layer_model = self.env['stock.valuation.layer']
        company = self.env.company
        categ = self.env['product.category'].create({
            'name': 'Reval Origin',
            'property_cost_method': 'fifo',
            'property_valuation': 'manual_periodic',
        })
        self.product = self.env['product.product'].create({
            'name': 'Reval Origin Product', 'type': 'product',
            'categ_id': categ.id, 'standard_price': 10.0,
        })
        self.wh1 = self.env['stock.warehouse'].search(
            [('company_id', '=', company.id)], limit=1)
        self.wh2 = self.env['stock.warehouse'].search(
            [('company_id', '=', company.id), ('id', '!=', self.wh1.id)], limit=1)
        if not self.wh2:
            self.wh2 = self.env['stock.warehouse'].create(
                {'name': 'Reval WH2', 'code': 'RVW2', 'company_id': company.id})
        supplier = self.env.ref('stock.stock_location_suppliers')
        self.receipt = self._picking(self.wh1.in_type_id, supplier, self.wh1.lot_stock_id, 10.0)
        self.base = self.layer_model.search([
            ('stock_move_id', '=', self.receipt.move_ids.id), ('quantity', '>', 0)], limit=1)

    def _picking(self, ptype, src, dest, qty):
        picking = self.env['stock.picking'].create({
            'picking_type_id': ptype.id, 'location_id': src.id, 'location_dest_id': dest.id,
        })
        self.env['stock.move'].create({
            'name': 'mv', 'product_id': self.product.id, 'product_uom_qty': qty,
            'product_uom': self.product.uom_id.id, 'picking_id': picking.id,
            'location_id': src.id, 'location_dest_id': dest.id,
        })
        picking.action_confirm()
        picking.action_assign()
        for ml in picking.move_line_ids:
            ml.quantity = ml.move_id.product_uom_qty
        picking.button_validate()
        return picking

    def _revalue(self, added):
        wizard = self.env['stock.valuation.layer.revaluation'].with_context(
            default_product_id=self.product.id, default_company_id=self.env.company.id).create({
                'product_id': self.product.id, 'company_id': self.env.company.id,
                'added_value': added, 'reason': 'test'})
        wizard.action_validate_revaluation()

    def test_revaluation_reaches_origin_value(self):
        self.base.invalidate_recordset()
        before = self.base.origin_remaining_value
        self._revalue(50.0)
        self.base.invalidate_recordset()
        self.assertAlmostEqual(self.base.remaining_value, before + 50.0, places=2)
        self.assertAlmostEqual(self.base.origin_remaining_value, before + 50.0, places=2,
                               msg='origin value must follow the revaluation')

    def test_revaluation_with_stock_split_across_warehouses(self):
        # 4 of 10 units moved to WH2: the revaluation is shared by the 2 in-stock layers;
        # both belong to the same origin, which must get the whole amount
        self._picking(self.wh1.int_type_id, self.wh1.lot_stock_id, self.wh2.lot_stock_id, 4.0)
        self.base.invalidate_recordset()
        before = self.base.origin_remaining_value
        self._revalue(100.0)
        in_stock = self.layer_model.search([
            ('product_id', '=', self.product.id), ('remaining_qty', '>', 0)])
        self.assertEqual(len(in_stock), 2)
        self.assertAlmostEqual(sum(in_stock.mapped('remaining_value')), before + 100.0, places=2)
        self.base.invalidate_recordset()
        self.assertAlmostEqual(self.base.origin_remaining_value, before + 100.0, places=2)
        self.assertAlmostEqual(self.base.origin_remaining_value,
                               sum(in_stock.mapped('remaining_value')), places=2,
                               msg='origin value equals the in-stock value of its chain')
