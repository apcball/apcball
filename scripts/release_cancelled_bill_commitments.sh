#!/usr/bin/env bash
# Release stale monthly 'reserved'/'used' commitments on CANCELLED vendor bills (MOG_LIVE).
# Default = dry run (lists only). APPLY=1 backs up budget_commitment rows, then releases.
set -euo pipefail
APPLY="${APPLY:-0}"
ssh mog-prod "APPLY=$APPLY bash -s" <<'REMOTE'
set -euo pipefail
export PGPASSWORD=$(grep -E '^db_password' /etc/instance1.conf | cut -d= -f2 | tr -d ' ')
PSQL="psql -h localhost -U odoo MOG_LIVE"
SEL="select c.id from budget_commitment c join account_move m on m.id=c.document_id where c.budget_source='monthly' and c.document_model='account.move' and c.state in ('reserved','used') and m.state='cancel'"
$PSQL -c "select c.id,c.state,c.date,round(c.amount) amt,m.name from budget_commitment c join account_move m on m.id=c.document_id where c.id in ($SEL) order by c.date"
[ "$APPLY" = 1 ] || { echo "dry run only (APPLY=1 to apply)"; exit 0; }
B=/root/backup_budget_commitment_$(date +%Y%m%d_%H%M%S).sql
[ -w /root ] || B=/tmp/backup_budget_commitment_$(date +%Y%m%d_%H%M%S).sql
pg_dump -h localhost -U odoo MOG_LIVE -t budget_commitment > "$B"; echo "backup: $B"
cd /opt/instance1/odoo17 && source /opt/instance1/odoo17-venv/bin/activate
python3 odoo-bin shell -c /etc/instance1.conf -d MOG_LIVE --no-http 2>&1 <<'PYEOF'
C = env['budget.commitment'].sudo()
recs = C.search([('budget_source','=','monthly'),('document_model','=','account.move'),('state','in',('reserved','used'))])
recs = recs.filtered(lambda c: env['account.move'].browse(c.document_id).exists() and env['account.move'].browse(c.document_id).state == 'cancel')
print('releasing', len(recs), sum(recs.mapped('amount')))
plans = env['monthly.budget.line'].search([('analytic_account_id','in',recs.mapped('analytic_account_id').ids)]).mapped('plan_id').filtered(lambda p: p.date_from.year == 2026 and p.date_from.month == 10)
recs.action_release()
for p in plans: p._refresh_budget_snapshot(refresh_report=True)
env.cr.commit()
print('done')
PYEOF
REMOTE
