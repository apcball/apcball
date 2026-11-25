#!/bin/bash
# READ-ONLY dry-run plan: over-cleared "Clearing: <Platform> -> customer [invoice]" entries (account_ar_settlement).
# Writes NOTHING to prod (psql runs with default_transaction_read_only=on).
#
# Plan per invoice ref (see conversation 2026-11-12):
#   keeper = clearing whose customer leg is reconciled with the invoice
#   extras = other clearings of the same ref
#   fix    = (a) unreconcile extra's platform leg from payout, (b) cancel extra move,
#            (c) reconcile freed payout credit with keeper's open platform debit leg.
#   GL impact 0 (all legs on the same receivable account, only partner sub-ledger moves).
#
# Usage:  scripts/dup_clearing_dryrun.sh [PLATFORM] [INVOICE_NO]   # PLATFORM = Shopee (default) | Lazada ; INVOICE_NO optional, e.g. IV260701646
# Output: ~/Desktop/dup_clearing_<platform>_plan_<date>.csv (per ref) and ..._detail_<date>.csv (per clearing)
set -euo pipefail
PLATFORM="${1:-Shopee}"; DOC="${2:-}"
case "$PLATFORM" in
  Shopee) PID=2142;;
  Lazada) PID=2141;;
  *) echo "unknown platform '$PLATFORM' (Shopee|Lazada)" >&2; exit 2;;
esac
OUT_DIR="$HOME/Desktop"; D=$(date +%F)
PLAN="$OUT_DIR/dup_clearing_${PLATFORM}_plan_${D}.csv"; DETAIL="$OUT_DIR/dup_clearing_${PLATFORM}_detail_${D}.csv"
[[ "$DOC" =~ ^[A-Za-z0-9_./-]*$ ]] || { echo "bad invoice no"; exit 1; }

read -r -d '' BASE <<SQL || true
with c as (
 select m.id mid, m.name, m.ref, m.date, m.create_date::date cdate, m.company_id,
  substring(m.ref from '\[([^\]]+)\]\s*\$') doc
 from account_move m where m.state='posted' and m.ref ilike 'Clearing: ${PLATFORM}%'
),
d as (select ref from c group by ref having count(*)>1),
x as (
 select c.*, inv.id inv_id, inv.amount_total inv_total, inv.payment_state, il.id inv_line,
  sl.id shopee_line, sl.debit shopee_amt, sl.amount_residual shopee_resid,
  cl.id cust_line, cl.partner_id cust_partner, abs(cl.balance) cust_amt, cl.amount_residual cust_resid,
  coalesce((select sum(pr.amount) from account_partial_reconcile pr where pr.debit_move_id=sl.id),0) shopee_matched,
  coalesce((select string_agg(distinct pm.name, ',') from account_partial_reconcile pr join account_move_line pl on pl.id=pr.credit_move_id join account_move pm on pm.id=pl.move_id where pr.debit_move_id=sl.id),'') payouts,
  coalesce((select sum(pr.amount) from account_partial_reconcile pr where pr.credit_move_id=cl.id and pr.debit_move_id=il.id),0) cust_to_inv
 from c join d on d.ref=c.ref
 join account_move_line sl on sl.move_id=c.mid and sl.partner_id=${PID} and sl.debit>0
 join account_move_line cl on cl.move_id=c.mid and cl.partner_id<>${PID} and cl.credit>0
 left join lateral (select id,amount_total,payment_state from account_move i where i.name=c.doc and i.move_type like 'out_%' limit 1) inv on true
 left join lateral (select l.id from account_move_line l join account_account a on a.id=l.account_id and a.account_type='asset_receivable' where l.move_id=inv.id limit 1) il on true
 where ('${DOC}'='' or c.doc='${DOC}')
),
y as (
 select x.*, case when cust_to_inv>0.004 then 'KEEPER' else 'EXTRA' end role,
  (cust_amt + cust_resid - cust_to_inv) cust_used_elsewhere,   -- cust_resid is <=0 for a credit leg
  (select fiscalyear_lock_date from res_company rc where rc.id=x.company_id) lock_date
 from x
)
SQL

