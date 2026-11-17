# pylint: disable=prefer-env-translation  # Odoo 17 has no env._ (that is Odoo 18 API)
# pylint: disable=protected-access  # standard ORM helper (_read_group)
from collections import defaultdict
from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import AccessError

from ..engine import gantt, scheduler

MAX_RUNS = 30
MAX_LOAD_WEEKS = 26
TOP_WORKCENTERS = 10
OPEN_STATES = ['proposed', 'approved']
DOCUMENT_STATES = ['none', 'draft', 'open', 'done', 'cancel']


class PlanDashboard(models.AbstractModel):
    """Read-only numbers of one plan for the Planning → Dashboard page."""
    _name = 'buz.plan.dashboard'
    _description = 'Planning Dashboard'

    @api.model
    def get_dashboard_data(self, run_id=False, tz=None):
        """Cards, charts and bottlenecks of one plan, as plain JSON.

        Everything is read through the ORM as the calling user: record rules and
        access rights decide what is visible. Nothing is written.
        """
        tz = self._dashboard_tz(tz)
        Run = self.env['buz.plan.run']
        visible = [('state', '!=', 'cancel'), ('company_id', 'in', self.env.companies.ids)]
        runs = Run.search(visible, order='id desc', limit=MAX_RUNS)
        run = Run.search(visible + [('id', '=', run_id)]) if run_id else Run
        run = run or runs[:1]
        if run and run not in runs:
            runs |= run
        res = {
            'runs': [{
                'id': r.id, 'name': r.name, 'state': r.state,
                'date_from': fields.Date.to_string(r.date_from),
                'date_to': fields.Date.to_string(r.date_to),
            } for r in runs],
            'run': False, 'cards': [], 'charts': {}, 'bottlenecks': [],
            'can_create': Run.check_access_rights('create', raise_exception=False),
            'updated_at': fields.Datetime.to_string(fields.Datetime.now()),
        }
        if not run:
            return res
        try:
            step, hint = run.next_step, run.next_step_hint
        except AccessError:
            # The hint counts purchase documents; a user without purchase rights gets no hint.
            step, hint = False, ''
        states = dict(Run._fields['state']._description_selection(self.env))
        res['run'] = {
            'id': run.id, 'name': run.name, 'state': run.state,
            'state_label': states.get(run.state, run.state),
            'date_from': fields.Date.to_string(run.date_from),
            'date_to': fields.Date.to_string(run.date_to),
            'planner': run.user_id.name or '',
            'next_step': step, 'next_step_hint': hint or '',
        }
        res['cards'] = self._cards(run)
        load_weeks, res['bottlenecks'] = self._load(run, tz)
        res['charts'] = {
            'load_weeks': load_weeks,
            'on_time': self._on_time(run),
            'release_weeks': self._release_weeks(run),
            'documents': self._documents(run),
        }
        return res

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @api.model
    def _dashboard_tz(self, tz):
        for name in (tz, self.env.user.tz):
            if name and name in pytz.all_timezones_set:
                return name
        return 'UTC'

    @api.model
    def _cards(self, run):
        in_run = [('run_id', '=', run.id)]
        is_open = ('state', 'in', OPEN_STATES)
        sugg, line = 'buz.plan.suggestion', 'buz.plan.schedule.line'
        # key, label, model, domain after the plan, tone, field counted distinct (optional)
        specs = [
            ('to_review', _("Suggestions to review"), sugg,
             [('state', '=', 'proposed')], 'info', False),
            ('no_document', _("Approved, no document yet"), sugg,
             [('state', '=', 'approved'), ('document_state', '=', 'none')], 'warning', False),
            ('late_suggestions', _("Late suggestions"), sugg,
             [('is_late', '=', True), is_open], 'danger', False),
            ('buy_no_vendor', _("Buy without vendor"), sugg,
             [('action', '=', 'buy'), ('vendor_id', '=', False), is_open], 'warning', False),
            ('shortage_products', _("Products short"), sugg,
             [('shortage_qty', '>', 0), is_open], 'danger', 'product_id'),
            ('late_workorders', _("Work orders finishing late"), line,
             [('is_late', '=', True)], 'danger', False),
            ('not_applied', _("Schedule lines not applied"), line,
             [('state', '=', 'proposed')], 'info', False),
        ]
        cards = []
        for key, label, model, extra, tone, distinct in specs:
            domain = in_run + extra
            if distinct:
                [[value]] = self.env[model]._read_group(
                    domain, aggregates=['%s:count_distinct' % distinct])
            else:
                value = self.env[model].search_count(domain)
            cards.append({
                'key': key, 'label': label, 'value': value or 0,
                'tone': tone if value else 'muted',
                'model': model, 'domain': domain, 'group_by': distinct,
            })
        return cards

    @api.model
    def _load_window(self, run, tz):
        """``(start, end, truncated)`` in naive UTC, or ``None`` when nothing is scheduled.

        From the Monday of the plan's first week (or the first job, if earlier) to the later
        of the plan end and the end of the last job, capped at ``MAX_LOAD_WEEKS``.
        """
        [(first, last)] = self.env['buz.plan.schedule.line']._read_group(
            [('run_id', '=', run.id)], aggregates=['date_start:min', 'date_end:max'])
        if not first or not last:
            return None
        zone = pytz.timezone(tz)

        def utc_midnight(day):
            local = zone.localize(datetime.combine(day, time.min))
            return local.astimezone(pytz.utc).replace(tzinfo=None)

        first_day = pytz.utc.localize(first).astimezone(zone).date()
        monday = run.date_from - timedelta(days=run.date_from.weekday())
        start = utc_midnight(min(monday, first_day))
        end = max(utc_midnight(run.date_to + timedelta(days=1)), last)
        cap = utc_midnight(min(monday, first_day) + timedelta(weeks=MAX_LOAD_WEEKS))
        return start, min(end, cap), end > cap

    @api.model
    def _load(self, run, tz):
        """Weekly load/capacity totals and the busiest workcenters of the plan."""
        Line = self.env['buz.plan.schedule.line']
        in_run = [('run_id', '=', run.id)]
        weekly = {'scheduled': False, 'truncated': False, 'weeks': []}
        window = self._load_window(run, tz)
        if not window:
            return weekly, []
        start, end, truncated = window
        weekly.update(scheduled=True, truncated=truncated)
        lines = Line.search(in_run + [('date_end', '>', start), ('date_start', '<', end)])
        all_wcs = self.env['mrp.workcenter'].browse(
            [wc.id for [wc] in Line._read_group(in_run, ['workcenter_id'])])
        # A workcenter whose working schedule was removed after scheduling cannot be measured.
        wcs = all_wcs.filtered('resource_calendar_id')
        worktime = scheduler.CalendarWorkTime(self.env)
        capacity, load = gantt.capacity_and_load(worktime, wcs, lines, start, end, tz)

        zone = pytz.timezone(tz)
        weeks = defaultdict(lambda: [0.0, 0.0])        # monday -> [load min, capacity min]
        per_wc = {}
        for wc in wcs:
            totals = [0.0, 0.0]
            for index, per_day in enumerate((load[wc.id], capacity[wc.id])):
                for day, minutes in per_day.items():
                    day = fields.Date.to_date(day)
                    weeks[day - timedelta(days=day.weekday())][index] += minutes
                    totals[index] += minutes
            per_wc[wc] = totals

        for monday in sorted(weeks):
            w0 = zone.localize(datetime.combine(monday, time.min)).astimezone(pytz.utc)
            w1 = zone.localize(
                datetime.combine(monday + timedelta(days=7), time.min)).astimezone(pytz.utc)
            weekly['weeks'].append({
                'week': fields.Date.to_string(monday),
                'load_hours': round(weeks[monday][0] / 60.0, 1),
                'capacity_hours': round(weeks[monday][1] / 60.0, 1),
                'domain': in_run + [
                    ('date_start', '<', fields.Datetime.to_string(w1.replace(tzinfo=None))),
                    ('date_end', '>', fields.Datetime.to_string(w0.replace(tzinfo=None)))],
            })

        def ratio(item):
            used, cap = item[1]
            return used / cap if cap else (float('inf') if used else 0.0)

        ranked = sorted(per_wc.items(), key=lambda item: (-ratio(item), item[0].name))
        bottlenecks = []
        for wc, (used, cap) in ranked[:TOP_WORKCENTERS]:
            if not used and not cap:
                continue
            bottlenecks.append({
                'id': wc.id, 'name': wc.display_name,
                'load_hours': round(used / 60.0, 1), 'capacity_hours': round(cap / 60.0, 1),
                'pct': round(100.0 * used / cap, 1) if cap else False,
                'overloaded': used > cap,
                'domain': in_run + [('workcenter_id', '=', wc.id)],
            })
        return weekly, bottlenecks

    @api.model
    def _on_time(self, run):
        """Scheduled manufacturing orders: late when any of their schedule lines is late."""
        Line = self.env['buz.plan.schedule.line']
        in_run = [('run_id', '=', run.id)]
        late_domain = in_run + [('is_late', '=', True)]
        [[total]] = Line._read_group(in_run, aggregates=['production_id:count_distinct'])
        [[late]] = Line._read_group(late_domain, aggregates=['production_id:count_distinct'])
        total, late = total or 0, late or 0
        return {
            'total': total, 'late': late, 'on_time': total - late,
            'pct': round(100.0 * (total - late) / total, 1) if total else 0.0,
            'late_domain': late_domain,
        }

    @api.model
    def _release_weeks(self, run):
        """Open suggestions per release week (Monday start), split Make / Buy."""
        domain = [('run_id', '=', run.id), ('state', 'in', OPEN_STATES)]
        counts = defaultdict(lambda: {'make': 0, 'buy': 0})
        # Grouped per day and bucketed here: ``:week`` follows the language's first weekday.
        for day, action, count in self.env['buz.plan.suggestion']._read_group(
                domain, ['date_release:day', 'action'], ['__count']):
            day = fields.Date.to_date(day)
            counts[day - timedelta(days=day.weekday())][action] += count
        return [{
            'week': fields.Date.to_string(monday),
            'make': counts[monday]['make'], 'buy': counts[monday]['buy'],
            'domain': domain + [
                ('date_release', '>=', fields.Date.to_string(monday)),
                ('date_release', '<', fields.Date.to_string(monday + timedelta(days=7)))],
        } for monday in sorted(counts)]

    @api.model
    def _documents(self, run):
        """Non-rejected suggestions by the status of their document."""
        Sugg = self.env['buz.plan.suggestion']
        domain = [('run_id', '=', run.id), ('state', '!=', 'rejected')]
        labels = dict(Sugg._fields['document_state']._description_selection(self.env))
        counts = dict(Sugg._read_group(domain, ['document_state'], ['__count']))
        return [{
            'key': key, 'label': labels.get(key, key), 'count': counts.get(key, 0),
            'domain': domain + [('document_state', '=', key)],
        } for key in DOCUMENT_STATES if key != 'cancel' or counts.get(key)]
