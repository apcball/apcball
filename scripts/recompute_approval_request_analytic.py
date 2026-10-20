# -*- coding: utf-8 -*-
"""Recompute amount_analytic / amount_overage of
buz.monthly.budget.approval.request after the "x N accounts" fix
(biz_monthly_analytic_budget 2e10376b).

Default is a DRY RUN (APPLY = False): read-only, ends with a rollback.
Run inside an Odoo shell, stdout only:

    ssh mog-prod "cd /opt/instance1/odoo17 && source /opt/instance1/odoo17-venv/bin/activate && \
      python3 odoo-bin shell -c /etc/instance1.conf -d MOG_LIVE --no-http" \
      < scripts/recompute_approval_request_analytic.py | grep -E '^(ROW|SUM)'

APPLY (only after a reviewed dry run and a fresh pg_dump of MOG_LIVE):

    sed 's/^APPLY = False/APPLY = True/' scripts/recompute_approval_request_analytic.py | ssh mog-prod ...
  (add  -e 's/^REHEARSE = False/REHEARSE = True/'  to run every step and roll back)

  * copies id / amount_analytic / amount_overage to bk_ar_analytic_YYYYMMDD first
  * plain SQL UPDATE of those two columns only, one row at a time, guarded by the
    value read in this run (rowcount must be 1); any mismatch -> rollback, abort
  * no ORM write: no chatter, no state change, no auto-approve, no plan refresh
  * rollback:  UPDATE buz_monthly_budget_approval_request r
               SET amount_analytic = b.amount_analytic, amount_overage = b.amount_overage
               FROM bk_ar_analytic_YYYYMMDD b WHERE b.id = r.id;

Rule (same as the fixed _prepare_amounts_from_source_document, but keeping the
used / reserved / limit snapshot stored on the request):
  * covered accounts = analytic accounts with a budget line in the request's plan
    (and sibling plans of the same company + period, for multi-plan documents)
  * new amount_analytic = covered amount of the source document lines
      - 'exact' when the all-accounts sum still equals the stored value
      - 'ratio' when the document changed since (stored * covered / all)
  * new amount_overage = max(0, used + reserved + new_analytic - limit) for PR /
    bill; PO overage never included amount_analytic -> left unchanged
State, chatter and plan snapshots are never touched.
"""
from collections import Counter

from odoo.addons.biz_monthly_analytic_budget.models.budget_utils import (
    extract_analytic_amounts,
)

env = env(su=True)  # noqa: F821 - provided by `odoo-bin shell`
Req = env['buz.monthly.budget.approval.request']
Plan = env['monthly.budget.plan']
BudgetLine = env['monthly.budget.line']
EPS = 0.01
APPLY = False  # flipped by sed for the real run
REHEARSE = False  # with APPLY: run every step, then roll back instead of commit

_covered_cache = {}


def covered_accounts(plan):
    if plan.id not in _covered_cache:
        siblings = Plan.search([
            ('company_id', '=', plan.company_id.id),
            ('date_from', '=', plan.date_from),
            ('date_to', '=', plan.date_to),
            ('state', 'in', ('confirmed', 'closed')),
        ]) | plan
        _covered_cache[plan.id] = set(siblings.mapped('budget_line_ids.analytic_account_id').ids)
    return _covered_cache[plan.id]


def source_lines(req):
    if req.document_type == 'pr':
        return req.ref_pr_id.requisition_order_ids, False
    if req.document_type == 'po':
        return req.ref_po_id.order_line, False
    if req.document_type == 'bill':
        return req.ref_bill_id.invoice_line_ids, True
    return Req.browse(), False


rows = []
for req in Req.search([], order='id'):
    lines, with_budget_model = source_lines(req)
    old_an, old_ov = req.amount_analytic, req.amount_overage
    new_an, new_ov, method = old_an, old_ov, ''
    if not lines:
        method = 'skip_no_doc'
    elif not req.plan_id:
        method = 'skip_no_plan'
    else:
        covered = covered_accounts(req.plan_id)
        all_sum = covered_sum = 0.0
        for line in lines:
            pairs = (extract_analytic_amounts(line, BudgetLine) if with_budget_model
                     else extract_analytic_amounts(line))
            for account_id, amount in pairs:
                all_sum += amount
                if account_id in covered:
                    covered_sum += amount
        if all_sum <= 0:
            method = 'skip_no_analytic'
        elif abs(all_sum - old_an) <= EPS:
            new_an, method = covered_sum, 'exact'
        else:
            new_an, method = old_an * covered_sum / all_sum, 'ratio'
        if req.document_type != 'po' and method in ('exact', 'ratio'):
            new_ov = max(0.0, req.amount_used + req.amount_reserved + new_an - req.amount_limit)
    # does the stored overage follow the formula? (PR / bill only)
    ov_formula_ok = ''
    if req.document_type != 'po':
        ov_formula_ok = abs(max(0.0, req.amount_used + req.amount_reserved + old_an
                                - req.amount_limit) - old_ov) <= EPS
    rows.append(dict(
        id=req.id, name=req.name, type=req.document_type, state=req.state,
        plan=req.plan_id.name or '', plan_state=req.plan_id.state or '',
        requested=req.amount_requested, old_an=old_an, new_an=new_an, method=method,
        old_ov=old_ov, new_ov=new_ov, ov_formula_ok=ov_formula_ok,
    ))

