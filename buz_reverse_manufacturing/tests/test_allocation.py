# Part of buz addons for Mogen Co. See LICENSE file.
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import ReverseManufacturingCommon


@tagged('post_install', '-at_install')
class TestAllocation(ReverseManufacturingCommon):

    def _get_line(self, rmo, product):
        return rmo.recovery_line_ids.filtered(lambda l: l.product_id == product)

    def test_bom_cost_ratio(self):
        rmo = self._create_rmo()
        rmo.allocation_method = 'bom_cost'
        rmo._compute_recovery_allocations()
        # bases: panel 500*1, pcb 300*1, plastic 100*1 (2 expected, 50% -> 1)
        total = 500.0 + 300.0 + 100.0
        self.assertAlmostEqual(
            self._get_line(rmo, self.comp_panel).allocation_percent,
            round(500.0 / total * 100, 2), places=2)
        self.assertAlmostEqual(
            sum(rmo.recovery_line_ids.mapped('allocation_percent')),
            100.0, places=2)

    def test_percentage(self):
        rmo = self._create_rmo()
        rmo.allocation_method = 'percentage'
        lines = rmo.recovery_line_ids
        lines[0].manual_percent = 60.0
        lines[1].manual_percent = 30.0
        lines[2].manual_percent = 10.0
        rmo._compute_recovery_allocations()
        self.assertAlmostEqual(lines[0].allocation_percent, 60.0, places=2)
        self.assertAlmostEqual(
            sum(lines.mapped('allocation_percent')), 100.0, places=2)

    def test_percentage_must_sum_100(self):
        rmo = self._create_rmo()
        rmo.allocation_method = 'percentage'
        rmo.recovery_line_ids[0].manual_percent = 50.0
        with self.assertRaises(ValidationError):
            rmo._compute_recovery_allocations()

    def test_quantity(self):
        rmo = self._create_rmo()
        rmo.allocation_method = 'quantity'
        rmo._compute_recovery_allocations()
        # actual qty: panel 1, pcb 1, plastic 1 -> 33.33 / 33.33 / 33.34
        self.assertAlmostEqual(
            sum(rmo.recovery_line_ids.mapped('allocation_percent')),
            100.0, places=2)
        self.assertAlmostEqual(
            self._get_line(rmo, self.comp_panel).allocation_percent,
            33.33, places=2)

    def test_weight(self):
        rmo = self._create_rmo()
        rmo.allocation_method = 'weight'
        rmo._compute_recovery_allocations()
        # weights x actual: panel 6, pcb 1, plastic 4
        total = 6.0 + 1.0 + 4.0
        self.assertAlmostEqual(
            self._get_line(rmo, self.comp_panel).allocation_percent,
            round(6.0 / total * 100, 2), places=2)
        self.assertAlmostEqual(
            sum(rmo.recovery_line_ids.mapped('allocation_percent')),
            100.0, places=2)

    def test_manual_amount(self):
        rmo = self._create_rmo()
        rmo.allocation_method = 'manual'
        lines = rmo.recovery_line_ids
        lines[0].manual_amount = 700.0
        lines[1].manual_amount = 200.0
        lines[2].manual_amount = 100.0
        rmo._compute_recovery_allocations()
        self.assertAlmostEqual(lines[0].allocation_percent, 70.0, places=2)
        self.assertAlmostEqual(
            sum(lines.mapped('allocation_percent')), 100.0, places=2)

    def test_zero_denominator_raises(self):
        rmo = self._create_rmo()
        rmo.allocation_method = 'manual'
        with self.assertRaises(ValidationError):
            rmo._compute_recovery_allocations()

    def test_rounding_last_line_absorbs(self):
        rmo = self._create_rmo()
        rmo.allocation_method = 'quantity'
        rmo._compute_recovery_allocations()
        total = sum(rmo.recovery_line_ids.mapped('allocation_percent'))
        self.assertEqual(round(total, 2), 100.0)

    def test_zero_qty_line_gets_zero_allocation(self):
        rmo = self._create_rmo()
        line = self._get_line(rmo, self.comp_plastic)
        line.actual_qty = 0.0
        rmo._compute_recovery_allocations()
        self.assertEqual(line.allocation_percent, 0.0)
        self.assertAlmostEqual(
            sum(rmo.recovery_line_ids.mapped('allocation_percent')),
            100.0, places=2)
