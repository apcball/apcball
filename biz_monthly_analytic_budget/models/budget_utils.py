# -*- coding: utf-8 -*-
"""
Shared utility functions for biz_monthly_analytic_budget.

Centralizes common logic used by both purchase_requisition.py and purchase_order.py
to avoid code duplication (DRY principle).
"""
import json
import logging
from decimal import Decimal
from odoo import _

_logger = logging.getLogger(__name__)

RESERVED_PR_STATES = ('waiting_purchase_approval', 'approved', 'purchase_order_created', 'received')


def find_active_monthly_plans(env, target_date, company_id):
    """Return ALL confirmed monthly budget plans that cover target_date for the company.

    Use this when the caller needs to route analytics across multiple plans
    (one analytic → one plan, no overlap within a month).

    :param env: Odoo environment
    :param target_date: date to match against plan period
    :param company_id: int company id
    :returns: monthly.budget.plan recordset (may be empty, single, or multiple)
    """
    if not target_date:
        return env['monthly.budget.plan']
    domain = [
        ('state', '=', 'confirmed'),
        ('date_from', '<=', target_date),
        ('date_to', '>=', target_date),
        ('company_id', '=', company_id),
    ]
    return env['monthly.budget.plan'].sudo().search(domain)


def find_active_monthly_plan(env, target_date, company_id, analytic_account_ids=None):
    """Find the best-matching confirmed monthly budget plan for target_date.

    When multiple confirmed plans exist for the same month (multi-plan scenario),
    the plan whose budget lines contain the most overlap with *analytic_account_ids*
    is preferred.  If *analytic_account_ids* is not supplied (or all plans tie),
    the first plan in model order (year desc, month desc, id desc) is returned,
    preserving backward-compatible behaviour.

    :param env: Odoo environment
    :param target_date: date to match against plan period
    :param company_id: int company id
    :param analytic_account_ids: optional collection of analytic account IDs
        (int) present on the document lines — used to pick the correct plan
        when several confirmed plans share the same month.
    :returns: monthly.budget.plan recordset (single or empty)
    """
    plans = find_active_monthly_plans(env, target_date, company_id)
    if not plans:
        return env['monthly.budget.plan']
    if len(plans) == 1:
        return plans

    # Multiple plans found for this month — pick the one that covers the analytics.
    if analytic_account_ids:
        analytic_ids_set = set(int(a) for a in analytic_account_ids if a)
        best_plan = plans[:1]
        best_coverage = -1
        for plan in plans:
            plan_analytics = set(plan.budget_line_ids.mapped('analytic_account_id').ids)
            coverage = len(analytic_ids_set & plan_analytics)
            if coverage > best_coverage:
                best_coverage = coverage
                best_plan = plan
        _logger.debug(
            'find_active_monthly_plan: %d plans found for %s company=%s; '
            'selected plan=%s (coverage=%d/%d analytics)',
            len(plans), target_date, company_id,
            best_plan.name, best_coverage, len(analytic_ids_set),
        )
        return best_plan

    # No analytics hint → fall back to first plan (original behaviour)
    _logger.debug(
        'find_active_monthly_plan: %d plans for %s company=%s, no analytic hint — '
        'using first plan: %s',
        len(plans), target_date, company_id, plans[0].name,
    )
    return plans[:1]


def find_plan_for_analytics(env, target_date, company_id, analytic_account_ids):
    """Resolve a set of analytic account IDs to their specific confirmed plan.

    In the multi-plan scenario each analytic belongs to exactly one plan per
    month (enforced by the _check_no_analytic_overlap constraint on
    monthly.budget.plan).  This helper builds a mapping
    ``{plan_id: {account_id: ...}}`` so callers can process analytics in
    per-plan buckets.

    :param env: Odoo environment
    :param target_date: date to match against plan period
    :param company_id: int company id
    :param analytic_account_ids: iterable of analytic account IDs (int)
    :returns: dict  { monthly.budget.plan record : set of analytic_account_id (int) }
             Analytics that belong to no plan are placed under the key ``None``.
    """
    plans = find_active_monthly_plans(env, target_date, company_id)
    analytic_ids = set(int(a) for a in analytic_account_ids if a)

    if not plans:
        return {None: analytic_ids} if analytic_ids else {}

    result = {}  # plan → set of account_ids
    unassigned = set(analytic_ids)

    for plan in plans:
        plan_analytics = set(plan.budget_line_ids.mapped('analytic_account_id').ids)
        matched = unassigned & plan_analytics
        if matched:
            result[plan] = matched
            unassigned -= matched

    if unassigned:
        result[None] = unassigned  # analytics not covered by any plan

    return result


