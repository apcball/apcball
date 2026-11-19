# Recompute reserved PR commitments whose PR already has confirmed PO(s).
#
# Once a PO of a PR is confirmed, the PR commitment must hold the still-UNBILLED amount of
# its confirmed POs. Two bugs (fixed in biz_monthly_analytic_budget, commit 3c0338a4) left it
# at the full PR amount (PR edit / payment_date sync re-reserve) or at the amount of only
# the last PO (PR with several POs). This replays the fixed PO._consume_monthly_analytic_budget
# once per affected PR; it rewrites amount / date of the existing commitment and may create
# one for an analytic that had none (printed as NEW).
#
# Run through the Odoo shell, MODE=dry (default, always rolls back) or MODE=apply (commits):
#   MODE=dry python3 odoo-bin shell -c /etc/instance1.conf -d MOG_LIVE --no-http < this_file
# Needs the fixed code on disk (the shell loads it without a service restart).
# Output lines are prefixed PRC| so they can be grepped out of the Odoo log noise.
import os

MODE = os.environ.get('MODE', 'dry')
TOL = 0.005

Commitment = env['budget.commitment'].sudo()
PR = env['employee.purchase.requisition'].sudo()
Report = env['monthly.budget.report']

# one MV refresh at the end instead of one per PR (each consume refreshes it)
_orig_refresh = type(Report).refresh_materialized_view
type(Report).refresh_materialized_view = lambda self: None

before_all = Commitment.search([
    ('budget_source', '=', 'monthly'),
    ('document_model', '=', 'employee.purchase.requisition'),
    ('state', '=', 'reserved'),
])
prs = PR.browse(sorted(set(before_all.mapped('document_id')))).exists()
print('PRC|mode=%s reserved_pr_commitments=%d prs=%d' % (MODE, len(before_all), len(prs)))


def snapshot(pr):
    return {c.id: (c.amount, c.date, c.analytic_account_id.id) for c in Commitment.search([
        ('budget_source', '=', 'monthly'),
        ('document_model', '=', 'employee.purchase.requisition'),
        ('document_id', '=', pr.id),
        ('state', '=', 'reserved'),
    ])}


changed, errors, no_po = [], [], 0
for pr in prs.sorted('id'):
    pos = pr._get_linked_confirmed_pos()
    if not pos:
        no_po += 1
        continue
    before = snapshot(pr)
    try:
        with env.cr.savepoint():
            pos[:1]._consume_monthly_analytic_budget()
    except Exception as exc:  # keep going: report and leave this PR as it was
        errors.append((pr.name, str(exc)[:120]))
        env.invalidate_all()
        continue
    after = snapshot(pr)
    for cid, (amount, date, an) in after.items():
        if cid not in before:
            changed.append((pr.name, cid, an, 0.0, amount, None, date, 'NEW'))
            continue
        old_amount, old_date, _an = before[cid]
        if abs(old_amount - amount) > TOL or old_date != date:
            changed.append((pr.name, cid, an, old_amount, amount, old_date, date, 'FIX'))
    for cid, (old_amount, old_date, an) in before.items():
        if cid not in after:   # released by the replay (e.g. stale duplicate)
            changed.append((pr.name, cid, an, old_amount, 0.0, old_date, None, 'REL'))

for name, cid, an, old, new, old_date, new_date, kind in changed:
    print('PRC|%s|%-12s|id=%s|an=%s|%12.2f -> %12.2f|diff=%12.2f|%s -> %s' % (
        kind, name, cid, an, old, new, new - old, old_date, new_date))
for name, err in errors:
    print('PRC|ERROR|%s|%s' % (name, err))

net = sum(new - old for _n, _c, _a, old, new, _od, _nd, _k in changed)
by_month = {}
for _n, _c, _a, old, new, od, nd, _k in changed:
    key = str(od or nd)[:7]
    by_month[key] = by_month.get(key, 0.0) + (new - old)
print('PRC|SUMMARY prs=%d without_confirmed_po=%d changed_rows=%d errors=%d net_change=%.2f' % (
    len(prs), no_po, len(changed), len(errors), net))
print('PRC|SUMMARY net_by_commitment_month=%s' % {k: round(v, 2) for k, v in sorted(by_month.items())})
print('PRC|REVERT_DATA(id, old_amount, old_date; set state=reserved again for REL rows)=%s' % [
    (cid, old, str(od) if od else None, k) for _n, cid, _a, old, _new, od, _nd, k in changed if k in ('FIX', 'REL')])
print('PRC|NEW_IDS(to release on revert)=%s' % [cid for _n, cid, _a, _o, _nw, _od, _nd, k in changed if k == 'NEW'])

if MODE == 'apply' and changed:
    type(Report).refresh_materialized_view = _orig_refresh
    Report.refresh_materialized_view()
    env.cr.commit()
    print('PRC|APPLIED changed_rows=%d (materialized view refreshed once)' % len(changed))
else:
    env.cr.rollback()
    print('PRC|NO CHANGES WRITTEN (%s)' % ('dry mode' if MODE != 'apply' else 'nothing to change'))
