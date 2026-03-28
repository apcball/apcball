# -*- coding: utf-8 -*-
"""
Shared utility functions for biz_monthly_analytic_budget.

Centralizes common logic used by both purchase_requisition.py and purchase_order.py
to avoid code duplication (DRY principle).
"""
import json
import logging
from decimal import Decimal

_logger = logging.getLogger(__name__)


def find_active_monthly_plan(env, target_date, company_id):
    """Find the confirmed monthly budget plan that covers target_date for the company.

    :param env: Odoo environment
    :param target_date: date to match against plan period
    :param company_id: int company id
    :returns: monthly.budget.plan recordset (single or empty)
    """
    if not target_date:
        return env['monthly.budget.plan']
    domain = [
        ('state', '=', 'confirmed'),
        ('date_from', '<=', target_date),
        ('date_to', '>=', target_date),
        ('company_id', '=', company_id),
    ]
    return env['monthly.budget.plan'].sudo().search(domain, limit=1)


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
    _logger.info("budget_utils PR line %s analytic_distribution=%r price_subtotal=%r", getattr(line, 'id', None), distribution, line.price_subtotal)
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
