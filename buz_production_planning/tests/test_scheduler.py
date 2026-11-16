from datetime import datetime, timedelta

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests.common import tagged

from odoo.addons.buz_production_planning.engine import scheduler

from .common import PlanCommon, SchedulingCommon, local


@tagged('post_install', '-at_install')
class TestEstimate(PlanCommon):

    def test_history_used_when_enough_workorders(self):
        minutes, source = scheduler.estimate_minutes(100, 10, 0, (5, 3.0), 5, 1.0)
        self.assertEqual((minutes, source), (30.0, 'history'))

    def test_expected_times_factor_when_history_too_small(self):
        minutes, source = scheduler.estimate_minutes(100, 10, 0, (4, 3.0), 5, 1.5)
        self.assertEqual((minutes, source), (150.0, 'expected'))
        minutes, source = scheduler.estimate_minutes(100, 10, 0, None, 5, 1.0)
        self.assertEqual((minutes, source), (100.0, 'expected'))

    def test_progress_deducts_done_time_with_one_minute_floor(self):
        self.assertEqual(scheduler.estimate_minutes(100, 1, 40, None, 5, 1.0)[0], 60.0)
        self.assertEqual(scheduler.estimate_minutes(100, 1, 400, None, 5, 1.0)[0], 1.0)
        self.assertEqual(scheduler.estimate_minutes(0, 1, 0, None, 5, 1.0)[0], 1.0)

    def test_history_on_remaining_qty_does_not_deduct_done_time_again(self):
        """History minutes are per unit of the remaining qty: time already spent
        belongs to the units already produced."""
        minutes, source = scheduler.estimate_minutes(100, 4, 30, (5, 3.0), 5, 1.0)
        self.assertEqual((minutes, source), (12.0, 'history'))

    def test_consume_skips_gaps(self):
        base = datetime(2026, 1, 5)
        work = [(base + timedelta(hours=8), base + timedelta(hours=12)),
                (base + timedelta(hours=13), base + timedelta(hours=17))]
        fn = lambda a, b: [w for w in work if w[1] > a and w[0] < b]  # noqa: E731
        start, end = scheduler.consume(fn, base + timedelta(hours=11), 120)
        self.assertEqual(start, base + timedelta(hours=11))
        self.assertEqual(end, base + timedelta(hours=14))