print('ROW|id|name|type|state|plan|plan_state|requested|old_analytic|new_analytic|method|old_overage|new_overage|ov_formula_ok')
for r in rows:
    print('ROW|%(id)s|%(name)s|%(type)s|%(state)s|%(plan)s|%(plan_state)s|%(requested).2f|%(old_an).2f|%(new_an).2f|'
          '%(method)s|%(old_ov).2f|%(new_ov).2f|%(ov_formula_ok)s' % r)

changed = [r for r in rows if abs(r['new_an'] - r['old_an']) > EPS or abs(r['new_ov'] - r['old_ov']) > EPS]
print('SUM requests', len(rows), 'to_change', len(changed))
print('SUM by method', dict(Counter(r['method'] for r in rows)))
print('SUM by type/state', dict(Counter((r['type'], r['state']) for r in rows)))
print('SUM analytic old/new %.2f / %.2f' % (sum(r['old_an'] for r in rows), sum(r['new_an'] for r in rows)))
print('SUM overage old/new %.2f / %.2f' % (sum(r['old_ov'] for r in rows), sum(r['new_ov'] for r in rows)))
print('SUM new_analytic/requested ratio', dict(Counter(
    round(r['new_an'] / r['requested'], 2) for r in rows if r['requested'] and r['method'] in ('exact', 'ratio')).most_common(8)))
flip = [r for r in rows if r['old_ov'] > EPS and r['new_ov'] <= EPS]
print('SUM overage >0 -> 0:', len(flip), dict(Counter(r['state'] for r in flip)))
print('SUM pending flipped:', [r['name'] for r in flip if r['state'] == 'pending'])
print('SUM ov_formula mismatch (PR/bill):', len([r for r in rows if r['ov_formula_ok'] is False]))
print('SUM plan_state of changed:', dict(Counter(r['plan_state'] for r in changed)))

if not APPLY:
    env.cr.rollback()  # belt and braces: nothing was written
    print('SUM mode DRY RUN (rolled back)')
else:
    import datetime
    cr = env.cr
    table = 'buz_monthly_budget_approval_request'
    backup = 'bk_ar_analytic_%s' % datetime.date.today().strftime('%Y%m%d')
    cr.execute('SELECT 1 FROM information_schema.tables WHERE table_name = %s', (backup,))
    if cr.fetchone():
        raise SystemExit('backup table %s already exists - aborting' % backup)
    cr.execute('SELECT md5(string_agg(id::text || state, \',\' ORDER BY id)) FROM ' + table)
    states_before = cr.fetchone()[0]
    cr.execute('CREATE TABLE %s AS SELECT id, amount_analytic, amount_overage FROM %s' % (backup, table))
    updated = 0
    for r in changed:
        cr.execute(
            'UPDATE ' + table + ' SET amount_analytic = %s, amount_overage = %s '
            'WHERE id = %s AND amount_analytic = %s AND amount_overage = %s',
            (r['new_an'], r['new_ov'], r['id'], r['old_an'], r['old_ov']))
        if cr.rowcount != 1:
            cr.rollback()
            raise SystemExit('guard failed on request %s (rowcount %s) - rolled back' % (r['id'], cr.rowcount))
        updated += 1
    cr.execute('SELECT md5(string_agg(id::text || state, \',\' ORDER BY id)) FROM ' + table)
    if cr.fetchone()[0] != states_before:
        cr.rollback()
        raise SystemExit('state checksum changed - rolled back')
    if REHEARSE:
        cr.rollback()
        print('SUM mode REHEARSAL (rolled back): would update %s rows, backup table %s' % (updated, backup))
    else:
        cr.commit()
        print('SUM mode APPLIED: updated %s rows, backup table %s' % (updated, backup))
