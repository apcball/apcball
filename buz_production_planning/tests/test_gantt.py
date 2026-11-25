from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests.common import tagged

from odoo.addons.buz_production_planning.engine import gantt

from .common import SchedulingCommon, local


@tagged('post_install', '-at_install')
class TestGanttData(SchedulingCommon):

    def setUp(self):
        super().setUp()
        self.mo = self._mo('GANTT', [(self.wc1, 60)])
        self._schedule()
        self.line = self._line(self.mo)

    def _data(self, **filters):
        return self.env['buz.plan.run'].gantt_data(
            self.run_.id, fields.Datetime.to_string(local('2026-11-16 00:00')),
            fields.Datetime.to_string(local('2026-11-19 00:00')), 'Asia/Bangkok', filters)

    def test_payload_shape(self):
        data = self._data()
        self.assertEqual(data['run']['id'], self.run_.id)
        self.assertEqual([w['id'] for w in data['workcenters']], [self.wc1.id])
        row = data['lines'][0]
        self.assertEqual(row['mo'], self.mo.name)
        self.assertEqual(row['wc'], self.wc1.id)
        self.assertEqual(row['start'], fields.Datetime.to_string(self.line.date_start))
        for key in ('product', 'qty', 'operation', 'deadline', 'is_late', 'is_locked', 'is_manual', 'minutes',
                    'progress', 'wo_state'):
            self.assertIn(key, row)
        self.assertTrue(0 <= row['progress'] <= 100)
        self.assertTrue(data['can_apply'])

    def test_apply_button_hidden_for_non_manager(self):
        user = self.env['res.users'].create({
            'name': 'TEST gantt user', 'login': 'test_gantt_user_x', 'email': 'gantt@example.com',
            'street': '1 Test Rd', 'street2': 'Test', 'city': 'Bangkok', 'zip': '10110',
            'country_id': self.env.ref('base.th').id, 'phone': '021234567',
            'state_id': self.env['res.country.state'].search(
                [('country_id', '=', self.env.ref('base.th').id)], limit=1).id,
            'groups_id': [Command.set([
                self.env.ref('base.group_user').id,
                self.env.ref('buz_production_planning.group_plan_user').id])],
        })
        data = self.env['buz.plan.run'].with_user(user).gantt_data(self.run_.id)
        self.assertFalse(data['can_apply'])
        self.assertTrue(data['lines'] is not None)

    def test_capacity_and_load_per_local_day(self):
        data = self._data()
        day = '2026-11-16'
        self.assertEqual(data['capacity'][self.wc1.id][day], 480.0, "8-12 + 13-17")
        self.assertEqual(data['load'][self.wc1.id][day], 60.0)
        self.assertNotIn('2026-11-21', data['capacity'][self.wc1.id], "Saturday has no capacity")

    def test_window_excludes_lines_outside(self):
        data = self.env['buz.plan.run'].gantt_data(
            self.run_.id, fields.Datetime.to_string(local('2026-12-01 00:00')),
            fields.Datetime.to_string(local('2026-12-04 00:00')), 'Asia/Bangkok')
        self.assertFalse(data['lines'])
        self.assertEqual([w['id'] for w in data['workcenters']], [self.wc1.id], "rows stay")

    def test_filters(self):
        self.assertFalse(self._data(late_only=True)['lines'])
        self.line.is_late = True
        self.assertEqual(len(self._data(late_only=True)['lines']), 1)
        other = self.picking_type.id + 100000
        self.assertFalse(self._data(picking_type_id=other)['lines'])
        self.assertEqual(len(self._data(picking_type_id=self.picking_type.id)['lines']), 1)
        self.assertFalse(self._data(workcenter_id=self.wc2.id)['workcenters'])

    def test_workcenter_group_by_code_prefix(self):
        self.wc1.code = 'PD2 -11'
        self.assertEqual(gantt.wc_group(self.wc1)[0], 'PD2')
        self.wc1.code = False
        self.assertEqual(gantt.wc_group(self.wc1)[0], 'zz')

    def test_split_by_day_cuts_at_local_midnight(self):
        parts = dict(gantt.split_by_day(local('2026-11-16 23:00'), local('2026-11-17 01:00'), 'Asia/Bangkok'))
        self.assertEqual(parts, {'2026-11-16': 60.0, '2026-11-17': 60.0})


