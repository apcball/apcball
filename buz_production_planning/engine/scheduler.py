"""Finite-capacity forward scheduler for buz_production_planning.

* ``schedule(tasks, worktime, now)``  pure placement, no database access.
* ``CalendarWorkTime``                working-time source backed by resource.calendar.
* ``build_tasks(run, cfg, now)``      reads workorders and returns tasks.
* ``run_schedule(run, cfg, now)``     builds, places and writes buz.plan.schedule.line.
* ``apply_lines(lines)``              writes planned dates on the real workorders.

All datetimes are naive UTC (Odoo convention).
"""
# pylint: disable=prefer-env-translation  # Odoo 17 has no env._ (that is Odoo 18 API)
from collections import defaultdict
from datetime import datetime, timedelta

import pytz

from odoo import _, fields
from odoo.exceptions import UserError

CHUNK = timedelta(days=14)
MAX_CHUNKS = 50            # same 700 day horizon Odoo uses for its own planning
MIN_MINUTES = 1.0
OPEN_WO_STATES = ('pending', 'waiting', 'ready', 'progress')


# ----------------------------------------------------------------------
# Pure helpers
# ----------------------------------------------------------------------
def estimate_minutes(expected, qty, done_minutes, stat, min_history, factor):
    """Remaining minutes and where the number came from.

    ``stat`` is ``(done_workorder_count, actual_minutes_per_unit)`` or None.
    History is used only when it has at least ``min_history`` workorders.
    ``qty`` is the quantity still to produce, so the history estimate already
    excludes finished units; ``done_minutes`` is deducted only from the expected
    duration, which covers the whole workorder.
    """
    if stat and stat[0] >= min_history and stat[1] > 0:
        return max(stat[1] * qty, MIN_MINUTES), 'history'
    total = (expected or 0.0) * factor
    return max(total - done_minutes, MIN_MINUTES), 'expected'


def consume(intervals_fn, start, minutes):
    """Spend ``minutes`` of working time from ``start``.

    ``intervals_fn(a, b)`` yields working ``(start, end)`` pairs inside [a, b).
    Returns the real start (first working instant) and the end.
    """
    remaining, first, cursor = minutes, None, start
    for _chunk in range(MAX_CHUNKS):
        chunk_end = cursor + CHUNK
        for a, b in intervals_fn(cursor, chunk_end):
            a = max(a, cursor)
            if b <= a:
                continue
            if first is None:
                first = a
            available = (b - a).total_seconds() / 60.0
            if available >= remaining - 1e-9:
                return first, a + timedelta(minutes=remaining)
            remaining -= available
        cursor = chunk_end
    raise UserError(_(
        "No working time found within 700 days after %s. "
        "Check the working schedule of the workcenter.", start))


class Task:
    def __init__(self, wo_id, mo_id, wc_id, minutes, source, mo_rank, order, deps=(),
                 fixed=None, locked=False, manual=False, deadline=None, line_id=False):
        self.wo_id, self.mo_id, self.wc_id = wo_id, mo_id, wc_id
        self.minutes, self.source = minutes, source
        self.mo_rank, self.order = mo_rank, order
        self.deps = list(deps)
        self.fixed = fixed            # (start, end) when the task must not move
        self.locked, self.manual = locked, manual
        self.deadline = deadline
        self.line_id = line_id        # existing schedule line kept as is


def _first_clear(worktime, wc_id, earliest, minutes, blocks):
    """Earliest slot on the workcenter that overlaps none of ``blocks``."""
    cursor = earliest
    for _attempt in range(10000):
        start, end = consume(lambda a, b: worktime.intervals(wc_id, a, b), cursor, minutes)
        clash = [e for s, e in blocks if s < end and e > start]
        if not clash:
            return start, end
        cursor = max(clash)
    raise UserError(_("The workcenter queue could not be resolved (too many fixed jobs)."))


def schedule(tasks, worktime, now):
    """Place every non-fixed task; return ``{wo_id: result dict}``.

    A workcenter holds one job at a time. Jobs go on in MO priority order;
    a job starts at max(next free time of the workcenter, end of its
    predecessors in the same MO, now). Fixed tasks keep their time and block
    the workcenter.
    """
    placed, blocks = {}, defaultdict(list)
    free_at = defaultdict(lambda: now)

    def record(task, start, end):
        placed[task.wo_id] = {
            'start': start, 'end': end, 'minutes': task.minutes, 'source': task.source,
            'is_locked': task.locked, 'is_manual': task.manual,
            'is_late': bool(task.deadline and end > task.deadline), 'fixed': task.fixed is not None,
            'line_id': task.line_id,
        }

    for t in tasks:
        if t.fixed:
            record(t, *t.fixed)
            blocks[t.wc_id].append(t.fixed)

    by_mo = defaultdict(list)
    for t in tasks:
        if not t.fixed:
            by_mo[t.mo_id].append(t)
    for mo_id in sorted(by_mo, key=lambda m: by_mo[m][0].mo_rank):
        pending = sorted(by_mo[mo_id], key=lambda t: t.order)
        in_mo = {t.wo_id for t in pending}
        while pending:
            progressed = False
            for t in list(pending):
                if any(d in in_mo and d not in placed for d in t.deps):
                    continue
                earliest = max([now, free_at[t.wc_id]] + [placed[d]['end'] for d in t.deps if d in placed])
                start, end = _first_clear(worktime, t.wc_id, earliest, t.minutes, blocks[t.wc_id])
                record(t, start, end)
                free_at[t.wc_id] = end
                pending.remove(t)
                progressed = True
            if not progressed:
                raise UserError(_(
                    "Workorder dependencies of a manufacturing order form a loop. "
                    "Remove the circular dependency and schedule again."))
    return placed


