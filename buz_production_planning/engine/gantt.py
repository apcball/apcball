"""Server side of the Gantt client action: capacity, load and group labels."""
# pylint: disable=prefer-env-translation  # Odoo 17 has no env._ (that is Odoo 18 API)
from collections import defaultdict
from datetime import datetime, time, timedelta

import pytz

from odoo import _

GROUP_LABELS = {
    'PD1': "PD1 · Sanitaryware QC / assembly",
    'PD2': "PD2 · Furniture / stairs",
}


def wc_group(workcenter):
    """Workcenters carry no production line; the code prefix (PD1-xx, PD2-xx) is the grouping."""
    prefix = (workcenter.code or '').replace(' ', '').split('-')[0]
    if not prefix:
        return 'zz', _("Other")
    return prefix, GROUP_LABELS.get(prefix, prefix)


def split_by_day(start, end, tz):
    """Yield ``(YYYY-MM-DD, minutes)`` for a naive-UTC span cut at local midnights."""
    zone = pytz.timezone(tz)
    cur = pytz.utc.localize(start).astimezone(zone)
    stop = pytz.utc.localize(end).astimezone(zone)
    while cur < stop:
        midnight = zone.localize(datetime.combine(cur.date() + timedelta(days=1), time.min))
        seg_end = min(stop, midnight)
        yield cur.strftime('%Y-%m-%d'), (seg_end - cur).total_seconds() / 60.0
        cur = seg_end


def capacity_and_load(worktime, workcenters, lines, window_start, window_end, tz):
    """Working minutes available per workcenter/day and minutes already planned."""
    capacity, load = {}, {}
    lines_by_wc = defaultdict(list)
    for line in lines:
        lines_by_wc[line.workcenter_id.id].append(line)
    for wc in workcenters:
        work = worktime.intervals(wc.id, window_start, window_end)
        cap = defaultdict(float)
        for a, b in work:
            for day, minutes in split_by_day(a, b, tz):
                cap[day] += minutes
        used = defaultdict(float)
        for line in lines_by_wc.get(wc.id, ()):
            for a, b in work:
                lo, hi = max(a, line.date_start), min(b, line.date_end)
                if hi > lo:
                    for day, minutes in split_by_day(lo, hi, tz):
                        used[day] += minutes
        capacity[wc.id] = {d: round(m, 1) for d, m in cap.items()}
        load[wc.id] = {d: round(m, 1) for d, m in used.items()}
    return capacity, load
