# Part of buz addons for Mogen Co. See LICENSE file.
from odoo.tests import tagged

from .common import ReverseManufacturingCommon


@tagged('post_install', '-at_install')
class TestWorkorder(ReverseManufacturingCommon):

    def test_workorders_from_reverse_bom(self):
        rmo = self._create_rmo()
        rmo.action_confirm()
        self.assertEqual(len(rmo.workorder_ids), 1)
        self.assertEqual(rmo.workorder_ids.workcenter_id, self.workcenter)

    def test_labor_cost_distributed(self):
        self._receive_input(qty=1.0)
        rmo = self._create_rmo()
        rmo.action_confirm()
        rmo.action_assign()
        wo = rmo.workorder_ids
        wo.duration = 60.0  # 1 hour at 120/h -> 120 labor cost
        rmo.button_mark_done()
        labor = sum(w._cal_cost() for w in rmo.workorder_ids)
        self.assertAlmostEqual(labor, 120.0, places=2)
        finished_value = sum(
            rmo.move_finished_ids.sudo().stock_valuation_layer_ids
            .mapped('value'))
        self.assertAlmostEqual(finished_value, 1000.0 + 120.0, delta=0.05)

    def test_qty_produced_mirrors_input(self):
        self._receive_input(qty=2.0)
        rmo = self._create_rmo(qty=2.0)
        rmo.action_confirm()
        rmo.action_assign()
        rmo.button_mark_done()
        self.assertEqual(rmo.qty_produced, 2.0)
