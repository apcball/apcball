# -*- coding: utf-8 -*-
"""Pure depreciation math. No ORM, no database access."""
import calendar
from datetime import date


def _first_of_month_plus(start_date, months):
    index = start_date.month - 1 + months
    return date(start_date.year + index // 12, index % 12 + 1, 1)


def _last_of_month(first_day):
    return date(first_day.year, first_day.month,
                calendar.monthrange(first_day.year, first_day.month)[1])


def compute_straight_line_schedule(depreciable_base, periods, start_date, round_fn):
    """Return monthly straight-line rows using the full-month convention.

    Period 1 is the calendar month containing ``start_date`` (no proration).
    Each row's accounting date is the last day of its month. Every period
    except the last gets ``round_fn(base / periods)``; the last period takes
    the remainder, so the total never exceeds the base.

    :param depreciable_base: gross cost minus residual value
    :param periods: number of monthly periods (> 0)
    :param start_date: ``date`` the asset starts depreciating
    :param round_fn: currency rounding callable (``currency.round``)
    :return: list of dicts with sequence, period_start, period_end,
             depreciation_date, amount, remaining_after
    """
    if periods <= 0:
        raise ValueError("periods must be greater than zero")
    if depreciable_base <= 0:
        return []

    regular = round_fn(depreciable_base / periods)
    accumulated = 0.0
    rows = []
    for index in range(periods):
        first_day = _first_of_month_plus(start_date, index)
        last_day = _last_of_month(first_day)
        remaining_before = round_fn(depreciable_base - accumulated)
        if index == periods - 1:
            amount = remaining_before
        else:
            amount = min(regular, remaining_before)
        accumulated = round_fn(accumulated + amount)
        rows.append({
            'sequence': index + 1,
            'period_start': first_day,
            'period_end': last_day,
            'depreciation_date': last_day,
            'amount': amount,
            'remaining_after': round_fn(depreciable_base - accumulated),
        })
    return rows
