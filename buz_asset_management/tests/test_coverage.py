# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta
from psycopg2 import IntegrityError

from odoo import Command, fields
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger


class TestAssetCoverage(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.category = cls.env['buz.asset.category'].create({
            'name': 'CovCat', 'company_id': cls.company.id, 'useful_life_months': 12})
        cls.provider = cls.env['res.partner'].with_context(skip_partner_required_fields=True).create(
            {'name': 'Insurer X'})
        Users = cls.env['res.users'].with_context(no_reset_password=True, skip_partner_required_fields=True)
        base = cls.env.ref('base.group_user').id

        def user(login, group):
            return Users.create({'name': login, 'login': login,
                                 'groups_id': [Command.set([base, cls.env.ref(group).id])]})
        cls.officer = user('buz_cov_officer', 'buz_asset_management.group_asset_officer')
        cls.viewer = user('buz_cov_viewer', 'buz_asset_management.group_asset_user')
        cls.today = fields.Date.context_today(cls.env['buz.asset'])
        cls.asset = cls.env['buz.asset'].create({
            'name': 'Server', 'category_id': cls.category.id, 'gross_cost': 9000.0, 'useful_life_months': 12})
        cls.asset.sudo().write({'approval_state': 'approved', 'operational_state': 'in_service'})

    def _cov(self, start=-10, end=100, **kw):
        vals = {'asset_id': self.asset.id, 'reference': 'W-%s-%s' % (start, end),
                'date_start': self.today + relativedelta(days=start), 'date_end': self.today + relativedelta(days=end),
                'provider_id': self.provider.id}
        vals.update(kw)
        return self.env['buz.asset.coverage'].with_user(self.officer).create(vals)

    def test_state_and_days_left(self):
        self.assertEqual(self._cov(-10, 100).state, 'active')
        self.assertEqual(self._cov(-10, 20).state, 'expiring')      # default window 30 days
        self.assertEqual(self._cov(-10, 20, reminder_days=10).state, 'active')
        self.assertEqual(self._cov(-100, -1).state, 'expired')
        self.assertEqual(self._cov(5, 50).state, 'upcoming')
        self.assertEqual(self._cov(-10, 20).days_left, 20)

    def test_state_search(self):
        Cov = self.env['buz.asset.coverage']
        active, expiring = self._cov(-10, 100), self._cov(-10, 20)
        expired, upcoming = self._cov(-100, -1), self._cov(5, 50)
        for state, rec in (('active', active), ('expiring', expiring), ('expired', expired),
                           ('upcoming', upcoming)):
            found = Cov.search([('state', '=', state)])
            self.assertIn(rec, found, state)
            self.assertEqual(set(found.mapped('state')), {state}, state)
        both = Cov.search([('state', 'in', ('active', 'expiring')), ('asset_id', '=', self.asset.id)])
        self.assertEqual(both, active | expiring)

    def test_dates_and_amount_validation(self):
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            self._cov(10, 5)
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            self._cov(insured_amount=-1.0)

    def test_insurance_fields_and_company_from_asset(self):
        policy = self._cov(coverage_type='insurance', insured_amount=250000.0, reference='POL-1',
                           coverage='ไฟไหม้', terms='ค่าเสียหายส่วนแรก 5,000')
        self.assertEqual(policy.insured_amount, 250000.0)
        self.assertEqual(policy.company_id, self.asset.company_id)

    def test_asset_current_end_dates(self):
        asset = self.env['buz.asset'].create({
            'name': 'Other', 'category_id': self.category.id, 'gross_cost': 1.0, 'useful_life_months': 12})
        Cov = self.env['buz.asset.coverage']
        Cov.create({'asset_id': asset.id, 'reference': 'old', 'date_start': self.today - relativedelta(years=2),
                    'date_end': self.today - relativedelta(days=1)})
        Cov.create({'asset_id': asset.id, 'reference': 'w1', 'date_start': self.today - relativedelta(days=5),
                    'date_end': self.today + relativedelta(days=40)})
        Cov.create({'asset_id': asset.id, 'reference': 'w2', 'date_start': self.today - relativedelta(days=5),
                    'date_end': self.today + relativedelta(days=90)})
        Cov.create({'asset_id': asset.id, 'reference': 'p1', 'coverage_type': 'insurance',
                    'date_start': self.today - relativedelta(days=5), 'date_end': self.today + relativedelta(days=200)})
        self.assertEqual(asset.warranty_end_date, self.today + relativedelta(days=90))
        self.assertEqual(asset.insurance_end_date, self.today + relativedelta(days=200))

    def test_reminder_once_and_rearmed_on_renewal(self):
        Cov = self.env['buz.asset.coverage']
        soon, far = self._cov(-10, 20), self._cov(-10, 100)
        Cov._cron_remind_expiring()
        Cov._cron_remind_expiring()
        self.assertEqual(len(soon.activity_ids), 1)
        self.assertTrue(soon.reminder_sent)
        self.assertEqual(soon.activity_ids.user_id, self.officer)
        self.assertFalse(far.activity_ids)
        # Renewal moves the end date out of the window and re-arms the reminder.
        soon.with_user(self.officer).write({'date_end': self.today + relativedelta(days=200)})
        self.assertFalse(soon.reminder_sent)
        soon.with_user(self.officer).write({'date_end': self.today + relativedelta(days=15)})
        Cov._cron_remind_expiring()
        self.assertEqual(len(soon.activity_ids), 2)

    def test_expired_and_upcoming_are_not_reminded(self):
        Cov = self.env['buz.asset.coverage']
        expired, upcoming = self._cov(-100, -1), self._cov(5, 20)
        Cov._cron_remind_expiring()
        self.assertFalse(expired.activity_ids)
        self.assertFalse(upcoming.activity_ids)

    def test_no_owner_leaves_chatter_trace(self):
        rec = self._cov(-10, 5, responsible_id=False)
        self.env['buz.asset.coverage']._cron_remind_expiring()
        self.assertTrue(rec.reminder_sent)
        self.assertFalse(rec.activity_ids)
        self.assertIn(rec.reference, ' '.join(rec.message_ids.mapped('body')))

    def test_permissions(self):
        with self.assertRaises(AccessError):
            self.env['buz.asset.coverage'].with_user(self.viewer).create({
                'asset_id': self.asset.id, 'reference': 'x', 'date_start': self.today, 'date_end': self.today})
        cov = self._cov()
        self.assertTrue(cov.with_user(self.viewer).reference)
        with self.assertRaises(AccessError):
            cov.with_user(self.officer).write({'reminder_sent': True})

    def test_maintenance_warranty_hint_and_no_accounting_effect(self):
        self._cov(-10, 100)
        before = self.env['account.move'].search_count([])
        job = self.env['buz.asset.maintenance'].new({'asset_id': self.asset.id, 'planned_date': self.today})
        job._onchange_warranty_hint()
        self.assertTrue(job.warranty_covered)
        other = self.env['buz.asset'].create({
            'name': 'NoWar', 'category_id': self.category.id, 'gross_cost': 1.0, 'useful_life_months': 12})
        job2 = self.env['buz.asset.maintenance'].new({'asset_id': other.id, 'planned_date': self.today})
        job2._onchange_warranty_hint()
        self.assertFalse(job2.warranty_covered)
        self.assertEqual(self.env['account.move'].search_count([]), before)
        self.assertEqual(self.asset.book_value, 9000.0)

    def test_dashboard_tiles_match_drilldown(self):
        Dash = self.env['buz.asset.dashboard']
        base = Dash.create({}).read(['coverage_expiring_count', 'coverage_expired_count'])[0]
        self._cov(-10, 10)
        self._cov(-100, -1)
        dash = Dash.create({})
        self.assertEqual(dash.coverage_expiring_count, base['coverage_expiring_count'] + 1)
        self.assertEqual(dash.coverage_expired_count, base['coverage_expired_count'] + 1)
        self.assertEqual(self.env['buz.asset.coverage'].search_count(
            dash.action_open_expiring_coverage()['domain']), dash.coverage_expiring_count)