@tagged('post_install', '-at_install')
class TestScheduler(SchedulingCommon):

    # ------------------------------------------------------------------
    def test_no_two_jobs_overlap_on_one_workcenter(self):
        a = self._mo('A', [(self.wc1, 60)])
        b = self._mo('B', [(self.wc1, 90)])
        c = self._mo('C', [(self.wc1, 30)])
        self._schedule()
        lines = self._lines(a, b, c).sorted('date_start')
        self.assertEqual(len(lines), 3)
        for first, second in zip(lines, lines[1:]):
            self.assertGreaterEqual(second.date_start, first.date_end)

    def test_operations_of_one_mo_follow_sequence(self):
        mo = self._mo('SEQ', [(self.wc1, 60), (self.wc2, 60), (self.wc1, 30)])
        self._schedule()
        lines = self._lines(mo).sorted('sequence')
        self.assertEqual(len(lines), 3)
        for first, second in zip(lines, lines[1:]):
            self.assertGreaterEqual(second.date_start, first.date_end)

    def test_working_hours_skip_lunch_and_weekend(self):
        mo = self._mo('HRS', [(self.wc1, 120)])
        self._schedule(now=local('2026-11-20 16:30'))             # Friday
        line = self._line(mo)
        self.assertEqual(line.date_start, local('2026-11-20 16:30'))
        self.assertEqual(line.date_end, local('2026-11-23 09:30'), "30 min Friday + 90 min Monday")
        self.run_.schedule_line_ids.unlink()
        self._schedule(now=local('2026-11-17 11:30'))
        line = self._line(mo)
        self.assertEqual(line.date_end, local('2026-11-17 14:30'), "30 min + lunch break + 90 min")

    def test_global_holiday_is_skipped(self):
        self.env['resource.calendar.leaves'].create({
            'name': 'TEST holiday', 'calendar_id': self.calendar.id,
            'date_from': local('2026-11-23 00:00'), 'date_to': local('2026-11-23 23:59'),
            'time_type': 'leave'})
        mo = self._mo('HOL', [(self.wc1, 120)])
        self._schedule(now=local('2026-11-20 16:30'))
        self.assertEqual(self._line(mo).date_end, local('2026-11-24 09:30'), "Monday is a holiday")

    def test_jobs_never_start_before_now(self):
        mo = self._mo('NOW', [(self.wc1, 30)])
        self._schedule(now=local('2026-11-18 10:15'))
        self.assertEqual(self._line(mo).date_start, local('2026-11-18 10:15'))

    def test_in_progress_workorder_is_not_moved(self):
        running = self._mo('RUN', [(self.wc1, 120)])
        waiting = self._mo('WAIT', [(self.wc1, 60)], deadline=self.now + timedelta(days=30))
        running.workorder_ids.write({'state': 'progress'})
        started = self.now - timedelta(minutes=20)
        loss = self.env['mrp.workcenter.productivity.loss'].search([('loss_type', '=', 'productive')], limit=1)
        self.env['mrp.workcenter.productivity'].create({
            'workorder_id': running.workorder_ids.id, 'workcenter_id': self.wc1.id,
            'loss_id': loss.id, 'date_start': started})
        self._schedule()
        run_line, wait_line = self._line(running), self._line(waiting)
        self.assertTrue(run_line.is_locked)
        self.assertEqual(run_line.date_start, self.now, "remaining work is shown from now")
        self.assertGreaterEqual(wait_line.date_start, run_line.date_end, "queued behind the running job")
        self._schedule(now=self.now + timedelta(minutes=30))
        again = self._line(running)
        self.assertEqual(again.date_start, self.now + timedelta(minutes=30))
        self.assertTrue(again.is_locked)
        self.assertEqual(running.workorder_ids.state, 'progress', "never touched")

    def test_stale_running_jobs_queue_instead_of_overlapping(self):
        """Prod has jobs left 'in progress' for months on one workcenter."""
        old = local('2026-08-27 09:00')
        loss = self.env['mrp.workcenter.productivity.loss'].search([('loss_type', '=', 'productive')], limit=1)
        mos = [self._mo('STALE%s' % i, [(self.wc1, 60)]) for i in range(3)]
        for mo in mos:
            mo.workorder_ids.write({'state': 'progress'})
            self.env['mrp.workcenter.productivity'].create({
                'workorder_id': mo.workorder_ids.id, 'workcenter_id': self.wc1.id,
                'loss_id': loss.id, 'date_start': old, 'date_end': old + timedelta(minutes=5)})
        later = self._mo('AFTER-STALE', [(self.wc1, 30)])
        self._schedule()
        lines = self._lines(*mos).sorted('date_start')
        self.assertEqual(lines[0].date_start, self.now)
        for a, b in zip(lines, lines[1:]):
            self.assertGreaterEqual(b.date_start, a.date_end, "one job at a time")
        self.assertGreaterEqual(self._line(later).date_start, lines[-1].date_end)

    def test_manual_line_survives_reschedule(self):
        a = self._mo('MAN-A', [(self.wc1, 60)])
        b = self._mo('MAN-B', [(self.wc1, 60)])
        self._schedule()
        line_a = self._line(a)
        moved_start = local('2026-11-19 09:00')
        line_a.write({'date_start': moved_start, 'date_end': moved_start + timedelta(hours=1), 'is_manual': True})
        line_id = line_a.id
        self._schedule()
        kept = self._line(a)
        self.assertEqual(kept.id, line_id)
        self.assertEqual(kept.date_start, moved_start)
        line_b = self._line(b)
        self.assertFalse(line_b.date_start < kept.date_end and line_b.date_end > kept.date_start,
                         "the other job is placed around the manual one")

    def test_locked_line_is_not_moved(self):
        a = self._mo('LCK', [(self.wc1, 60)])
        self._schedule()
        line = self._line(a)
        start, end = line.date_start, line.date_end
        line.is_locked = True
        self._schedule(now=self.now + timedelta(days=2))
        self.assertEqual((self._line(a).date_start, self._line(a).date_end), (start, end))

    def test_earlier_deadline_goes_first(self):
        late = self._mo('LATE-DL', [(self.wc1, 60)], deadline=self.now + timedelta(days=20))
        early = self._mo('EARLY-DL', [(self.wc1, 60)], deadline=self.now + timedelta(days=5))
        none = self._mo('NO-DL', [(self.wc1, 60)])
        self._schedule()
        order = self.run_.schedule_line_ids.sorted('date_start').production_id
        self.assertEqual(order.ids, [early.id, late.id, none.id], "no deadline goes last")

    def test_is_late_flag(self):
        tight = self._mo('TIGHT', [(self.wc1, 120)], deadline=self.now + timedelta(minutes=30))
        roomy = self._mo('ROOMY', [(self.wc2, 60)], deadline=self.now + timedelta(days=10))
        self._schedule()
        self.assertTrue(self._line(tight).is_late)
        self.assertFalse(self._line(roomy).is_late)

    def test_expected_duration_times_factor_without_history(self):
        mo = self._mo('FAC', [(self.wc1, 60)], qty=2.0)       # expected = 120 min
        cfg = dict(self.cfg, expected_factor=1.5)
        scheduler.run_schedule(self.run_, cfg, self.now)
        line = self._line(mo)
        self.assertEqual(line.duration_source, 'expected')
        self.assertAlmostEqual(line.duration_minutes, 180.0)

    def test_draft_mo_is_not_scheduled(self):
        product = self._product('DRAFT')
        bom = self._bom(product, [(self.rm, 1)])
        self.env['mrp.production'].create({
            'product_id': product.id, 'product_qty': 1, 'bom_id': bom.id,
            'picking_type_id': self.picking_type.id})
        stats = self._schedule()
        self.assertEqual(stats['workorders'], 0)

    def test_workcenter_without_calendar_gives_clear_error(self):
        wc = self._workcenter('TEST-NOCAL')
        mo = self._mo('NOCAL', [(wc, 30)])
        wc.resource_calendar_id = False
        self.assertTrue(mo)
        with self.assertRaises(UserError) as cm:
            self._schedule()
        self.assertIn('TEST-NOCAL', str(cm.exception))

    # ------------------------------------------------------------------
    def test_apply_writes_workorder_dates_and_keeps_state(self):
        mo = self._mo('APPLY', [(self.wc1, 60), (self.wc2, 90)])
        wos = mo.workorder_ids.sorted('id')
        states = wos.mapped('state')
        mo_state = mo.state
        self._schedule()
        lines = self._lines(mo).sorted('sequence')
        self.run_.action_apply_schedule()
        for line in lines:
            wo = line.workorder_id
            self.assertEqual(wo.date_start, line.date_start)
            self.assertEqual(wo.date_finished, line.date_end, "not recomputed from expected duration")
            self.assertTrue(wo.leave_id, "Odoo calendar leave created")
            self.assertEqual(line.state, 'applied')
        self.assertEqual(wos.mapped('state'), states, "workorder state untouched")
        self.assertEqual(mo.state, mo_state, "MO state untouched")
        self.assertEqual(mo.date_start, lines[0].date_start)
        self.assertEqual(mo.date_finished, lines[-1].date_end)
        self.assertTrue(mo.is_planned, "MO was not unplanned by the write")

    def test_apply_skips_workorder_in_progress(self):
        mo = self._mo('APPLY-RUN', [(self.wc1, 60), (self.wc2, 60)])
        first = mo.workorder_ids.sorted('id')[0]
        first.write({'state': 'progress'})
        self._schedule()
        self.run_.action_apply_schedule()
        self.assertFalse(first.date_start, "running workorder is left alone")
        second = mo.workorder_ids.sorted('id')[1]
        self.assertTrue(second.date_start)

    def test_apply_skips_mo_with_done_stock_moves(self):
        """Odoo rewrites the date of every component/finished move when MO dates
        change, done moves included. An MO that already has done moves is not
        touched, so stock history keeps its dates."""
        mo = self._mo('APPLY-DONE', [(self.wc1, 60)])
        ok = self._mo('APPLY-OK', [(self.wc1, 60)])
        component = self._product('APPLY-COMP')
        done_move = self.env['stock.move'].create({
            'name': 'consumed', 'product_id': component.id, 'product_uom_qty': 1,
            'product_uom': component.uom_id.id, 'raw_material_production_id': mo.id,
            'location_id': mo.location_src_id.id,
            'location_dest_id': component.property_stock_production.id,
            'date': datetime(2026, 11, 2, 3, 0)})
        done_move.write({'state': 'done'})
        old_date = done_move.date
        self._schedule()
        res = self.run_.apply_schedule_batch()
        self.assertEqual(res['applied'], 1, "only the MO without done moves")
        self.assertEqual(done_move.date, old_date, "done move keeps its date")
        self.assertFalse(mo.workorder_ids.date_start)
        self.assertEqual(set(self._lines(mo).mapped('state')), {'proposed'})
        self.assertTrue(ok.workorder_ids.date_start)
        self.assertEqual(res['remaining'], 0, "a blocked MO does not keep the loop running")

    def test_apply_requires_manager(self):
        self._mo('PERM', [(self.wc1, 60)])
        self._schedule()
        user = self.env['res.users'].create({
            'name': 'TEST sched user', 'login': 'test_sched_user_x', 'email': 'sched@example.com',
            'street': '1 Test Rd', 'street2': 'Test', 'city': 'Bangkok', 'zip': '10110',
            'country_id': self.env.ref('base.th').id, 'phone': '021234567',
            'state_id': self.env['res.country.state'].search(
                [('country_id', '=', self.env.ref('base.th').id)], limit=1).id,
            'groups_id': [Command.set([
                self.env.ref('base.group_user').id,
                self.env.ref('buz_production_planning.group_plan_user').id])],
        })
        with self.assertRaises(AccessError):
            self.run_.with_user(user).action_apply_schedule()

    def test_apply_without_schedule_raises(self):
        with self.assertRaises(UserError):
            self.run_.action_apply_schedule()

    def test_apply_in_batches_is_resumable(self):
        mos = [self._mo('BATCH%s' % i, [(self.wc1, 30)]) for i in range(3)]
        self._schedule()
        res = self.run_.apply_schedule_batch(limit=1)
        self.assertEqual((res['applied'], res['remaining']), (1, 2))
        res = self.run_.apply_schedule_batch(limit=2)
        self.assertEqual((res['applied'], res['remaining']), (2, 0))
        self.assertEqual(set(self._lines(*mos).mapped('state')), {'applied'})
        for mo in mos:
            self.assertTrue(mo.workorder_ids.date_start)
        with self.assertRaises(UserError, msg="nothing left to apply"):
            self.run_.apply_schedule_batch()

    def test_apply_button_reports_remaining(self):
        for i in range(scheduler.APPLY_BATCH_MOS + 2):
            self._mo('BTN%s' % i, [(self.wc1, 1)])
        self._schedule()
        action = self.run_.action_apply_schedule()
        self.assertEqual(action['params']['type'], 'warning')
        self.assertIn('2 manufacturing orders remain', action['params']['message'])
        action = self.run_.action_apply_schedule()
        self.assertEqual(action['params']['type'], 'success')

    def test_apply_batch_requires_manager(self):
        self._mo('PERM2', [(self.wc1, 60)])
        self._schedule()
        user = self.env['res.users'].create({
            'name': 'TEST batch user', 'login': 'test_batch_user_x', 'email': 'batch@example.com',
            'street': '1 Test Rd', 'street2': 'Test', 'city': 'Bangkok', 'zip': '10110',
            'country_id': self.env.ref('base.th').id, 'phone': '021234567',
            'state_id': self.env['res.country.state'].search(
                [('country_id', '=', self.env.ref('base.th').id)], limit=1).id,
            'groups_id': [Command.set([
                self.env.ref('base.group_user').id,
                self.env.ref('buz_production_planning.group_plan_user').id])],
        })
        with self.assertRaises(AccessError):
            self.run_.with_user(user).apply_schedule_batch()

