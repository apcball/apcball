# pylint: disable=prefer-env-translation  # Odoo 17 has no env._ (that is Odoo 18 API)
# pylint: disable=protected-access  # standard ORM helper (_read_group)
from collections import defaultdict
from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import AccessError
from odoo.tools import html2plaintext

from ..engine import gantt, scheduler

MAX_RUNS = 30
MAX_LOAD_WEEKS = 26
SOON_DAYS = 7
TOP_SUGGESTIONS = 5
ACTIVITY_LIMIT = 5
OPEN_STATES = ['proposed', 'approved']


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
            'run': False, 'cards': [], 'charts': {}, 'top_suggestions': [],
            'status': {}, 'activity': [],
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
        res['charts'] = {'load_weeks': self._load(run, tz)}
        res['top_suggestions'] = self._top_suggestions(run)
        res['status'] = self._status(run)
        res['activity'] = self._activity(run)
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
        """Weekly load/capacity totals of the plan."""
        Line = self.env['buz.plan.schedule.line']
        in_run = [('run_id', '=', run.id)]
        weekly = {'scheduled': False, 'truncated': False, 'weeks': []}
        window = self._load_window(run, tz)
        if not window:
            return weekly
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
        for wc in wcs:
            for index, per_day in enumerate((load[wc.id], capacity[wc.id])):
                for day, minutes in per_day.items():
                    day = fields.Date.to_date(day)
                    weeks[day - timedelta(days=day.weekday())][index] += minutes

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

        return weekly

    @api.model
    def _bucket(self, sugg, today):
        """overdue (high) / at_risk (medium) / on_track (low) of one open suggestion."""
        if sugg.is_late or sugg.shortage_qty > 0:
            return 'overdue'
        if sugg.date_release and sugg.date_release <= today + timedelta(days=SOON_DAYS):
            return 'at_risk'
        return 'on_track'

    @api.model
    def _open_suggestions(self, run):
        return self.env['buz.plan.suggestion'].search(
            [('run_id', '=', run.id), ('state', 'in', OPEN_STATES)])

    @api.model
    def _top_suggestions(self, run):
        """The five most urgent open suggestions: overdue first, then at risk, then on track."""
        today = fields.Date.context_today(self)
        rank = {'overdue': 0, 'at_risk': 1, 'on_track': 2}
        labels = {'overdue': _("High"), 'at_risk': _("Medium"), 'on_track': _("Low")}
        suggs = self._open_suggestions(run)
        ordered = sorted(suggs, key=lambda s: (
            rank[self._bucket(s, today)], -s.shortage_qty, s.date_release or today, s.id))
        rows = []
        for sugg in ordered[:TOP_SUGGESTIONS]:
            bucket = self._bucket(sugg, today)
            action = dict(sugg._fields['action']._description_selection(self.env))
            rows.append({
                'id': sugg.id, 'name': sugg.product_id.display_name,
                'action': action.get(sugg.action, sugg.action),
                'priority': bucket, 'priority_label': labels[bucket],
            })
        return rows

    @api.model
    def _status(self, run):
        """Share of open suggestions that are on track, at risk or overdue."""
        today = fields.Date.context_today(self)
        suggs = self._open_suggestions(run)
        counts = dict.fromkeys(('on_track', 'at_risk', 'overdue'), 0)
        for sugg in suggs:
            counts[self._bucket(sugg, today)] += 1
        total = len(suggs)
        pct = {key: int(100 * n / total) for key, n in counts.items()} if total else counts
        if total:
            # Give the rounding remainder to the largest bucket so the three add up to 100.
            pct[max(counts, key=counts.get)] += 100 - sum(pct.values())
        labels = {'on_track': _("On Track"), 'at_risk': _("At Risk"), 'overdue': _("Overdue")}
        return {
            'total': total,
            'rows': [{'key': key, 'label': labels[key], 'count': counts[key], 'pct': pct[key]}
                     for key in ('on_track', 'at_risk', 'overdue')],
        }

    @api.model
    def _activity(self, run):
        """Latest notes and status changes on the plan and its suggestions."""
        suggs = self.env['buz.plan.suggestion'].search([('run_id', '=', run.id)])
        domain = ['|', '&', ('model', '=', run._name), ('res_id', '=', run.id),
                  '&', ('model', '=', suggs._name), ('res_id', 'in', suggs.ids),
                  ('message_type', 'in', ('comment', 'notification'))]
        try:
            messages = self.env['mail.message'].search(domain, limit=ACTIVITY_LIMIT * 4,
                                                       order='id desc')
        except AccessError:
            return []
        rows = []
        for msg in messages:
            text = html2plaintext(msg.body or '').strip()
            if not text and msg.tracking_value_ids:
                text = ", ".join(
                    "%s: %s" % (t.field_id.field_description, t.new_value_char or '')
                    for t in msg.tracking_value_ids)
            if not text:
                continue
            rows.append({
                'id': msg.id, 'text': text[:140],
                'date': fields.Datetime.to_string(msg.date),
                'model': msg.model, 'res_id': msg.res_id,
            })
            if len(rows) == ACTIVITY_LIMIT:
                break
        return rows