PSQL='PW=$(grep -E "^db_password" /etc/instance1.conf | cut -d= -f2 | tr -d " "); PGPASSWORD=$PW psql -h localhost -U odoo MOG_LIVE -X --csv -v ON_ERROR_STOP=1 -c "set default_transaction_read_only=on" -f -'

# Per-clearing detail
{ echo "$BASE"; cat <<'SQL'
select ref "Ref", name "Clearing move", date "Date", cdate "Created", role "Role",
 shopee_amt "Amount", shopee_resid "Platform leg open", shopee_matched "Platform matched to payout", payouts "Payout(s)",
 cust_resid "Customer leg open", cust_to_inv "Customer matched to invoice", round(cust_used_elsewhere,2) "Customer used elsewhere",
 inv_total "Invoice total", payment_state "Invoice state",
 case when lock_date is not null and date<=lock_date then 'LOCKED' else '' end "Lock"
from y order by ref, role, name;
SQL
} | ssh mog-prod "$PSQL" | awk 'NR==1 && $0=="SET"{next} {print}' > "$DETAIL"

# Per-ref plan
{ echo "$BASE"; cat <<'SQL'
, p as (
 select ref, min(doc) doc, max(inv_total) inv_total, count(*) n,
  count(*) filter (where role='KEEPER') keepers, count(*) filter (where role='EXTRA') extras,
  sum(shopee_amt) filter (where role='EXTRA') extra_amt,
  coalesce(sum(shopee_matched) filter (where role='EXTRA'),0) freed_payout,
  coalesce(sum(shopee_resid) filter (where role='KEEPER'),0) keeper_shopee_open,
  coalesce(sum(shopee_resid) filter (where role='EXTRA'),0) extra_shopee_open,
  coalesce(sum(cust_resid) filter (where role='EXTRA'),0) extra_cust_open,
  coalesce(sum(cust_used_elsewhere) filter (where role='EXTRA'),0) extra_cust_used_elsewhere,
  bool_or(lock_date is not null and date<=lock_date) locked,
  string_agg(distinct payouts, ',') filter (where payouts<>'') payouts,
  string_agg(name, ',' order by role desc, name) moves
 from y group by ref)
select ref "Ref", doc "Invoice", inv_total "Invoice total", n "Clearings", keepers "Keepers", extras "Extras",
 extra_amt "Extra amount", freed_payout "Payout freed on cancel", keeper_shopee_open "Keeper platform open",
 round(keeper_shopee_open - freed_payout,2) "Platform residual after fix",
 extra_cust_open "Extra customer open (removed)", payouts "Payouts touched",
 case when keepers=0 then 'MANUAL: no keeper'
      when extras=0 then 'OK: nothing to remove'
      when extra_cust_used_elsewhere>0.005 then 'MANUAL: extra customer leg used elsewhere'
      when keepers>1 then 'MANUAL: >1 keeper (partial payments?)'
      when abs(keeper_shopee_open - freed_payout)<0.005 and locked then 'AUTO-REVERSE: balanced but period locked'
      when abs(keeper_shopee_open - freed_payout)<0.005 then 'AUTO: cancel extras + reconcile'
      when keeper_shopee_open - freed_payout>0 then 'MANUAL: keeper platform debit left (no payout)'
      else 'MANUAL: freed payout exceeds keeper open' end "Plan",
 moves "Moves (keeper first)"
from p order by 12 nulls last, 1;
SQL
} | ssh mog-prod "$PSQL" | awk 'NR==1 && $0=="SET"{next} {print}' > "$PLAN"

python3 -I - "$PLAN" "$DETAIL" <<'PY'
import csv,sys,collections
r=list(csv.DictReader(open(sys.argv[1])))
c=collections.Counter(x['Plan'] for x in r)
f=lambda k,rows: round(sum(float(x[k] or 0) for x in rows),2)
print(f"refs: {len(r)}")
for k,v in sorted(c.items()): 
    rows=[x for x in r if x['Plan']==k]
    print(f"  {v:5d}  {k:55s} extra_amt={f('Extra amount',rows):>14,.2f} payout_freed={f('Payout freed on cancel',rows):>14,.2f}")
print("plan  :",sys.argv[1]); print("detail:",sys.argv[2])
PY