# ----------------------------------------------------------------------
# Working time from resource.calendar
# ----------------------------------------------------------------------
class CalendarWorkTime:
    """Working intervals of a workcenter: attendances minus global holidays.

    Leaves bound to the workcenter resource are ignored on purpose: those are
    the leaves Odoo creates when workorders are planned, and this scheduler
    owns the queue itself.
    """

    def __init__(self, env):
        self.env = env
        self._cache = {}
        self._wc = {}

    def _calendar(self, wc_id):
        if wc_id not in self._wc:
            wc = self.env['mrp.workcenter'].browse(wc_id)
            if not wc.resource_calendar_id:
                raise UserError(_(
                    "Workcenter %s has no working schedule. Set one on the workcenter and "
                    "schedule again.", wc.display_name))
            self._wc[wc_id] = wc.resource_calendar_id
        return self._wc[wc_id]

    def intervals(self, wc_id, start, end):
        cal = self._calendar(wc_id)
        key = (cal.id, start, end)
        if key not in self._cache:
            tz = pytz.timezone(cal.tz or 'UTC')
            res = cal._work_intervals_batch(  # pylint: disable=protected-access
                pytz.utc.localize(start), pytz.utc.localize(end), tz=tz)[False]
            self._cache[key] = [
                (a.astimezone(pytz.utc).replace(tzinfo=None), b.astimezone(pytz.utc).replace(tzinfo=None))
                for a, b, _meta in res]
        return self._cache[key]


# ----------------------------------------------------------------------
# Database side
# ----------------------------------------------------------------------
def _fix_progress_windows(progress, worktime, now):
    """Workorders in progress keep their workcenter, and their remaining work is
    queued from ``now`` one after another per workcenter (oldest start first).

    Their real start stays on the workorder (Apply never writes them). Drawing
    them from that start made jobs left "in progress" for months stack on top
    of each other (prod 2026-11: 5 such jobs since 2026-08-28).
    """
    def real_start(task_wo):
        starts = task_wo[1].time_ids.filtered('date_start').mapped('date_start')
        return min(starts) if starts else (task_wo[1].date_start or now)

    cursor = defaultdict(lambda: now)
    for task, wo in sorted(progress, key=lambda tw: (real_start(tw), tw[1].id)):
        wc_id = wo.workcenter_id.id
        task.fixed = consume(lambda a, b, wc_id=wc_id: worktime.intervals(wc_id, a, b),
                             cursor[wc_id], task.minutes)
        cursor[wc_id] = task.fixed[1]


def build_tasks(run, cfg, now, worktime):
    env = run.env
    domain = [
        ('state', 'in', OPEN_WO_STATES),
        ('production_id.state', 'in', ('confirmed', 'progress')),
        ('production_id.company_id', '=', run.company_id.id),
    ]
    if run.picking_type_ids:
        domain.append(('production_id.picking_type_id', 'in', run.picking_type_ids.ids))
    workorders = env['mrp.workorder'].search(domain)
    stats = {
        (r.operation_id.id, r.workcenter_id.id): (r.wo_count, r.actual_minutes_per_unit)
        for r in env['buz.plan.operation.time'].search([])}
    kept = {
        l.workorder_id.id: l for l in run.schedule_line_ids
        if (l.is_locked or l.is_manual) and l.workorder_id.state != 'progress'}

    mos = workorders.production_id
    far = datetime.max
    ranked = sorted(mos, key=lambda m: (
        m.date_deadline or far, -int(m.priority or 0), m.date_start or far, m.id))
    rank = {m.id: i for i, m in enumerate(ranked)}

    tasks, progress = [], []
    for mo in mos:
        wos = workorders.filtered(lambda w, mo=mo: w.production_id == mo).sorted(
            lambda w: (w.operation_id.sequence, w.operation_id.id, w.id))
        ids_in = set(wos.ids)
        previous = False
        for order, wo in enumerate(wos):
            if mo.allow_workorder_dependencies:
                deps = [d.id for d in wo.blocked_by_workorder_ids if d.id in ids_in]
            else:
                deps = [previous] if previous else []
            previous = wo.id
            minutes, source = estimate_minutes(
                wo.duration_expected, wo.qty_remaining or wo.qty_production,
                wo.duration if wo.state == 'progress' else 0.0,
                stats.get((wo.operation_id.id, wo.workcenter_id.id)),
                cfg['min_history_wo'], cfg['expected_factor'])
            task = Task(wo.id, mo.id, wo.workcenter_id.id, minutes, source,
                        rank[mo.id], order, deps, deadline=mo.date_deadline)
            if wo.state == 'progress':
                progress.append((task, wo))   # window set below, once all are known
                task.locked = True
            elif wo.id in kept:
                line = kept[wo.id]
                task.fixed = (line.date_start, line.date_end)
                task.locked, task.manual = line.is_locked, line.is_manual
                task.minutes, task.source = line.duration_minutes, line.duration_source
                task.line_id = line.id
            tasks.append(task)
    _fix_progress_windows(progress, worktime, now)
    return tasks


