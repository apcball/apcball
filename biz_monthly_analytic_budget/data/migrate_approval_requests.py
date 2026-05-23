#!/usr/bin/env python3
"""
Migration Script: Recalculate all PR-linked Monthly Budget Approval Requests.

อ่านยอดจาก PR ที่ link อยู่ แล้วคำนวณ amount_requested, amount_analytic,
amount_limit, amount_used, amount_reserved, amount_overage ใหม่ทั้งหมด
ตรงตาม budget line จริงตอน run script

วิธีรัน:
  docker exec -i odoo python3 /mnt/extra-addons/biz_monthly_analytic_budget/data/migrate_approval_requests.py
"""

import os
import sys
import logging

os.environ['ODOO_SKIP_MODULE_WARNINGS'] = '1'

from odoo import api, SUPERUSER_ID, registry, _
from odoo.tools import float_round

_logger = logging.getLogger(__name__)

DB = 'MOG_DEV'

def main():
    with registry(DB).cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {})

        ApprovalReq = env['buz.monthly.budget.approval.request']
        BudgetLine = env['monthly.budget.line']
        AnalyticAccount = env['account.analytic.account']

        # ── 1. All PR-linked approval requests ──
        pr_requests = ApprovalReq.search([
            ('document_type', '=', 'pr'),
            ('ref_pr_id', '!=', False),
        ])

        import importlib.util
        _budget_utils_path = '/mnt/custom-addons/biz_monthly_analytic_budget/models/budget_utils.py'
        _budget_utils_spec = importlib.util.spec_from_file_location('budget_utils_migrate', _budget_utils_path)
        _budget_utils_mod = importlib.util.module_from_spec(_budget_utils_spec)
        _budget_utils_spec.loader.exec_module(_budget_utils_mod)
        extract_analytic_amounts = _budget_utils_mod.extract_analytic_amounts
        split_analytic_totals_by_plan = _budget_utils_mod.split_analytic_totals_by_plan
        get_first_plan_from_groups = _budget_utils_mod.get_first_plan_from_groups

        updated = []

        for req in pr_requests:
            pr = req.ref_pr_id
            if not pr.exists():
                sys.stdout.write(f'SKIP  {req.name:<18} PR ID={req.ref_pr_id.id} no longer exists\n')
                continue

            target_date = pr.payment_date
            if not target_date:
                sys.stdout.write(f'SKIP  {req.name:<18} PR={pr.name} no payment_date\n')
                continue

            # ── Build analytic totals from current PR lines ──
            analytic_totals = {}
            for line in pr.requisition_order_ids:
                for account_id, amount in extract_analytic_amounts(line):
                    analytic_totals[account_id] = analytic_totals.get(account_id, 0.0) + amount

            grouped_totals, _ignored_totals = split_analytic_totals_by_plan(
                env, target_date, pr.company_id.id, analytic_totals,
            )
            if not grouped_totals:
                sys.stdout.write(f'SKIP  {req.name:<18} PR={pr.name} no budget plan found\n')
                continue

            # ── Calculate amounts ──
            pr_amount = sum(pr.requisition_order_ids.mapped('price_subtotal'))
            analytic_amount = sum(analytic_totals.values())

            limit_amt = 0.0
            used = 0.0
            reserved = 0.0
            budget_line_names = []
            plan_ids = set()

            for plan, plan_totals in grouped_totals:
                plan_ids.add(plan.id)
                for account_id, amt in plan_totals.items():
                    analytic = AnalyticAccount.browse(account_id)
                    if not analytic.exists():
                        continue
                    bl = BudgetLine._find_budget_line(
                        plan, {'analytic_account_id': account_id}, log_fallback=False
                    )
                    if bl:
                        limit_amt += bl.budget_amount
                        used += bl.used_amount
                        reserved += bl.reserved_amount
                        budget_line_names.append('%s (%s)' % (bl.analytic_account_id.name, plan.name))

            overage = max(0.0, used + reserved + analytic_amount - limit_amt)
            primary_plan = get_first_plan_from_groups(grouped_totals)
            budget_line_name_str = ', '.join(budget_line_names) or req.budget_line_name or ''

            # ── Check if anything changed ──
            changes = {}
            test_vals = {
                'amount_requested': pr_amount,
                'amount_analytic': analytic_amount,
                'amount_limit': limit_amt,
                'amount_used': used,
                'amount_reserved': reserved,
                'amount_overage': overage,
            }
            for fld, new_val in test_vals.items():
                old_val = req[fld]
                if abs(old_val - new_val) > 0.01:
                    changes[fld] = (old_val, new_val)

            if req.budget_line_name != budget_line_name_str:
                changes['budget_line_name'] = (req.budget_line_name, budget_line_name_str)

            old_plan = req.plan_id
            new_plan = primary_plan or old_plan
            if old_plan.id != new_plan.id:
                changes['plan_id'] = (old_plan.name if old_plan else '-', new_plan.name if new_plan else '-')

            if not changes:
                sys.stdout.write(f'SAME  {req.name:<18} PR={pr.name:<20} no changes needed\n')
                continue

            # ── Apply changes ──
            write_vals = {}
            for fld, (old, new) in changes.items():
                write_vals[fld] = new

            req.write(write_vals)

            sys.stdout.write(
                f'FIX   {req.name:<18} PR={pr.name:<20} {len(changes)} field(s): '
            )
            parts = []
            for fld, (old, new) in changes.items():
                if isinstance(old, float):
                    parts.append(f'{fld} {old:,.2f}→{new:,.2f}')
                else:
                    parts.append(f'{fld} {old!r}→{new!r}')
            sys.stdout.write(', '.join(parts) + '\n')
            updated.append(req.id)

        # ── 2. Bill-linked requests ──
        bill_requests = ApprovalReq.search([
            ('document_type', '=', 'bill'),
            ('ref_bill_id', '!=', False),
        ])
        for req in bill_requests:
            bill = req.ref_bill_id
            if not bill.exists():
                sys.stdout.write(f'SKIP  {req.name:<18} Bill ID={req.ref_bill_id.id} no longer exists\n')
                continue

            target_date = bill.invoice_date_due or bill.date or bill.invoice_date
            if not target_date:
                sys.stdout.write(f'SKIP  {req.name:<18} Bill={bill.name} no date\n')
                continue

            analytic_totals = {}
            for line in bill.invoice_line_ids:
                for account_id, amount in extract_analytic_amounts(line):
                    analytic_totals[account_id] = analytic_totals.get(account_id, 0.0) + amount

            grouped_totals, _ignored_totals = split_analytic_totals_by_plan(
                env, target_date, bill.company_id.id, analytic_totals,
            )
            if not grouped_totals:
                sys.stdout.write(f'SKIP  {req.name:<18} Bill={bill.name} no plan\n')
                continue

            bill_amount = bill.amount_untaxed if hasattr(bill, 'amount_untaxed') else sum(bill.invoice_line_ids.mapped('price_subtotal'))
            analytic_amount = sum(analytic_totals.values())
            limit_amt = 0.0
            used = 0.0
            reserved = 0.0
            budget_line_names = []
            for plan, plan_totals in grouped_totals:
                for account_id, amt in plan_totals.items():
                    analytic = AnalyticAccount.browse(account_id)
                    if not analytic.exists():
                        continue
                    bl = BudgetLine._find_budget_line(plan, {'analytic_account_id': account_id}, log_fallback=False)
                    if bl:
                        limit_amt += bl.budget_amount
                        used += bl.used_amount
                        reserved += bl.reserved_amount
                        budget_line_names.append('%s (%s)' % (bl.analytic_account_id.name, plan.name))

            overage = max(0.0, used + reserved + analytic_amount - limit_amt)
            primary_plan = get_first_plan_from_groups(grouped_totals)

            changes = {}
            test_vals = {
                'amount_requested': bill_amount,
                'amount_analytic': analytic_amount,
                'amount_limit': limit_amt,
                'amount_used': used,
                'amount_reserved': reserved,
                'amount_overage': overage,
            }
            for fld, new_val in test_vals.items():
                old_val = req[fld]
                if abs(old_val - new_val) > 0.01:
                    changes[fld] = (old_val, new_val)

            bl_name_str = ', '.join(budget_line_names)
            if req.budget_line_name != bl_name_str:
                changes['budget_line_name'] = (req.budget_line_name, bl_name_str)

            old_plan = req.plan_id
            new_plan = primary_plan or old_plan
            if old_plan.id != new_plan.id:
                changes['plan_id'] = (old_plan.name if old_plan else '-', new_plan.name if new_plan else '-')

            if not changes:
                sys.stdout.write(f'SAME  {req.name:<18} Bill={bill.name:<20} no changes\n')
                continue

            write_vals = {fld: new for fld, (old, new) in changes.items()}
            req.write(write_vals)
            parts = [f'{fld} {old!r}→{new!r}' for fld, (old, new) in changes.items()]
            sys.stdout.write(f'FIX   {req.name:<18} Bill={bill.name:<20} {", ".join(parts)}\n')
            updated.append(req.id)

        cr.commit()

        sys.stdout.write(f'\n{"="*60}\n')
        sys.stdout.write(f'Total records updated: {len(updated)}\n')
        sys.stdout.write(f'{"="*60}\n')


if __name__ == '__main__':
    main()