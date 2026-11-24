#!/bin/bash
# READ-ONLY. For the 'pre-cutoff residue fix' qty-only layer pairs: compare buz_new_stock_card basis
# (move lines in/out of the warehouse internal locations; value = SVL with location_id in scope: pre-start any, in-range move-linked)
# against quant and SVL for range 2026-03-30 (start_utc 2026-03-29 17:00) .. today. Writes nothing.
ssh mog-prod 'PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"; psql -h localhost -U odoo MOG_LIVE -X -P footer=off' <<'SQL'
with t as (select distinct product_id, warehouse_id from stock_valuation_layer
  where quantity<>0 and value=0 and description ilike 'Reverse FIFO Reset Flush (pre-cutoff residue fix)%' and product_id<>11535 and stock_move_id is null),
 -- note: 305167 was relinked; others still move-less
 locs as (select t.product_id, t.warehouse_id, array_agg(sl.id) ids from t join stock_location sl on sl.warehouse_id=t.warehouse_id and sl.usage='internal' group by 1,2),
 card_q as (
  select l.product_id, l.warehouse_id,
   coalesce(sum(case when ml.location_dest_id=any(l.ids) and not ml.location_id=any(l.ids) then ml.quantity when ml.location_id=any(l.ids) and not ml.location_dest_id=any(l.ids) then -ml.quantity else 0 end),0) cq
  from locs l left join stock_move_line ml on ml.product_id=l.product_id and ml.state='done' and (ml.location_id=any(l.ids) or ml.location_dest_id=any(l.ids))
  group by 1,2),
 card_v as (
  select l.product_id, l.warehouse_id,
   coalesce(sum(s.value) filter (where coalesce(s.accounting_date,s.create_date)<'2026-03-29 17:00' and s.location_id=any(l.ids)),0)
 + coalesce(sum(s.value) filter (where coalesce(s.accounting_date,s.create_date)>='2026-03-29 17:00' and s.location_id=any(l.ids) and s.stock_move_id is not null),0) cv
  from locs l left join stock_valuation_layer s on s.product_id=l.product_id and s.warehouse_id=l.warehouse_id
  group by 1,2),
 sv as (select product_id, warehouse_id, sum(quantity) sq, round(sum(value),2) sval, round(sum(value) filter (where coalesce(accounting_date,create_date)>='2026-03-30 17:00'),2) wval from stock_valuation_layer group by 1,2),
 qt as (select l.product_id, l.warehouse_id, coalesce(sum(q.quantity),0) qq from locs l left join stock_quant q on q.product_id=l.product_id and q.location_id=any(l.ids) group by 1,2)
select pp.default_code, sw.code wh, round(cq.cq,2) card_q, round(qt.qq,2) quant_q, round(card_q.cq-qt.qq,2) q_gap,
  round(card_v.cv,2) card_v, sv.sval svl_v, round(card_v.cv-sv.sval,2) v_gap
from locs l join product_product pp on pp.id=l.product_id join stock_warehouse sw on sw.id=l.warehouse_id
join card_q cq on cq.product_id=l.product_id and cq.warehouse_id=l.warehouse_id
join card_q on card_q.product_id=l.product_id and card_q.warehouse_id=l.warehouse_id
join card_v on card_v.product_id=l.product_id and card_v.warehouse_id=l.warehouse_id
join sv on sv.product_id=l.product_id and sv.warehouse_id=l.warehouse_id
join qt on qt.product_id=l.product_id and qt.warehouse_id=l.warehouse_id
order by abs(card_q.cq-qt.qq) desc, pp.default_code;
SQL
