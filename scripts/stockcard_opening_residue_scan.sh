#!/bin/bash
# READ-ONLY. Scan + dry-run for the "stock card opening != 0 at cutoff" defect (FU0033FC1560 FG10/FG40, move MV-0109408).
# Cause: pre-cutoff-dated move created after the 2026-03-30 reset -> reset zeroed less/more than the move ledger holds,
# so move-ledger balance at cutoff end is nonzero (stock card opening != 0) while SVL/quant/imex say 0.
# Per (product, internal location): balance of done moves dated <= cutoff (2026-03-30 17:00 UTC), plus
# whether any of those moves was created after the cutoff (the causal pattern).
# Usage: bash stockcard_opening_residue_scan.sh [product_code]   (no writes; proposal = compensating no-quant moves)
CODE="${1:-}"
ssh mog-prod 'PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"; psql -h localhost -U odoo MOG_LIVE -X -P footer=off -v code="'"$CODE"'"' <<'SQL'
\echo '== 1. rows: move-ledger balance at cutoff <> 0 (internal locations) =='
with bal as (
  select m.product_id, l.id loc_id, l.complete_name, l.warehouse_id,
    sum(case when m.location_dest_id=l.id then m.quantity else -m.quantity end) opening,
    count(*) filter (where m.create_date > '2026-03-30 17:00' and m.reference not ilike 'Product Quantity Updated%') late_created,
    string_agg(distinct m.reference, ',') filter (where m.create_date > '2026-03-30 17:00' and m.reference not ilike 'Product Quantity Updated%') late_refs
  from stock_move m
  join stock_location l on l.usage='internal' and (l.id=m.location_id or l.id=m.location_dest_id)
  where m.state='done' and m.date <= '2026-03-30 17:00'
    and not (m.location_id=l.id and m.location_dest_id=l.id)
    and (:'code'='' or m.product_id=(select id from product_product where default_code=:'code'))
  group by 1,2,3,4
  having abs(sum(case when m.location_dest_id=l.id then m.quantity else -m.quantity end)) > 0.0001
)
select pp.default_code, b.complete_name loc, round(b.opening,4) opening_qty,
       b.late_created, left(b.late_refs,60) late_refs
from bal b join product_product pp on pp.id=b.product_id
order by (b.late_created>0) desc, abs(b.opening) desc, pp.default_code;

\echo '== 2. summary =='
with bal as (
  select m.product_id, l.id loc_id,
    sum(case when m.location_dest_id=l.id then m.quantity else -m.quantity end) opening,
    count(*) filter (where m.create_date > '2026-03-30 17:00' and m.reference not ilike 'Product Quantity Updated%') late_created
  from stock_move m
  join stock_location l on l.usage='internal' and (l.id=m.location_id or l.id=m.location_dest_id)
  where m.state='done' and m.date <= '2026-03-30 17:00' and not (m.location_id=l.id and m.location_dest_id=l.id)
  group by 1,2
  having abs(sum(case when m.location_dest_id=l.id then m.quantity else -m.quantity end)) > 0.0001
)
select count(*) rows_total, count(*) filter (where late_created>0) rows_late_created_pattern,
       count(distinct product_id) products, round(sum(opening),2) net_qty from bal;

\echo '== 3. DRY-RUN proposal: compensating move per row (no quant, no SVL), dated 2026-03-30 16:59:59.999999 =='
\echo '   qty>0 at loc -> move loc -> Inventory adjustment(14) qty=opening ; qty<0 -> adjustment -> loc qty=-opening'
with bal as (
  select m.product_id, l.id loc_id, l.complete_name,
    sum(case when m.location_dest_id=l.id then m.quantity else -m.quantity end) opening
  from stock_move m
  join stock_location l on l.usage='internal' and (l.id=m.location_id or l.id=m.location_dest_id)
  where m.state='done' and m.date <= '2026-03-30 17:00' and not (m.location_id=l.id and m.location_dest_id=l.id)
    and (:'code'='' or m.product_id=(select id from product_product where default_code=:'code'))
  group by 1,2,3
  having abs(sum(case when m.location_dest_id=l.id then m.quantity else -m.quantity end)) > 0.0001
)
select pp.default_code, b.complete_name,
  case when b.opening>0 then b.complete_name else 'Virtual Locations/Inventory adjustment' end as src,
  case when b.opening>0 then 'Virtual Locations/Inventory adjustment' else b.complete_name end as dst,
  abs(round(b.opening,4)) qty
from bal b join product_product pp on pp.id=b.product_id order by pp.default_code, b.complete_name limit 200;
SQL
