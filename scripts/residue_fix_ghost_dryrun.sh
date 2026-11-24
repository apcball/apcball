#!/bin/bash
# READ-ONLY dry-run: classify 'pre-cutoff residue fix' qty-only layers (qty<>0, value=0, no move).
# Writes nothing. Usage: bash scripts/residue_fix_ghost_dryrun.sh > out.txt
ssh mog-prod 'PW=$(grep -E "^db_password" /etc/instance1.conf | cut -d= -f2 | tr -d " "); export PGPASSWORD="$PW"; psql -h localhost -U odoo MOG_LIVE -X -A -F"|" -P footer=off' <<'SQL'
\pset border 1
with t as (
  select product_id, warehouse_id, min(id) tid, sum(quantity) tq
  from stock_valuation_layer
  where quantity<>0 and value=0 and stock_move_id is null
    and description ilike 'Reverse FIFO Reset Flush (pre-cutoff residue fix)%'
  group by 1,2),
agg as (
  select t.product_id, t.warehouse_id, t.tid, t.tq,
    sum(l.quantity) filter (where l.accounting_date <  '2026-03-30 17:00') pre_q,
    sum(l.value)    filter (where l.accounting_date <  '2026-03-30 17:00') pre_v,
    sum(l.quantity) filter (where l.accounting_date >= '2026-03-30 17:00') win_q,
    sum(l.value)    filter (where l.accounting_date >= '2026-03-30 17:00') win_v,
    sum(l.quantity) end_q, sum(l.value) end_v,
    sum(l.remaining_qty) rem_q, sum(l.remaining_value) rem_v,
    count(*) filter (where l.description ilike '%ledger fix%' or l.description ilike '%REBASELINE%'
                       or l.description ilike '%count adjust%' or l.description ilike '%revaluation%'
                       and l.id<>t.tid) other_fix
  from t join stock_valuation_layer l on l.product_id=t.product_id and l.warehouse_id=t.warehouse_id
  group by 1,2,3,4),
q as (
  select sq.product_id, sl.warehouse_id, sum(sq.quantity) quant_q
  from stock_quant sq join stock_location sl on sl.id=sq.location_id
  where sl.usage='internal' group by 1,2)
select pp.default_code, sw.code wh,
  round(a.pre_v,2) pre_v, round(a.win_v,2) win_v, round(a.end_q,2) end_q, round(a.end_v,2) end_v,
  round(coalesce(q.quant_q,0),2) quant_q, round(coalesce(a.rem_q,0),2) rem_q, round(coalesce(a.rem_v,0),2) rem_v, a.other_fix,
  case
    when coalesce(a.pre_v,0)=0                                                    then 'A_clean_opening'
    when abs(a.end_q-coalesce(q.quant_q,0))>0.0001                               then 'D_qty_mismatch_vs_quant'
    when a.other_fix>0                                                            then 'E_already_touched_by_fix'
    when abs(a.end_q)<0.0001 and abs(a.end_v)>0.005                               then 'B_stuck_value_at_qty0'
    when abs(a.end_v-coalesce(a.rem_v,0))<=0.05 and abs(a.end_q-coalesce(a.rem_q,0))<0.0001 then 'C_opening_only_ending_consistent'
    else 'F_other_review'
  end cls
from agg a join product_product pp on pp.id=a.product_id join stock_warehouse sw on sw.id=a.warehouse_id
left join q on q.product_id=a.product_id and q.warehouse_id=a.warehouse_id
order by cls, pp.default_code;
SQL
