# -*- coding: utf-8 -*-
"""Running-balance arithmetic for the backdate check. No Odoo imports."""


def find_negative_balance(current_qty, other_events, moved_events, new_date,
                          rounding):
    """Would re-dating ``moved_events`` to ``new_date`` drive stock negative?

    The history is rebuilt backwards from the current on-hand quantity, so the
    balance at time t is ``current_qty`` minus everything dated after t.
    Events sharing a timestamp are netted together.

    :param current_qty: on-hand quantity today
    :param other_events: ``[(date, signed_qty)]`` of done moves that are not
        being re-dated; must contain every one dated after the earliest of
        ``new_date`` and the moved dates
    :param moved_events: ``[(old_date, signed_qty)]`` being re-dated
    :param new_date: the date they all move to
    :param rounding: UoM rounding of the quantities
    :return: ``None``, or ``(date, new_balance, old_balance)`` for the lowest
        point that is negative *and* lower than before the change. Balances
        that are already negative and not made worse are ignored.
    """
    if not moved_events:
        return None
    dates = [date for date, _qty in moved_events] + [new_date]
    low, high = min(dates), max(dates)
    if low == high:
        return None

    tolerance = rounding / 2.0
    events = sorted(
        list(other_events) + list(moved_events),
        key=lambda event: event[0], reverse=True)
    # Outside [low, high) the change cancels out, so only these points can move.
    points = {date for date, _qty in events if low <= date < high}
    if new_date < high:
        points.add(new_date)

    moved_total = sum(qty for _date, qty in moved_events)
    worst = None
    later_total = 0.0
    index = 0
    for point in sorted(points, reverse=True):
        while index < len(events) and events[index][0] > point:
            later_total += events[index][1]
            index += 1
        before = current_qty - later_total
        change = (moved_total if new_date <= point else 0.0) - sum(
            qty for date, qty in moved_events if date <= point)
        after = before + change
        if after < -tolerance and change < -tolerance:
            # <= keeps the earliest date among equally low points.
            if worst is None or after <= worst[1] + tolerance:
                worst = (point, after, before)
    return worst
