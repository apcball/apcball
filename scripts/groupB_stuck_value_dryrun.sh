#!/bin/bash
# READ-ONLY. Plan for group B (qty-0 / value-stuck rows after 'pre-cutoff residue fix'). Writes nothing.
ssh mog-prod 'PW=$(grep -E "^db_password" /etc/instance1.conf | cut -d= -f2 | tr -d " "); export PGPASSWORD="$PW"; psql -h localhost -U odoo MOG_LIVE -X' <<'SQL'
\echo '== per-wh state for every warehouse of the 6 products + swap counterparts (excl. tagged rebaseline in guard col)'
with prods as (select id,default_code from product_product where default_code in
 ('504110001','3AC0031100','3ACA0041100','201030398','511010014','(ไม่ใช้)C2S0001HI020000','504040003','MO010S101'))
select p.default_code, sw.code wh,
 round(sum(l.quantity) filter (where l.accounting_date< '2026-03-30 17:00'),2) pre_q,
 round(sum(l.value)    filter (where l.accounting_date< '2026-03-30 17:00'),2) pre_v,
 round(sum(l.quantity) filter (where l.accounting_date>='2026-03-30 17:00'),2) win_q,
 round(sum(l.value)    filter (where l.accounting_date>='2026-03-30 17:00'),2) win_v,
 round(sum(l.quantity),2) all_q, round(sum(l.value),2) all_v,
 round(coalesce((select sum(sq.quantity) from stock_quant sq join stock_location sl on sl.id=sq.location_id where sq.product_id=p.id and sl.warehouse_id=l.warehouse_id and sl.usage='internal'),0),2) quant_q,
 round(coalesce(sum(l.remaining_qty),0),2) rem_q, round(coalesce(sum(l.remaining_value),0),2) rem_v
from prods p join stock_valuation_layer l on l.product_id=p.id join stock_warehouse sw on sw.id=l.warehouse_id
group by p.id,p.default_code,sw.code,l.warehouse_id order by 1,2;
SQL
