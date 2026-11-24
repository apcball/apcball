# pylint: disable=protected-access  # _load_window is the unit under test
import json
from datetime import timedelta

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests.common import tagged

from odoo.addons.buz_production_planning.engine import gantt, scheduler

from .common import MONDAY, SchedulingCommon, local

TZ = 'Asia/Bangkok'


class DashboardCommon(SchedulingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Dashboard = cls.env['buz.plan.dashboard']
        cls.run_.write({'date_from': MONDAY, 'horizon_weeks': 2})
        cls.vendor = cls._vendor('TEST DASH Vendor')

    def _data(self, run=None, env=None):
        dashboard = self.Dashboard if env is None else env['buz.plan.dashboard']
        return dashboard.get_dashboard_data((run or self.run_).id, TZ)

    def _sugg(self, product, run=None, **kw):
        vals = {
            'run_id': (run or self.run_).id, 'product_id': product.id, 'action': 'make',
            'qty': 5.0, 'uom_id': product.uom_id.id, 'date_need': MONDAY + timedelta(days=7),
            'date_release': MONDAY + timedelta(days=2), 'state': 'proposed',
        }
        vals.update(kw)
        return self.env['buz.plan.suggestion'].create(vals)

    def _company(self, name):
        # buz_partner_required_fields refuses the bare partner a new company creates for itself.
        return self.env['res.company'].create({'name': name, 'partner_id': self._vendor(name).id})

    def _card(self, data, key):
        return next(c for c in data['cards'] if c['key'] == key)

    def _user(self, login, groups):
        thailand = self.env.ref('base.th')
        return self.env['res.users'].create({
            'name': 'TEST %s' % login, 'login': login, 'email': '%s@example.com' % login,
            'street': '1 Test Rd', 'street2': 'Test', 'city': 'Bangkok', 'zip': '10110',
            'country_id': thailand.id, 'phone': '021234567',
            'state_id': self.env['res.country.state'].search(
                [('country_id', '=', thailand.id)], limit=1).id,
            'groups_id': [Command.set([self.env.ref(g).id for g in groups])],
        })


@tagged('post_install', '-at_install')
class TestDashboardPlans(DashboardCommon):

    def test_payload_shape_and_json(self):
        data = self._data()
        for key in ('runs', 'run', 'cards', 'charts', 'bottlenecks', 'updated_at', 'can_create'):
            self.assertIn(key, data)
        for key in ('id', 'name', 'state', 'state_label', 'date_from', 'date_to', 'planner',
                    'next_step', 'next_step_hint'):
            self.assertIn(key, data['run'])
        self.assertEqual(
            [c['key'] for c in data['cards']],
            ['to_review', 'no_document', 'late_suggestions', 'buy_no_vendor', 'shortage_products',
             'late_workorders', 'not_applied'])
        for card in data['cards']:
            self.assertEqual(
                set(card), {'key', 'label', 'value', 'tone', 'model', 'domain', 'group_by'})
        self.assertEqual(
            set(data['charts']), {'load_weeks', 'on_time', 'release_weeks', 'documents'})
        json.dumps(data)

    def test_unscheduled_plan_has_no_load(self):
        data = self._data()
        self.assertFalse(data['charts']['load_weeks']['scheduled'])
        self.assertFalse(data['charts']['load_weeks']['weeks'])
        self.assertFalse(data['bottlenecks'])
        self.assertEqual(data['charts']['on_time']['total'], 0)

    def test_no_plan_at_all(self):
        company = self._company('TEST DASH empty company')
        data = self.Dashboard.with_context(
            allowed_company_ids=company.ids).get_dashboard_data(False, TZ)
        self.assertIs(data['run'], False)
        self.assertEqual(data['runs'], [])
        self.assertEqual(data['cards'], [])
        self.assertEqual(data['bottlenecks'], [])
        json.dumps(data)

    def test_default_is_latest_not_cancelled(self):
        newer = self.env['buz.plan.run'].create({'state': 'computed'})
        data = self.Dashboard.get_dashboard_data(False, TZ)
        self.assertEqual(data['run']['id'], newer.id)
        self.assertEqual(data['runs'][0]['id'], newer.id)
        self.assertLessEqual(len(data['runs']), 30)
        newer.action_cancel()
        data = self.Dashboard.get_dashboard_data(False, TZ)
        self.assertEqual(data['run']['id'], self.run_.id)
        self.assertNotIn(newer.id, [r['id'] for r in data['runs']])

    def test_explicit_run_is_honoured(self):
        newer = self.env['buz.plan.run'].create({'state': 'computed'})
        self.assertEqual(self._data()['run']['id'], self.run_.id)
        self.assertEqual(self._data(newer)['run']['id'], newer.id)

    def test_cancelled_or_missing_run_falls_back_to_latest(self):
        newer = self.env['buz.plan.run'].create({'state': 'computed'})
        newer.action_cancel()
        self.assertEqual(self._data(newer)['run']['id'], self.run_.id)
        self.assertEqual(
            self.Dashboard.get_dashboard_data(newer.id + 100000, TZ)['run']['id'], self.run_.id)

    def test_other_company_plan_is_not_listed_nor_counted(self):
        other = self._company('TEST DASH other company')
        foreign = self.env['buz.plan.run'].create({
            'state': 'computed', 'company_id': other.id, 'warehouse_ids': [Command.clear()]})
        self._sugg(self.fg, run=foreign)
        mine = self.Dashboard.with_context(allowed_company_ids=self.env.company.ids)
        data = mine.get_dashboard_data(foreign.id, TZ)
        self.assertNotIn(foreign.id, [r['id'] for r in data['runs']])
        self.assertNotEqual(data['run']['id'], foreign.id, "unreadable plan falls back")
        theirs = self.Dashboard.with_context(allowed_company_ids=other.ids)
        data = theirs.get_dashboard_data(False, TZ)
        self.assertEqual([r['id'] for r in data['runs']], [foreign.id])
        self.assertEqual(self._card(data, 'to_review')['value'], 1)

    def test_mrp_user_can_read_the_dashboard(self):
        user = self._user('test_dash_mrp', ['base.group_user', 'mrp.group_mrp_user'])
        self._sugg(self.fg)
        data = self._data(env=self.env(user=user))
        self.assertEqual(data['run']['id'], self.run_.id)
        self.assertEqual(self._card(data, 'to_review')['value'], 1)
        self.assertFalse(data['can_create'], "read-only user gets no Create button")

    def test_user_without_mrp_group_is_refused(self):
        user = self._user('test_dash_nobody', ['base.group_user'])
        with self.assertRaises(AccessError):
            self._data(env=self.env(user=user))


@tagged('post_install', '-at_install')
class TestDashboardNumbers(DashboardCommon):

    def setUp(self):
        super().setUp()
        # Three operations on one MO, plus a second MO: 2 MOs, 4 schedule lines.
        self.mo3 = self._mo('DASH3', [(self.wc1, 60), (self.wc2, 120), (self.wc1, 30)])
        self.mo1 = self._mo('DASH1', [(self.wc1, 600)])
        self._schedule()
        self._line(self.mo3, 1).is_late = True
        self._line(self.mo1).state = 'applied'

        other = self._product('DASH-OTHER')
        self.proposed = self._sugg(self.fg, shortage_qty=4.0)
        self.approved = self._sugg(self.semi, state='approved')
        self.with_doc = self._sugg(self.semi, state='approved', production_id=self.mo1.id)
        self.late = self._sugg(other, is_late=True)
        self.buy_open = self._sugg(self.rm, action='buy', shortage_qty=5.0)
        self.buy_ok = self._sugg(
            self.rm, action='buy', state='approved', vendor_id=self.vendor.id, shortage_qty=3.0,
            date_release=MONDAY + timedelta(days=9))
        self.rejected = self._sugg(
            other, action='buy', state='rejected', is_late=True, shortage_qty=9.0)

    def test_cards_match_known_counts(self):
        data = self._data()
        expected = {
            'to_review': 3,           # proposed, late, buy_open
            'no_document': 2,         # approved, buy_ok
            'late_suggestions': 1,
            'buy_no_vendor': 1,
            'shortage_products': 2,   # fg and rm (rm twice, rejected ignored)
            'late_workorders': 1,
            'not_applied': 3,
        }
        self.assertEqual({c['key']: c['value'] for c in data['cards']}, expected)

    def test_card_value_equals_search_count_of_its_domain(self):
        for card in self._data()['cards']:
            Model = self.env[card['model']]
            self.assertEqual(card['domain'][0], ('run_id', '=', self.run_.id))
            if card['group_by']:
                rows = len(Model.search(card['domain']).mapped(card['group_by']))
            else:
                rows = Model.search_count(card['domain'])
            self.assertEqual(card['value'], rows, card['key'])

    def test_tone_is_muted_only_when_zero(self):
        data = self._data()
        self.assertEqual(self._card(data, 'late_suggestions')['tone'], 'danger')
        self.late.state = 'rejected'
        self.assertEqual(self._card(self._data(), 'late_suggestions')['tone'], 'muted')

    def test_second_plan_does_not_leak(self):
        before = {c['key']: c['value'] for c in self._data()['cards']}
        charts_before = self._data()['charts']
        second = self.env['buz.plan.run'].create({'state': 'computed', 'date_from': MONDAY})
        self._sugg(self.fg, run=second, is_late=True, shortage_qty=1.0)
        self._sugg(self.rm, run=second, action='buy')
        self.assertEqual({c['key']: c['value'] for c in self._data()['cards']}, before)
        self.assertEqual(self._data()['charts'], charts_before)
        other = {c['key']: c['value'] for c in self._data(second)['cards']}
        self.assertEqual(other['to_review'], 2)
        self.assertEqual(other['late_workorders'], 0)
        self.assertEqual(other['not_applied'], 0)

    def test_weekly_totals_equal_capacity_and_load(self):
        data = self._data()
        weekly = data['charts']['load_weeks']
        self.assertTrue(weekly['scheduled'])
        self.assertFalse(weekly['truncated'])
        start, end, _cut = self.Dashboard._load_window(self.run_, TZ)
        self.assertEqual(start, local('2026-11-16 00:00'))
        self.assertEqual(end, local('2026-11-30 00:00'), "2 weeks, nothing runs past the horizon")
        lines = self.run_.schedule_line_ids
        capacity, load = gantt.capacity_and_load(
            scheduler.CalendarWorkTime(self.env), lines.workcenter_id, lines, start, end, TZ)
        cap_minutes = sum(m for per_day in capacity.values() for m in per_day.values())
        load_minutes = sum(m for per_day in load.values() for m in per_day.values())
        self.assertEqual(load_minutes, 60 + 120 + 30 + 600)
        self.assertEqual(cap_minutes, 2 * 10 * 480, "2 workcenters x 10 working days x 8 h")
        self.assertAlmostEqual(
            sum(w['load_hours'] for w in weekly['weeks']), load_minutes / 60.0, delta=0.2)
        self.assertAlmostEqual(
            sum(w['capacity_hours'] for w in weekly['weeks']), cap_minutes / 60.0, delta=0.2)
        self.assertEqual([w['week'] for w in weekly['weeks']], ['2026-11-16', '2026-11-23'])
        first = weekly['weeks'][0]
        self.assertEqual(
            self.env['buz.plan.schedule.line'].search_count(first['domain']), 4)

    def test_bottlenecks_rank_by_load_share(self):
        rows = self._data()['bottlenecks']
        self.assertEqual([r['id'] for r in rows], [self.wc1.id, self.wc2.id])
        self.assertEqual(rows[0]['load_hours'], 11.5)
        self.assertEqual(rows[0]['capacity_hours'], 80.0)
        self.assertEqual(rows[0]['pct'], 14.4)
        self.assertFalse(rows[0]['overloaded'])
        self.assertEqual(
            self.env['buz.plan.schedule.line'].search_count(rows[0]['domain']), 3)

    def test_window_follows_the_schedule_past_the_horizon_and_is_capped(self):
        line = self._line(self.mo1)
        line.write({'date_start': local('2027-01-04 08:00'), 'date_end': local('2027-01-04 18:00')})
        start, end, truncated = self.Dashboard._load_window(self.run_, TZ)
        self.assertEqual(end, local('2027-01-04 18:00'))
        self.assertFalse(truncated)
        line.write({'date_start': local('2027-09-06 08:00'), 'date_end': local('2027-09-06 18:00')})
        start, end, truncated = self.Dashboard._load_window(self.run_, TZ)
        self.assertEqual(end, start + timedelta(weeks=26))
        self.assertTrue(truncated)
        self.assertTrue(self._data()['charts']['load_weeks']['truncated'])

    def test_on_time_counts_manufacturing_orders(self):
        on_time = self._data()['charts']['on_time']
        self.assertEqual(
            (on_time['total'], on_time['late'], on_time['on_time']), (2, 1, 1),
            "one late line of three makes one late MO")
        self.assertEqual(on_time['pct'], 50.0)
        self.assertEqual(
            self.env['buz.plan.schedule.line'].search_count(on_time['late_domain']), 1)

    def test_release_weeks_split_make_and_buy(self):
        weeks = self._data()['charts']['release_weeks']
        self.assertEqual(
            [(w['week'], w['make'], w['buy']) for w in weeks],
            [('2026-11-16', 4, 1), ('2026-11-23', 0, 1)])
        Sugg = self.env['buz.plan.suggestion']
        self.assertEqual([Sugg.search_count(w['domain']) for w in weeks], [5, 1])

    def test_documents_by_status(self):
        docs = {d['key']: d for d in self._data()['charts']['documents']}
        self.assertEqual(set(docs), {'none', 'draft', 'open', 'done'}, "cancel hidden when empty")
        self.assertEqual(docs['none']['count'], 5)
        self.assertEqual(docs['open']['count'], 1, "confirmed MO = in progress")
        Sugg = self.env['buz.plan.suggestion']
        for doc in docs.values():
            self.assertEqual(doc['count'], Sugg.search_count(doc['domain']), doc['key'])

    def test_dashboard_writes_nothing(self):
        lines = self.run_.schedule_line_ids
        before = (lines.mapped('write_date'), self.run_.suggestion_ids.sorted('id').mapped('state'),
                  self.run_.state, len(lines))
        self._data()
        self.env.invalidate_all()
        after = (lines.mapped('write_date'), self.run_.suggestion_ids.sorted('id').mapped('state'),
                 self.run_.state, len(self.run_.schedule_line_ids))
        self.assertEqual(before, after)
