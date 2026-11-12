#!/usr/bin/env bash
# Remove over-cleared "Clearing: <Platform> -> customer [invoice]" entries (account_ar_settlement dup bug, see dup_clearing_dryrun.sh).
# Per invoice ref with >1 clearing:
#   keeper = clearing whose customer leg is reconciled with the invoice; extras = the rest.
#   1. extras: button_draft() (drops reconciliations, frees the payout credit) then button_cancel()
#   2. reconcile keeper's open Shopee debit leg with the freed payout credit line(s)
#   GL impact 0 (same receivable account, partner sub-ledger only).
# Only plans the dry-run classes 'AUTO' are touched; anything else is skipped and listed.
#
# Usage: scripts/fix_dup_clearing.sh <dry|apply> <Shopee|Lazada> <ALL|INVOICE_NO> [LIMIT] [BACKUP_DUMP_PATH_ON_MOG_PROD]
#   dry   : executes everything, reports, ROLLBACK (still takes row locks briefly; run off-hours)
#   apply : needs BACKUP_DUMP_PATH (file must exist on mog-prod, policy: dump MOG_LIVE first); COMMITs per ref (resumable/idempotent)
# Pilot: dry on one invoice, then apply on that one, then apply ALL in batches (LIMIT 100).
# Log: ~/Desktop/dup_clearing_<platform>_<mode>_<timestamp>.log
set -euo pipefail
MODE="${1:-}"; PLATFORM="${2:-}"; SCOPE="${3:-}"; LIMIT="${4:-0}"; BACKUP="${5:-}"
case "$MODE" in dry|apply) ;; *) echo "usage: $0 dry|apply Shopee|Lazada ALL|INVOICE_NO [LIMIT] [BACKUP_PATH]" >&2; exit 2;; esac
case "$PLATFORM" in Shopee) PID=2142;; Lazada) PID=2141;; *) echo "unknown platform (Shopee|Lazada)" >&2; exit 2;; esac
[[ "$SCOPE" =~ ^[A-Za-z0-9_./-]+$ ]] || { echo "bad scope" >&2; exit 2; }
[[ "$LIMIT" =~ ^[0-9]+$ ]] || { echo "bad limit" >&2; exit 2; }
[[ "$BACKUP" =~ ^[A-Za-z0-9_./~-]*$ ]] || { echo "bad backup path" >&2; exit 2; }
if [ "$MODE" = apply ] && [ -z "$BACKUP" ]; then echo "apply requires BACKUP_PATH (pg_dump of MOG_LIVE on mog-prod)" >&2; exit 2; fi
LOG="$HOME/Desktop/dup_clearing_${PLATFORM}_${MODE}_$(date +%Y%m%d_%H%M%S).log"
ssh mog-prod "cd /opt/instance1/odoo17 && source /opt/instance1/odoo17-venv/bin/activate && python3 odoo-bin shell -c /etc/instance1.conf -d MOG_LIVE --no-http 2>&1 << 'PYEOF' | grep -E '^(>|ERR)'
MODE = '$MODE'; SCOPE = '$SCOPE'; LIMIT = int('$LIMIT'); BACKUP = '$BACKUP'; PLATFORM = '$PLATFORM'; SH = int('$PID')
PREFIX = 'Clearing: ' + PLATFORM + '%'
import os
Move = env['account.move']; Line = env['account.move.line']; Partial = env['account.partial.reconcile']
def ctl(tag):
    env.cr.execute('''select coalesce(sum(l.amount_residual) filter (where l.partner_id=%s),0),
        coalesce(sum(l.amount_residual) filter (where l.partner_id<>%s),0),
        count(*) filter (where abs(l.amount_residual)>0.004)
        from account_move_line l join account_move m on m.id=l.move_id join account_account a on a.id=l.account_id
        where m.state='posted' and m.ref ilike %s and a.account_type='asset_receivable' ''', (SH, SH, PREFIX))
    r = env.cr.fetchone()
    print('> CTL', tag, 'platform_open', round(r[0],2), 'customer_open', round(r[1],2), 'open_legs', r[2])
