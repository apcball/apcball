# Part of buz addons for Mogen Co. See LICENSE file.
from odoo.tests import tagged

from .common import ReverseManufacturingCommon


@tagged('post_install', '-at_install')
class TestReverseBom(ReverseManufacturingCommon):

    def test_reverse_type_exists(self):
        selection = dict(
            self.env['mrp.bom']._fields['type']._description_selection(self.env))
        self.assertIn('reverse', selection)

    def test_bom_find_never_returns_reverse(self):
        """Normal flows (no explicit bom_type) must not pick a reverse BOM."""
        bom_by_product = self.env['mrp.bom']._bom_find(self.finished)
        self.assertFalse(bom_by_product[self.finished],
                         'Reverse BOM leaked into the normal _bom_find flow')

    def test_bom_find_explicit_reverse(self):
        bom_by_product = self.env['mrp.bom']._bom_find(
            self.finished, bom_type='reverse')
        self.assertEqual(bom_by_product[self.finished], self.bom_reverse)

    def test_recovery_line_generation(self):
        rmo = self._create_rmo(qty=2.0)
        self.assertEqual(len(rmo.recovery_line_ids), 3)
        panel = rmo.recovery_line_ids.filtered(
            lambda l: l.product_id == self.comp_panel)
        plastic = rmo.recovery_line_ids.filtered(
            lambda l: l.product_id == self.comp_plastic)
        self.assertEqual(panel.expected_qty, 2.0)
        self.assertEqual(panel.actual_qty, 2.0)
        self.assertEqual(plastic.expected_qty, 4.0)
        # 50 % recovery
        self.assertEqual(plastic.actual_qty, 2.0)
        self.assertEqual(plastic.scrap_qty, 2.0)
        # per-line destination from BOM, fallback for the line without one
        self.assertEqual(panel.destination_location_id, self.loc_reuse)

    def test_rmo_sequence(self):
        rmo = self._create_rmo()
        self.assertTrue(rmo.name.startswith('RMO'))

    def test_reverse_moves_generation(self):
        rmo = self._create_rmo()
        rmo.action_confirm()
        # one raw move: the input product
        self.assertEqual(len(rmo.move_raw_ids), 1)
        self.assertEqual(rmo.move_raw_ids.product_id, self.finished)
        # finished moves: one per recovery line with actual qty > 0, none
        # for the input product itself
        self.assertEqual(len(rmo.move_finished_ids), 3)
        self.assertNotIn(self.finished, rmo.move_finished_ids.product_id)
        panel_move = rmo.move_finished_ids.filtered(
            lambda m: m.product_id == self.comp_panel)
        self.assertEqual(panel_move.location_dest_id, self.loc_reuse)

    def test_no_backorder_split(self):
        rmo = self._create_rmo(qty=2.0)
        rmo.action_confirm()
        with self.assertRaises(Exception):
            rmo._split_productions()
