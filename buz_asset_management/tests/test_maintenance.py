# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError
from odoo.tests.common import TransactionCase


class TestAssetMaintenance(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.category = cls.env['buz.asset.category'].create({
            'name': 'MntCat', 'company_id': cls.company.id, 'useful_life_months': 12})
        Users = cls.env['res.users'].with_context(no_reset_password=True, skip_partner_required_fields=True)
        base = cls.env.ref('base.group_user').id

        def user(login, group):
            return Users.create({'name': login, 'login': login,
                                 'groups_id': [Command.set([base, cls.env.ref(group).id])]})
        cls.officer = user('buz_mnt_officer', 'buz_asset_management.group_asset_officer')
        cls.viewer = user('buz_mnt_viewer', 'buz_asset_management.group_asset_user')
        cls.today = fields.Date.context_today(cls.env['buz.asset'])

    def _asset(self, **kw):
        vals = {'name': 'Pump', 'category_id': self.category.id, 'gross_cost': 5000.0, 'useful_life_months': 12}
        vals.update(kw)
        asset = self.env['buz.asset'].create(vals)
        asset.sudo().write({'approval_state': 'approved', 'operational_state': 'in_service'})
        return asset

    def _job(self, asset=None, **kw):
        vals = {'asset_id': (asset or self._asset()).id, 'description': 'Replace belt',
                'planned_date': self.today}
        vals.update(kw)
        return self.env['buz.asset.maintenance'].with_user(self.officer).create(vals)

    def _finish(self, job):
        job.with_user(self.officer).action_start()
        job.with_user(self.officer).write({'result': 'ok'})
        job.with_user(self.officer).action_done()

    def test_full_flow(self):
        job = self._job()
        self.assertTrue(job.name.startswith('MNT/'))
        job.with_user(self.officer).action_plan()
        self.assertEqual(job.state, 'planned')
        job.with_user(self.officer).action_start()
        self.assertEqual(job.state, 'in_progress')
        self.assertTrue(job.actual_start)
        job.with_user(self.officer).write({'result': 'เปลี่ยนสายพานแล้ว'})
        job.with_user(self.officer).action_done()
        self.assertEqual(job.state, 'done')
        self.assertTrue(job.actual_end)

    def test_asset_state_follows_jobs_and_is_restored(self):
        asset = self._asset()
        job1, job2 = self._job(asset), self._job(asset)
        job1.with_user(self.officer).action_start()
        self.assertEqual(asset.operational_state, 'under_maintenance')
        job2.with_user(self.officer).action_start()
        job1.with_user(self.officer).write({'result': 'x'})
        job1.with_user(self.officer).action_done()
        self.assertEqual(asset.operational_state, 'under_maintenance')  # second job still running
        job2.with_user(self.officer).action_cancel()
        self.assertEqual(asset.operational_state, 'in_service')

    def test_cost_is_operational_only(self):
        asset = self._asset()
        job = self._job(asset, cost=100.0, part_ids=[
            Command.create({'name': 'Belt', 'quantity': 2, 'unit_cost': 50.0}),
            Command.create({'name': 'Oil', 'quantity': 1, 'unit_cost': 25.5})])
        self.assertEqual(job.parts_cost, 125.5)
        self.assertEqual(job.total_cost, 225.5)
        before_moves = self.env['account.move'].search_count([])
        self._finish(job)
        self.assertEqual(asset.gross_cost, 5000.0)
        self.assertEqual(asset.book_value, 5000.0)
        self.assertEqual(self.env['account.move'].search_count([]), before_moves)

    def test_done_job_is_locked(self):
        job = self._job(cost=10.0, part_ids=[Command.create({'name': 'Belt', 'quantity': 1, 'unit_cost': 5.0})])
        self._finish(job)
        for vals in ({'cost': 1.0}, {'result': 'changed'}, {'description': 'x'}):
            with self.assertRaises(UserError):
                job.with_user(self.officer).write(vals)
        with self.assertRaises(UserError):
            job.part_ids.with_user(self.officer).write({'unit_cost': 1.0})
        with self.assertRaises(UserError):
            job.part_ids.with_user(self.officer).unlink()
        with self.assertRaises(UserError):
            job.with_user(self.officer).unlink()

    def test_permissions_and_state_guard(self):
        job = self._job()
        with self.assertRaises(AccessError):
            job.with_user(self.viewer).action_start()
        with self.assertRaises(AccessError):
            self.env['buz.asset.maintenance'].with_user(self.viewer).create({
                'asset_id': job.asset_id.id, 'description': 'x'})
        with self.assertRaises(AccessError):
            job.with_user(self.officer).write({'state': 'done'})
        self.assertTrue(job.with_user(self.viewer).name)  # read allowed

    def test_validations(self):
        job = self._job(planned_date=False)
        with self.assertRaises(UserError):
            job.with_user(self.officer).action_plan()  # no planned date
        job.with_user(self.officer).action_start()
        with self.assertRaises(UserError):
            job.with_user(self.officer).action_done()  # no result
        with self.assertRaises(UserError):
            job.with_user(self.officer).action_plan()  # wrong state

    def test_disposed_or_unapproved_asset_rejected(self):
        asset = self._asset()
        asset.sudo().write({'operational_state': 'disposed'})
        with self.assertRaises(UserError):
            self._job(asset).with_user(self.officer).action_start()
        draft = self.env['buz.asset'].create({
            'name': 'Draft', 'category_id': self.category.id, 'gross_cost': 1.0, 'useful_life_months': 12})
        with self.assertRaises(UserError):
            self._job(draft).with_user(self.officer).action_start()

    def test_downtime_defaults_from_actual_times(self):
        job = self._job()
        job.with_user(self.officer).action_start()
        job.sudo().write({'actual_start': fields.Datetime.now() - relativedelta(hours=3)})
        job.with_user(self.officer).write({'result': 'ok'})
        job.with_user(self.officer).action_done()
        self.assertAlmostEqual(job.downtime_hours, 3.0, delta=0.05)
        manual = self._job(downtime_hours=1.5)
        self._finish(manual)
        self.assertEqual(manual.downtime_hours, 1.5)

    def test_recurrence_schedules_one_next_activity(self):
        job = self._job(recurrence_months=3)
        self._finish(job)
        acts = job.activity_ids
        self.assertEqual(len(acts), 1)
        self.assertEqual(acts.date_deadline, self.today + relativedelta(months=3))
        self.assertEqual(acts.user_id, self.officer)
        plain = self._job()
        self._finish(plain)
        self.assertFalse(plain.activity_ids)

    def test_due_reminder_is_not_duplicated(self):
        Maint = self.env['buz.asset.maintenance']
        soon = self._job(planned_date=self.today + relativedelta(days=3))
        far = self._job(planned_date=self.today + relativedelta(days=60))
        draft = self._job(planned_date=self.today)
        for job in (soon, far):
            job.with_user(self.officer).action_plan()
        Maint._cron_remind_due()
        Maint._cron_remind_due()
        self.assertEqual(len(soon.activity_ids), 1)
        self.assertTrue(soon.reminder_sent)
        self.assertFalse(far.activity_ids)
        self.assertFalse(draft.activity_ids)

    def test_overdue_filter_and_dashboard(self):
        late = self._job(planned_date=self.today - relativedelta(days=2))
        late.with_user(self.officer).action_plan()
        fine = self._job(planned_date=self.today + relativedelta(days=5))
        fine.with_user(self.officer).action_plan()
        Maint = self.env['buz.asset.maintenance']
        self.assertTrue(late.is_overdue)
        self.assertFalse(fine.is_overdue)
        self.assertIn(late, Maint.search([('is_overdue', '=', True)]))
        self.assertNotIn(late, Maint.search([('is_overdue', '=', False)]))
        self.assertIn(fine, Maint.search([('is_overdue', '=', False)]))
        dash = self.env['buz.asset.dashboard'].create({})
        self.assertGreaterEqual(dash.maintenance_overdue_count, 1)
        self.assertEqual(
            Maint.search_count(dash.action_open_overdue_maintenance()['domain']), dash.maintenance_overdue_count)

    def test_cancel_and_reopen(self):
        job = self._job()
        job.with_user(self.officer).action_cancel()
        with self.assertRaises(UserError):
            job.with_user(self.officer).write({'description': 'x'})
        job.with_user(self.officer).action_reset_to_draft()
        self.assertEqual(job.state, 'draft')
