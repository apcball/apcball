# Fix monthly-budget commitments of vendor refunds (in_refund) booked with the wrong sign.
# Bug: price_subtotal is positive on refund lines, so credit notes consumed budget instead of
# giving it back. Code fix: account.move._get_monthly_bill_analytic_totals (negates refunds).
#
# Run through the Odoo shell, MODE=dry (default, always rolls back) or MODE=apply (commits):
#   MODE=dry python3 odoo-bin shell -c /etc/instance1.conf -d MOG_LIVE --no-http < this_file
# Output lines are prefixed RFX| so they can be grepped out of the Odoo log noise.
import os

MODE = os.environ.get('MODE', 'dry')
TOL = 0.005

Commitment = env['budget.commitment'].sudo()
Plan = env['monthly.budget.plan'].sudo()

commitments = Commitment.search([
    ('budget_source', '=', 'monthly'),
    ('document_model', '=', 'account.move'),
    ('state', 'in', ('reserved', 'used')),
])
moves = env['account.move'].sudo().browse(sorted(set(commitments.mapped('document_id')))).exists()
moves = moves.filtered(lambda m: m.move_type == 'in_refund')
print('RFX|mode=%s refunds_with_commitments=%d' % (MODE, len(moves)))

fixes = []      # (commitment, expected)
skipped = []    # (move, reason)
for move in moves.sorted('id'):
    expected = move._get_monthly_bill_analytic_totals()
    by_analytic = {}
    for c in commitments.filtered(lambda c, m=move: c.document_id == m.id):
        by_analytic.setdefault(c.analytic_account_id.id, []).append(c)
    for analytic_id, cs in by_analytic.items():
        if analytic_id not in expected:
            skipped.append((move, 'analytic %s no longer on bill' % analytic_id))
            continue
        if len(cs) > 1:
            skipped.append((move, 'analytic %s has %d commitments' % (analytic_id, len(cs))))
            continue
        c = cs[0]
        e = expected[analytic_id]
        status = 'OK' if abs(c.amount - e) <= TOL else 'FIX'
        print('RFX|%s|%-16s|%-6s|%s|an=%s|state=%s|cur=%12.2f|exp=%12.2f|diff=%12.2f' % (
            status, move.name, move.state, c.date, analytic_id, c.state, c.amount, e, e - c.amount))
        if status == 'FIX':
            fixes.append((c, e))

for move, reason in skipped:
    print('RFX|SKIP|%s|%s|%s' % (move.name, move.state, reason))

net = sum(e - c.amount for c, e in fixes)
print('RFX|SUMMARY fixes=%d skipped=%d net_change_in_used_and_reserved=%.2f' % (len(fixes), len(skipped), net))
by_state = {}
for c, e in fixes:
    by_state[c.state] = by_state.get(c.state, 0.0) + (e - c.amount)
print('RFX|SUMMARY by_state=%s' % {k: round(v, 2) for k, v in by_state.items()})

if MODE == 'apply' and fixes:
    plans = Plan
    for c, e in fixes:
        plan = Plan.search([
            ('company_id', '=', c.company_id.id), ('date_from', '<=', c.date), ('date_to', '>=', c.date),
            ('state', 'in', ('confirmed', 'closed')),
        ], limit=1)
        c.write({'amount': e})
        plans |= plan
    for plan in plans:
        plan._refresh_budget_snapshot(refresh_report=False)
    env['monthly.budget.report'].refresh_materialized_view()
    env.cr.commit()
    print('RFX|APPLIED fixes=%d plans_refreshed=%d' % (len(fixes), len(plans)))
    print('RFX|APPLIED_IDS=%s' % sorted(c.id for c, _e in fixes))
    print('RFX|REVERT: UPDATE budget_commitment SET amount = -amount WHERE id IN (%s);' % ','.join(str(c.id) for c, _e in sorted(fixes, key=lambda x: x[0].id)))
else:
    env.cr.rollback()
    print('RFX|NO CHANGES WRITTEN (%s)' % ('dry mode' if MODE != 'apply' else 'nothing to fix'))
