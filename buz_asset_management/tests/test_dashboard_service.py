# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import Command, fields
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase

from ..services.ledger import AssetLedger


class TestDashboardService(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.today = fields.Date.context_today(cls.env['buz.asset'])
        cls.service = cls.env['buz.asset.dashboard.service']
        cls.category = cls.env['buz.asset.category'].create({
            'name': 'DashCat', 'company_id': cls.company.id, 'useful_life_months': 12})
        cls.category2 = cls.env['buz.asset.category'].create({
            'name': 'DashCat2', 'company_id': cls.company.id, 'useful_life_months': 12})
        Users = cls.env['res.users'].with_context(no_reset_password=True, skip_partner_required_fields=True)
        base = cls.env.ref('base.group_user').id
        cls.viewer = Users.create({
            'name': 'dash_viewer', 'login': 'dash_viewer',
            'groups_id': [Command.set([base, cls.env.ref('buz_asset_management.group_asset_user').id])]})
        cls.outsider = Users.create({
            'name': 'dash_outsider', 'login': 'dash_outsider', 'groups_id': [Command.set([base])]})
        cls.a1 = cls._asset('A1', cls.category, 12000.0)
        cls.a2 = cls._asset('A2', cls.category2, 6000.0)

    @classmethod
    def _asset(cls, name, category, cost):
        asset = cls.env['buz.asset'].create({
            'name': name, 'category_id': category.id, 'gross_cost': cost, 'useful_life_months': 12,
            'in_service_date': cls.today - relativedelta(months=3)})
        asset.sudo().write({'approval_state': 'approved', 'operational_state': 'in_service',
                            'accounting_state': 'capitalized'})
        return asset

    def _data(self, **filters):
        return self.service.with_user(self.viewer).get_data(filters)

    def test_access_denied_without_group(self):
        with self.assertRaises(AccessError):
            self.service.with_user(self.outsider).get_data({})

    def test_structure_and_totals_match_ledger(self):
        data = self._data(as_of=fields.Date.to_string(self.today))
        ledger = AssetLedger(self.env, self.company, self.today)
        cost = sum(ledger.cost_by_asset().values())
        accum = sum(ledger.accumulated_by_asset().values())
        self.assertAlmostEqual(data['kpis']['gross_cost'], cost)
        self.assertAlmostEqual(data['kpis']['accumulated_depreciation'], accum)
        self.assertAlmostEqual(data['kpis']['nbv'], cost - accum)
        for key in ('financial', 'by_category', 'monthly_depreciation', 'by_status', 'by_department'):
            self.assertIn(key, data['charts'])
        for key in ('end_of_life', 'recent_activities', 'warranty', 'pending_actions'):
            self.assertIn(key, data['tables'])

    def test_trend_has_12_months_and_last_point_matches_kpis(self):
        data = self._data(as_of=fields.Date.to_string(self.today))
        trend = data['charts']['trend']
        self.assertEqual(len(trend['labels']), 12)
        self.assertAlmostEqual(trend['cost'][-1], data['kpis']['gross_cost'])
        self.assertAlmostEqual(trend['accumulated'][-1], data['kpis']['accumulated_depreciation'])
        self.assertAlmostEqual(trend['nbv'][-1], data['kpis']['nbv'])

    def test_as_of_before_in_service_excludes_asset(self):
        data = self._data(as_of=fields.Date.to_string(self.today - relativedelta(months=6)))
        self.assertNotIn(self.a1.id, [r['id'] for r in data['tables']['end_of_life']])
        before = AssetLedger(self.env, self.company, self.today - relativedelta(months=6))
        self.assertNotIn(self.a1, before.live_assets())

    def test_category_filter_applies_to_every_component(self):
        data = self._data(category_id=self.category2.id)
        self.assertEqual(data['kpis']['asset_count'], 1)
        self.assertAlmostEqual(data['kpis']['gross_cost'], 6000.0)
        self.assertEqual([b['name'] for b in data['charts']['by_category']], ['DashCat2'])
        self.assertEqual(sum(s['count'] for s in data['charts']['by_status']), 1)

    def test_empty_state(self):
        data = self._data(category_id=self.env['buz.asset.category'].create({
            'name': 'Empty', 'company_id': self.company.id}).id)
        self.assertTrue(data['meta']['is_empty'])
        self.assertEqual(data['kpis']['asset_count'], 0)
        self.assertEqual(data['kpis']['gross_cost'], 0.0)

    def test_pending_depreciation_separates_states(self):
        Line = self.env['buz.asset.depreciation.line']
        self.a1.with_user(self.env.ref('base.user_admin')).sudo().action_compute_schedule()
        lines = Line.search([('asset_id', '=', self.a1.id), ('depreciation_date', '<=', self.today)])
        planned = sum(lines.filtered(lambda l: l.state == 'planned').mapped('planned_amount'))
        data = self._data(category_id=self.category.id)
        breakdown = data['kpis']['pending_breakdown']
        self.assertAlmostEqual(breakdown['planned'], planned)
        self.assertEqual(set(breakdown), {'planned', 'draft_move', 'exception'})
        # Planned lines never reduce NBV: no posted entries yet.
        self.assertAlmostEqual(data['kpis']['accumulated_depreciation'], 0.0)

    def test_warranty_kpi_counts_only_window(self):
        Cov = self.env['buz.asset.coverage']
        for ref, days in (('in', 10), ('out', 90), ('past', -5)):
            Cov.create({'asset_id': self.a1.id, 'reference': ref, 'coverage_type': 'warranty',
                        'date_start': self.today - relativedelta(days=200),
                        'date_end': self.today + relativedelta(days=days)})
        data = self._data(category_id=self.category.id)
        self.assertEqual(data['kpis']['warranty_expiring'], 1)
        self.assertEqual([r['reference'] for r in data['tables']['warranty']], ['in'])

    def test_read_only_no_moves_or_lines_created(self):
        Move, Line = self.env['account.move'], self.env['buz.asset.depreciation.line']
        moves, lines = Move.search_count([]), Line.search_count([])
        self._data()
        self.assertEqual(Move.search_count([]), moves)
        self.assertEqual(Line.search_count([]), lines)

    def test_no_company_leak(self):
        # DEV cannot create companies (buz_it_asset hook), so use an existing one the viewer lacks.
        other = self.env['res.company'].search([('id', 'not in', self.viewer.company_ids.ids)], limit=1)
        if not other:
            self.skipTest("only one company in this database")
        data = self.service.with_user(self.viewer).get_data({'company_ids': [other.id]})
        # Requested company is not in the user's allowed companies -> falls back to allowed set only.
        self.assertNotIn(other.id, data['meta']['company_ids'])

    def test_query_count_independent_of_asset_count(self):
        self._data()  # warm caches
        start = self.env.cr.sql_log_count
        self._data()
        few = self.env.cr.sql_log_count - start
        for i in range(10):
            self._asset('Bulk%s' % i, self.category, 100.0)
        self.env.invalidate_all()
        self._data()  # warm
        start = self.env.cr.sql_log_count
        self._data()
        many = self.env.cr.sql_log_count - start
        self.assertLessEqual(many, few + 5, "dashboard queries must not scale with asset count")