def run_schedule(run, cfg, now=None):
    """Schedule the open workorders of ``run``; returns a small statistics dict."""
    env = run.env
    now = now or fields.Datetime.now()
    worktime = CalendarWorkTime(env)
    tasks = build_tasks(run, cfg, now, worktime)
    placed = schedule(tasks, worktime, now)

    Line = env['buz.plan.schedule.line']
    keep_ids = {r['line_id'] for r in placed.values() if r['line_id']}
    run.schedule_line_ids.filtered(lambda l: l.id not in keep_ids).unlink()
    wos = env['mrp.workorder'].browse(list(placed))
    wo_by_id = {w.id: w for w in wos}
    task_by_wo = {t.wo_id: t for t in tasks}
    vals = []
    for wo_id, r in placed.items():
        if r['line_id']:
            Line.browse(r['line_id']).is_late = r['is_late']
            continue
        wo = wo_by_id[wo_id]
        vals.append({
            'run_id': run.id, 'workorder_id': wo_id, 'workcenter_id': wo.workcenter_id.id,
            'sequence': task_by_wo[wo_id].order, 'date_start': r['start'], 'date_end': r['end'],
            'duration_minutes': r['minutes'], 'duration_source': r['source'],
            'is_locked': r['is_locked'], 'is_late': r['is_late'], 'is_manual': False,
        })
    Line.create(vals)
    return {
        'workorders': len(placed), 'productions': len({t.mo_id for t in tasks}),
        'late': sum(1 for r in placed.values() if r['is_late']),
        'locked': sum(1 for r in placed.values() if r['fixed']),
    }


APPLY_BATCH_MOS = 50


def _eligible(line):
    return (line.state == 'proposed'
            and line.workorder_id.state in ('pending', 'waiting', 'ready')
            and line.production_id.state in ('confirmed', 'progress'))


def _has_done_moves(mo):
    """Odoo copies new MO dates onto every component / finished move, done ones
    included (mrp_production.write). Such an MO is never re-dated by Apply so
    stock history keeps its dates."""
    return any(m.state == 'done' for m in mo.move_raw_ids | mo.move_finished_ids)


def apply_lines(lines, limit=0):
    """Write the planned dates on the real workorders, ``limit`` MOs at a time.

    Returns ``(done, skipped, remaining_mos)``. Every call is resumable: lines
    already applied are not eligible any more, so calling again continues
    where the previous (possibly interrupted) call stopped.

    Behaviour of Odoo 17 that this relies on (read from source, not assumed):
    * writing both dates on a workorder recomputes ``date_finished`` from the
      expected duration unless ``bypass_duration_calculation`` is in the context;
    * the write creates / moves the workorder's ``resource.calendar.leaves``;
    * the first / last workorder write also rewrites the MO dates, so the MO is
      set once at the end with ``force_date`` (what Odoo's own planner does),
      which avoids the ``button_unplan`` path of a plain MO date write.
    * that MO write also rewrites ``stock.move.date`` of all its raw / finished
      moves, done ones included, so MOs with done moves are skipped entirely.
    State of workorders and MOs is never touched. Workorders in progress are skipped.
    """
    groups = _group_by_production(lines)
    skipped = lines.browse()
    todo_mos = []
    for mo, mo_lines in groups.items():
        if not any(_eligible(l) for l in mo_lines):
            continue
        if _has_done_moves(mo):
            skipped |= mo_lines
        else:
            todo_mos.append(mo)
    batch = todo_mos[:limit] if limit else todo_mos
    done = lines.browse()
    for mo in batch:
        mo_lines = groups[mo]
        todo = mo_lines.filtered(_eligible)
        skipped |= mo_lines - todo
        for line in todo:
            line.workorder_id.with_context(bypass_duration_calculation=True).write({
                'date_start': line.date_start, 'date_finished': line.date_end})
        dated = mo.workorder_ids.filtered(
            lambda w: w.state not in ('done', 'cancel') and w.date_start and w.date_finished)
        mo.with_context(force_date=True).write({
            'date_start': min(dated.mapped('date_start')),
            'date_finished': max(dated.mapped('date_finished')),
        })
        done |= todo
    done.write({'state': 'applied'})
    return done, skipped, len(todo_mos) - len(batch)


def _group_by_production(lines):
    out = {}
    for mo in lines.production_id.sorted('id'):
        out[mo] = lines.filtered(lambda l, mo=mo: l.production_id == mo)
    return out