def extract_analytic_amounts(line, budget_line_model=None):
    """
    Extract analytic account allocations from a line record.

    Works with both purchase.requisition.order lines and purchase.order.line
    by reading the standard Odoo 17 ``analytic_distribution`` JSON field.
    Normalizes distribution using Decimal for financial precision when
    budget_line_model is provided.

    :param line: a record with analytic_distribution and price_subtotal fields
    :param budget_line_model: optional monthly.budget.line model for Decimal precision
    :returns: list of (analytic_account_id (int), allocated_amount (float))
    """
    distribution = line.analytic_distribution
    _logger.debug("budget_utils PR line %s analytic_distribution=%r price_subtotal=%r", getattr(line, 'id', None), distribution, line.price_subtotal)
    if not distribution:
        return []

    if isinstance(distribution, str):
        try:
            distribution = json.loads(distribution)
        except json.JSONDecodeError:
            return []

    if not isinstance(distribution, dict) or not distribution:
        return []

    subtotal = line.price_subtotal or 0.0

    # Normalize using Decimal for precision (via budget line helper if available)
    if budget_line_model:
        try:
            dist_amounts = budget_line_model._compute_distribution_amount(subtotal, distribution)
            result = []
            for acc_id_str_group, amount in dist_amounts.items():
                amt = float(amount)
                for acc_id_str in acc_id_str_group.split(','):
                    try:
                        account_id = int(acc_id_str.strip())
                        result.append((account_id, amt))
                    except (ValueError, TypeError):
                        continue
            return result
        except Exception:
            pass  # fall through to legacy method

    # Fallback: legacy float computation
    result = []
    for acc_id_str_group, pct in distribution.items():
        allocated = subtotal * (pct or 0.0) / 100.0
        for acc_id_str in acc_id_str_group.split(','):
            try:
                account_id = int(acc_id_str.strip())
                result.append((account_id, allocated))
            except (ValueError, TypeError):
                continue
    return result


def filter_analytic_totals_for_plan(plan, analytic_totals):
    """
    Keep only analytic accounts that are configured on the given budget plan.

    If the plan does not yet have any budget lines, the totals are returned as-is
    so the normal "missing budget line" validation still applies.
    """
    if not plan or not analytic_totals:
        return analytic_totals, {}

    allowed_ids = set(plan.budget_line_ids.mapped('analytic_account_id').ids)
    if not allowed_ids:
        return analytic_totals, {}

    filtered_totals = {}
    ignored_totals = {}
    for account_id, amount in analytic_totals.items():
        if account_id in allowed_ids:
            filtered_totals[account_id] = amount
        else:
            ignored_totals[account_id] = amount

    return filtered_totals, ignored_totals


def split_analytic_totals_by_plan(env, target_date, company_id, analytic_totals):
    """Split analytic totals into per-plan buckets for multi-plan processing.

    :returns: tuple ``(grouped_totals, ignored_totals)``
      - grouped_totals: list of ``(plan, {analytic_id: amount})``
      - ignored_totals: ``{analytic_id: amount}`` not covered by any active plan
    """
    if not analytic_totals:
        return [], {}

    plan_map = find_plan_for_analytics(
        env, target_date, company_id, analytic_totals.keys()
    )
    grouped_totals = []
    ignored_totals = {}

    for plan, analytic_ids in plan_map.items():
        plan_totals = {
            account_id: analytic_totals[account_id]
            for account_id in analytic_ids
            if account_id in analytic_totals
        }
        if not plan_totals:
            continue
        if plan:
            grouped_totals.append((plan, plan_totals))
        else:
            ignored_totals.update(plan_totals)

    return grouped_totals, ignored_totals


def get_first_plan_from_groups(grouped_totals):
    """Return the first plan from grouped totals for backwards-compatible fields."""
    for plan, _totals in grouped_totals:
        return plan
    return False


def collect_analytic_ids_from_lines(lines):
    """Return the set of analytic account IDs (int) referenced by *lines*.

    Lines must carry an ``analytic_distribution`` field (standard Odoo 17 widget).
    This is a lightweight scan — it does NOT compute amounts, just IDs.

    :param lines: recordset of document lines (PO lines, PR order lines, bill lines…)
    :returns: set of int analytic account IDs
    """
    result = set()
    for line in lines:
        distribution = line.analytic_distribution
        if not distribution:
            continue
        if isinstance(distribution, str):
            try:
                import json as _json
                distribution = _json.loads(distribution)
            except Exception:
                continue
        if not isinstance(distribution, dict):
            continue
        for key in distribution:
            for part in str(key).split(','):
                try:
                    result.add(int(part.strip()))
                except (ValueError, TypeError):
                    pass
    return result


def format_ignored_analytic_accounts_message(ignored_names):
    """Return the standard message for analytics excluded from plan checks."""
    return _(
        'Analytic accounts not configured in this plan were ignored: %s'
    ) % ignored_names


def format_no_analytic_distribution_message():
    """Return the standard message for documents without analytic totals."""
    return _('No analytic distribution found on document lines.')


def format_missing_budget_line_message(analytic_name, plan_name):
    """Return the standard message for a missing monthly budget line."""
    return _(
        'No monthly budget line found for analytic account "%s".\n'
        'Please add it to the monthly budget plan "%s" first.'
    ) % (analytic_name, plan_name)
