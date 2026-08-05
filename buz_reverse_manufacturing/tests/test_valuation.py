# Part of buz addons for Mogen Co. See LICENSE file.
from odoo.tests import tagged

from .common import ReverseManufacturingCommon


@tagged('post_install', '-at_install')
class TestValuation(ReverseManufacturingCommon):

    def _run_rmo_to_done(self, qty=1.0):
        self._receive_input(qty=qty, price=1000.0)
        rmo = self._create_rmo(qty=qty)
        rmo.action_confirm()
        rmo.action_assign()
        rmo.button_mark_done()
        return rmo

    def test_fifo_full_flow_valuation(self):
        rmo = self._run_rmo_to_done()
        self.assertEqual(rmo.state, 'done')
        raw_layers = rmo.move_raw_ids.sudo().stock_valuation_layer_ids
        out_value = -sum(raw_layers.mapped('value'))
        self.assertAlmostEqual(out_value, 1000.0, places=2,
                               msg='Input must be consumed at its FIFO cost')
        finished_layers = rmo.move_finished_ids.sudo().stock_valuation_layer_ids
        in_value = sum(finished_layers.mapped('value'))
        labor = sum(wo._cal_cost() for wo in rmo.workorder_ids)
        # 2-decimal SVL rounding per line: allow a few cents of drift
        self.assertAlmostEqual(
            in_value, 1000.0 + labor, delta=0.05,
            msg='Recovered value must equal input cost + labor')

    def test_allocation_matches_layer_values(self):
        rmo = self._run_rmo_to_done()
        labor = sum(wo._cal_cost() for wo in rmo.workorder_ids)
        total = 1000.0 + labor
        for line in rmo.recovery_line_ids.filtered('move_id'):
            layer_value = sum(
                line.move_id.sudo().stock_valuation_layer_ids.mapped('value'))
            self.assertAlmostEqual(
                layer_value, total * line.allocation_percent / 100.0,
                places=1,
                msg='Layer value must match the allocation share for %s'
                    % line.product_id.name)

    def test_journal_entries_posted(self):
        rmo = self._run_rmo_to_done()
        layers = (rmo.move_raw_ids | rmo.move_finished_ids).sudo()\
            .stock_valuation_layer_ids
        amls = layers.account_move_id.line_ids
        self.assertTrue(amls, 'Real-time valuation must post journal entries')
        self.assertAlmostEqual(
            sum(amls.mapped('debit')), sum(amls.mapped('credit')), places=2)

    def test_avco_flow(self):
        avco_finished = self._create_product(
            'RMO TV AVCO', self.category_avco, 800.0, 12.0)
        bom = self.bom_reverse.copy({
            'product_tmpl_id': avco_finished.product_tmpl_id.id})
        move = self.env['stock.move'].create({
            'name': 'in avco',
            'product_id': avco_finished.id,
            'product_uom': avco_finished.uom_id.id,
            'product_uom_qty': 1.0,
            'price_unit': 800.0,
            'location_id': self.env.ref('stock.stock_location_suppliers').id,
            'location_dest_id': self.stock_location.id,
            'company_id': self.company.id,
        })
        move._action_confirm()
        move.quantity = 1.0
        move.picked = True
        move._action_done()

        rmo = self.env['mrp.production'].create({
            'is_reverse': True,
            'product_id': avco_finished.id,
            'product_uom_id': avco_finished.uom_id.id,
            'product_qty': 1.0,
            'bom_id': bom.id,
        })
        # recovery lines auto-generated in create()
        self.assertTrue(rmo.recovery_line_ids)
        rmo.action_confirm()
        rmo.action_assign()
        rmo.button_mark_done()
        finished_value = sum(
            rmo.move_finished_ids.sudo().stock_valuation_layer_ids
            .mapped('value'))
        labor = sum(wo._cal_cost() for wo in rmo.workorder_ids)
        self.assertAlmostEqual(finished_value, 800.0 + labor, delta=0.05)
