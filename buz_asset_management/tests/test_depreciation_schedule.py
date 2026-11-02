# -*- coding: utf-8 -*-
from datetime import date

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests.common import BaseCase, TransactionCase

from odoo.addons.buz_asset_management.services.depreciation import (
    compute_straight_line_schedule,
)


def _round2(value):
    return round(value + 1e-9, 2)


class TestScheduleMath(BaseCase):
    """Pure math: no database."""

    def _amounts(self, rows):
        return [row['amount'] for row in rows]

    def test_even_split(self):
        rows = compute_straight_line_schedule(1200.0, 12, date(2026, 1, 1), _round2)
        self.assertEqual(self._amounts(rows), [100.0] * 12)
        self.assertEqual(rows[-1]['remaining_after'], 0.0)

    def test_last_period_absorbs_remainder(self):
        rows = compute_straight_line_schedule(1000.0, 3, date(2026, 1, 1), _round2)
        self.assertEqual(self._amounts(rows), [333.33, 333.33, 333.34])

    def test_total_equals_base_for_awkward_cases(self):
        for base, periods in ((100.01, 7), (0.05, 10), (999999.99, 36), (1.0, 3)):
            rows = compute_straight_line_schedule(base, periods, date(2026, 5, 20), _round2)
            self.assertEqual(len(rows), periods)
            self.assertAlmostEqual(sum(self._amounts(rows)), base, places=2)
            self.assertTrue(all(amount >= 0 for amount in self._amounts(rows)))
            self.assertEqual(rows[-1]['remaining_after'], 0.0)

    def test_zero_or_negative_base_has_no_schedule(self):
        self.assertEqual(compute_straight_line_schedule(0.0, 12, date(2026, 1, 1), _round2), [])
        self.assertEqual(compute_straight_line_schedule(-5.0, 12, date(2026, 1, 1), _round2), [])

    def test_invalid_periods_rejected(self):
        with self.assertRaises(ValueError):
            compute_straight_line_schedule(100.0, 0, date(2026, 1, 1), _round2)

    def test_first_period_is_in_service_month(self):
        rows = compute_straight_line_schedule(1200.0, 12, date(2026, 3, 15), _round2)
        self.assertEqual(rows[0]['period_start'], date(2026, 3, 1))
        self.assertEqual(rows[0]['depreciation_date'], date(2026, 3, 31))
        self.assertEqual(rows[-1]['depreciation_date'], date(2027, 2, 28))

    def test_month_end_start_does_not_skip_month(self):
        rows = compute_straight_line_schedule(300.0, 3, date(2026, 1, 31), _round2)
        self.assertEqual([r['depreciation_date'] for r in rows],
                         [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)])

    def test_leap_year_february(self):
        rows = compute_straight_line_schedule(200.0, 2, date(2024, 1, 10), _round2)
        self.assertEqual(rows[1]['depreciation_date'], date(2024, 2, 29))

    def test_year_rollover(self):
        rows = compute_straight_line_schedule(300.0, 3, date(2026, 12, 5), _round2)
        self.assertEqual([r['depreciation_date'] for r in rows],
                         [date(2026, 12, 31), date(2027, 1, 31), date(2027, 2, 28)])


class TestScheduleModel(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.category = cls.env['buz.asset.category'].create({
            'name': 'Equipment', 'company_id': cls.env.company.id, 'useful_life_months': 12,
        })
        Users = cls.env['res.users'].with_context(
            no_reset_password=True, skip_partner_required_fields=True)

        def make_user(login, group):
            return Users.create({
                'name': login, 'login': login, 'email': '%s@example.com' % login,
                'groups_id': [Command.set([
                    cls.env.ref('base.group_user').id,
                    cls.env.ref('buz_asset_management.%s' % group).id])],
            })
        cls.officer = make_user('buz_sched_officer', 'group_asset_officer')
        cls.accountant = make_user('buz_sched_accountant', 'group_asset_accountant')

    def _asset(self, **kw):
        vals = {
            'name': 'Server', 'category_id': self.category.id,
            'gross_cost': 1200.0, 'residual_value': 0.0, 'useful_life_months': 12,
            'in_service_date': '2026-03-15',
        }
        vals.update(kw)
        return self.env['buz.asset'].create(vals)

    def test_compute_creates_schedule(self):
        asset = self._asset()
        asset.with_user(self.accountant).action_compute_schedule()
        lines = asset.depreciation_line_ids.sorted('sequence')
        self.assertEqual(len(lines), 12)
        self.assertAlmostEqual(sum(lines.mapped('planned_amount')), asset.depreciable_base, places=2)
        self.assertEqual(lines[0].depreciation_date, date(2026, 3, 31))
        self.assertEqual(set(lines.mapped('state')), {'planned'})
        self.assertEqual(len(set(lines.mapped('idempotency_key'))), 12)

    def test_start_date_overrides_in_service_date(self):
        asset = self._asset(depreciation_start_date='2026-06-01')
        asset.with_user(self.accountant).action_compute_schedule()
        self.assertEqual(asset.depreciation_line_ids.sorted('sequence')[0].depreciation_date,
                         date(2026, 6, 30))

    def test_recompute_replaces_planned_lines(self):
        asset = self._asset()
        asset.with_user(self.accountant).action_compute_schedule()
        asset.gross_cost = 2400.0
        asset.with_user(self.accountant).action_compute_schedule()
        lines = asset.depreciation_line_ids
        self.assertEqual(len(lines), 12)
        self.assertEqual(set(lines.mapped('calculation_version')), {2})
        self.assertAlmostEqual(sum(lines.mapped('planned_amount')), 2400.0, places=2)

    def test_recompute_blocked_once_entries_exist(self):
        asset = self._asset()
        asset.with_user(self.accountant).action_compute_schedule()
        asset.depreciation_line_ids[:1].sudo().write({'state': 'posted'})
        with self.assertRaises(UserError):
            asset.with_user(self.accountant).action_compute_schedule()
        self.assertEqual(len(asset.depreciation_line_ids), 12)

    def test_requires_start_date(self):
        asset = self._asset(in_service_date=False)
        with self.assertRaises(UserError):
            asset.with_user(self.accountant).action_compute_schedule()

    def test_zero_base_gives_empty_schedule(self):
        asset = self._asset(gross_cost=500.0, residual_value=500.0)
        asset.with_user(self.accountant).action_compute_schedule()
        self.assertFalse(asset.depreciation_line_ids)

    def test_officer_cannot_compute(self):
        asset = self._asset()
        with self.assertRaises(AccessError):
            asset.with_user(self.officer).action_compute_schedule()

    def test_lines_not_directly_writable(self):
        asset = self._asset()
        asset.with_user(self.accountant).action_compute_schedule()
        line = asset.depreciation_line_ids[:1].with_user(self.accountant)
        with self.assertRaises(AccessError):
            line.write({'planned_amount': 1.0})
        with self.assertRaises(AccessError):
            self.env['buz.asset.depreciation.line'].with_user(self.accountant).create({})