def analyse(ref, moves):
    if '[' not in ref: return None, 'no invoice in ref'
    doc = ref.rsplit('[',1)[1].rstrip(']').strip()
    inv = Move.search([('name','=',doc),('move_type','like','out_')], limit=1)
    il = inv.line_ids.filtered(lambda l: l.account_id.account_type=='asset_receivable')[:1]
    if not il: return None, 'invoice/AR line not found'
    lock = moves[:1].company_id.fiscalyear_lock_date
    rows = []
    for m in moves:
        sl = m.line_ids.filtered(lambda l: l.partner_id.id==SH and l.debit>0)
        cl = m.line_ids.filtered(lambda l: l.partner_id.id!=SH and l.credit>0)
        if len(sl)!=1 or len(cl)!=1: return None, 'unexpected move shape ' + m.name
        to_inv = sum(Partial.search([('credit_move_id','=',cl.id),('debit_move_id','=',il.id)]).mapped('amount'))
        matched = Partial.search([('debit_move_id','=',sl.id)])
        rows.append(dict(m=m, sl=sl, cl=cl, keeper=to_inv>0.004, matched=matched,
                         used_else=abs(cl.balance)+cl.amount_residual-to_inv))
    keepers = [r for r in rows if r['keeper']]; extras = [r for r in rows if not r['keeper']]
    if not keepers: return None, 'no keeper'
    if len(keepers)>1: return None, '>1 keeper (partial payments?)'
    if not extras: return None, 'nothing to remove'
    if any(r['used_else']>0.005 for r in extras): return None, 'extra customer leg used elsewhere'
    if lock and any(r['m'].date<=lock for r in rows): return None, 'period locked (needs reverse route)'
    k = keepers[0]
    freed = sum(sum(r['matched'].mapped('amount')) for r in extras)
    kopen = k['sl'].amount_residual
    if kopen<=0.004 and freed<=0.004: pass
    elif abs(kopen-freed)>0.005: return None, 'keeper open %.2f != freed payout %.2f' % (kopen, freed)
    return dict(keeper=k, extras=extras, freed=freed, kopen=kopen, doc=doc), None
try:
    if MODE=='apply':
        assert BACKUP and os.path.exists(os.path.expanduser(BACKUP)), 'backup dump not found: ' + BACKUP
    ctl('before')
    moves = Move.search([('state','=','posted'),('ref','=like',PREFIX)])
    groups = {}
    for m in moves: groups.setdefault(m.ref, Move)
    for m in moves: groups[m.ref] |= m
    refs = sorted(r for r,g in groups.items() if len(g)>1 and (SCOPE=='ALL' or ('[' + SCOPE + ']') in r))
    print('> refs with >1 clearing in scope:', len(refs))
    ok = skipped = failed = 0; extra_amt = 0.0; n = 0
    for ref in refs:
        if LIMIT and n >= LIMIT: break
        plan, why = analyse(ref, groups[ref])
        if not plan:
            skipped += 1; print('> SKIP', ref, '|', why); continue
        n += 1
        try:
            with env.cr.savepoint():
                k = plan['keeper']; extras = plan['extras']
                payout_lines = Line
                for r in extras: payout_lines |= r['matched'].mapped('credit_move_id')
                for r in extras:
                    r['m'].message_post(body='Cancelled as duplicate clearing of ' + k['m'].name + ' (dedupe script, over-clear fix)')
                    r['m'].button_draft(); r['m'].button_cancel()
                if plan['kopen']>0.004:
                    (k['sl'] | payout_lines).reconcile()
                k['sl'].invalidate_recordset()
                assert abs(k['sl'].amount_residual)<0.005, 'keeper Shopee leg still open %s' % k['sl'].amount_residual
                assert all(r['m'].state=='cancel' for r in extras), 'extra not cancelled'
            ok += 1; extra_amt += sum(r['sl'].debit for r in extras)
            print('> OK', ref, 'keeper', k['m'].name, 'cancelled', [r['m'].name for r in extras], 'freed', plan['freed'])
            if MODE=='apply': env.cr.commit()
        except Exception as e:
            failed += 1; print('> FAIL', ref, repr(e)[:200])
    print('> SUMMARY ok', ok, 'skipped', skipped, 'failed', failed, 'extra_amount_cancelled', round(extra_amt,2))
    ctl('after')
    if MODE=='apply':
        env.cr.commit(); print('> COMMITTED')
    else:
        env.cr.rollback(); print('> ROLLED BACK (dry)')
except Exception as e:
    env.cr.rollback(); print('ERR', repr(e))
PYEOF
" | tee "$LOG"
echo "log: $LOG"
