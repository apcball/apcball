# Part of buz addons for Mogen Co. See LICENSE file.
from odoo.tests import tagged

from .common import ReverseManufacturingCommon


@tagged('post_install', '-at_install')
class TestScrap(ReverseManufacturingCommon):

    def test_shortfall_creates_scrap(self):
        self._receive_input(qty=1.0)
        rmo = self._create_rmo()
        # plastic: expected 2, recovery 50 % -> actual 1, scrap 1
        plastic_line = rmo.recovery_line_ids.filtered(
            lambda l: l.product_id == self.comp_plastic)
        self.assertEqual(plastic_line.scrap_qty, 1.0)
        rmo.action_confirm()
        rmo.action_assign()
        rmo.button_mark_done()
        self.assertTrue(plastic_line.scrap_id)
        self.assertEqual(plastic_line.scrap_id.state, 'done')
        self.assertEqual(plastic_line.scrap_id.scrap_qty, 1.0)
        self.assertEqual(
            plastic_line.scrap_id.reverse_recovery_line_id, plastic_line)
        self.assertEqual(plastic_line.scrap_id.production_id, rmo)

    def test_no_scrap_when_policy_none(self):
        self._receive_input(qty=1.0)
        rmo = self._create_rmo()
        plastic_line = rmo.recovery_line_ids.filtered(
            lambda l: l.product_id == self.comp_plastic)
        plastic_line.scrap_policy = 'none'
        rmo.action_confirm()
        rmo.action_assign()
        rmo.button_mark_done()
        self.assertFalse(plastic_line.scrap_id)

    def test_no_scrap_without_shortfall(self):
        self._receive_input(qty=1.0)
        rmo = self._create_rmo()
        panel_line = rmo.recovery_line_ids.filtered(
            lambda l: l.product_id == self.comp_panel)
        rmo.action_confirm()
        rmo.action_assign()
        rmo.button_mark_done()
        self.assertFalse(panel_line.scrap_id)

    def test_scrap_has_no_valuation_impact(self):
        """Scrap consumes from the virtual production location, so it must
        not create valuation layers: the whole cost stays on the actually
        recovered components."""
        self._receive_input(qty=1.0)
        rmo = self._create_rmo()
        rmo.action_confirm()
        rmo.action_assign()
        rmo.button_mark_done()
        scraps = rmo.recovery_line_ids.scrap_id
        self.assertTrue(scraps)
        scrap_layers = scraps.move_ids.sudo().stock_valuation_layer_ids
        self.assertFalse(
            scrap_layers.filtered(lambda l: l.value),
            'Shortfall scrap must not carry stock value')