@tagged('post_install', '-at_install')
class TestGanttUpdate(SchedulingCommon):

    def setUp(self):
        super().setUp()
        self.mo = self._mo('GUPD', [(self.wc1, 60)], deadline=local('2026-11-18 12:00'))
        self._schedule()
        self.line = self._line(self.mo)

    def _s(self, text):
        return fields.Datetime.to_string(local(text))

    def test_move_keeps_duration_and_marks_manual(self):
        res = self.line.gantt_update(self._s('2026-11-17 10:00'), self._s('2026-11-17 11:00'), 'move')
        self.assertEqual(self.line.date_start, local('2026-11-17 10:00'))
        self.assertEqual(self.line.date_end, local('2026-11-17 11:00'))
        self.assertEqual(self.line.duration_minutes, 60)
        self.assertTrue(self.line.is_manual)
        self.assertEqual(res['id'], self.line.id)

    def test_move_snaps_into_working_time_and_keeps_work_minutes(self):
        self.line.gantt_update(self._s('2026-11-17 11:30'), self._s('2026-11-17 12:30'), 'move')
        self.assertEqual(self.line.date_end, local('2026-11-17 13:30'), "30 min + lunch + 30 min")
        self.line.gantt_update(self._s('2026-11-21 10:00'), self._s('2026-11-21 11:00'), 'move')
        self.assertEqual(self.line.date_start, local('2026-11-23 08:00'), "Saturday → Monday")

    def test_resize_counts_working_minutes_only(self):
        self.line.gantt_update(self._s('2026-11-17 10:00'), self._s('2026-11-17 13:30'), 'resize')
        self.assertEqual(self.line.duration_minutes, 150, "10-12 and 13-13:30")
        self.assertEqual(self.line.date_end, local('2026-11-17 13:30'))
        self.assertEqual(self.line.date_start, local('2026-11-17 10:00'))

    def test_resize_in_non_working_time_rejected(self):
        with self.assertRaises(UserError):
            self.line.gantt_update(self._s('2026-11-21 10:00'), self._s('2026-11-21 12:00'), 'resize')
        with self.assertRaises(UserError):
            self.line.gantt_update(self._s('2026-11-17 10:00'), self._s('2026-11-17 09:00'), 'resize')

    def test_locked_line_cannot_move(self):
        self.line.is_locked = True
        with self.assertRaises(UserError):
            self.line.gantt_update(self._s('2026-11-17 10:00'), self._s('2026-11-17 11:00'), 'move')

    def test_in_progress_line_cannot_move(self):
        self.mo.workorder_ids.write({'state': 'progress'})
        with self.assertRaises(UserError):
            self.line.gantt_update(self._s('2026-11-17 10:00'), self._s('2026-11-17 11:00'), 'move')

    def test_is_late_follows_the_move(self):
        self.assertFalse(self.line.is_late)
        self.line.gantt_update(self._s('2026-11-18 11:30'), self._s('2026-11-18 12:30'), 'move')
        self.assertTrue(self.line.is_late, "now ends after the deadline")

    def test_edited_applied_line_returns_to_proposed(self):
        self.run_.action_apply_schedule()
        self.assertEqual(self.line.state, 'applied')
        self.line.gantt_update(self._s('2026-11-17 10:00'), self._s('2026-11-17 11:00'), 'move')
        self.assertEqual(self.line.state, 'proposed')
        self.run_.action_apply_schedule()
        self.assertEqual(self.mo.workorder_ids.date_start, local('2026-11-17 10:00'))

    def test_manual_edit_survives_reschedule(self):
        self.line.gantt_update(self._s('2026-11-17 10:00'), self._s('2026-11-17 11:00'), 'move')
        self._schedule()
        self.assertEqual(self._line(self.mo).date_start, local('2026-11-17 10:00'))
