#!/usr/bin/env bash
# 404030004 (product via default_code) RM02T/2610021 (move 363828, picking 48846) transferred 230 RM02->RM03/FXF but RM02 only had 195.
# User option A (2026-11-09): RM03 really holds 328. Move line/header 230 -> 195, SVL 297129 -230/-19550 -> -195/-16575 (remaining 0),
# delete SVL 297130 (+35 split) and our ledger-fix pair 302739/302740, FXF quant 363 -> 328, delete QTL quant (-35).
# Result: RM02 docs 0 == quant 0 == SVL window 0; RM03 docs 328 == quant 328 == SVL; Initial 0.
# Modes: check | dry (rolls back) | apply (pg_dump backup first).
set -euo pipefail
MODE="${1:-check}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply" >&2; exit 2;; esac
REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'
if [ "$MODE" = apply ]; then
  TS=$(date +%Y%m%d_%H%M%S)
  ssh mog-prod "$REMOTE_ENV; pg_dump -h localhost -U odoo -Fc -t stock_quant -t stock_valuation_layer -t stock_move -t stock_move_line MOG_LIVE > ~/db_backups/p404030004_transfer_$TS.dump && ls -l ~/db_backups/p404030004_transfer_$TS.dump"
fi
END=ROLLBACK; [ "$MODE" = apply ] && END=COMMIT
ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -P pager=off" <<SQL
BEGIN;
CREATE FUNCTION pg_temp.st() RETURNS TABLE(what text, v numeric) LANGUAGE sql AS \$f\$
 SELECT 'quant RM02', coalesce((SELECT sum(quantity) FROM stock_quant WHERE product_id=p.id AND location_id=116),0) FROM product_product p WHERE default_code='404030004'
 UNION ALL SELECT 'quant FXF', coalesce((SELECT sum(quantity) FROM stock_quant WHERE product_id=p.id AND location_id=1205),0) FROM product_product p WHERE default_code='404030004'
 UNION ALL SELECT 'quant QTL', coalesce((SELECT sum(quantity) FROM stock_quant WHERE product_id=p.id AND location_id=1187),0) FROM product_product p WHERE default_code='404030004'
 UNION ALL SELECT 'svl14 all', coalesce(sum(quantity),0) FROM stock_valuation_layer WHERE product_id=(SELECT id FROM product_product WHERE default_code='404030004') AND warehouse_id=14
 UNION ALL SELECT 'svl14 win', coalesce(sum(quantity),0) FROM stock_valuation_layer WHERE product_id=(SELECT id FROM product_product WHERE default_code='404030004') AND warehouse_id=14 AND COALESCE(accounting_date,create_date)>='2026-03-30 17:00'
 UNION ALL SELECT 'svl14 win value', coalesce(round(sum(value),2),0) FROM stock_valuation_layer WHERE product_id=(SELECT id FROM product_product WHERE default_code='404030004') AND warehouse_id=14 AND COALESCE(accounting_date,create_date)>='2026-03-30 17:00'
 UNION ALL SELECT 'svl15 all', coalesce(sum(quantity),0) FROM stock_valuation_layer WHERE product_id=(SELECT id FROM product_product WHERE default_code='404030004') AND warehouse_id=15
 UNION ALL SELECT 'svl15 win', coalesce(sum(quantity),0) FROM stock_valuation_layer WHERE product_id=(SELECT id FROM product_product WHERE default_code='404030004') AND warehouse_id=15 AND COALESCE(accounting_date,create_date)>='2026-03-30 17:00'
 UNION ALL SELECT 'svl15 win value', coalesce(round(sum(value),2),0) FROM stock_valuation_layer WHERE product_id=(SELECT id FROM product_product WHERE default_code='404030004') AND warehouse_id=15 AND COALESCE(accounting_date,create_date)>='2026-03-30 17:00'
\$f\$;
\echo BEFORE
SELECT * FROM pg_temp.st();
DO \$\$
DECLARE n int; pid int;
BEGIN
  SELECT id INTO pid FROM product_product WHERE default_code='404030004';
  IF (SELECT product_id FROM stock_move WHERE id=363828)<>pid THEN RAISE EXCEPTION 'move 363828 is not this product'; END IF;
  IF (SELECT count(*) FROM stock_valuation_layer_usage WHERE stock_valuation_layer_id IN (297128,297129,297130,302739,302740))>0 THEN RAISE EXCEPTION 'FIFO usage rows reference the layers'; END IF;
  IF (SELECT count(*) FROM mrp_period_cost_alloc WHERE svl_id IN (297128,297129,297130,302739,302740))>0 THEN RAISE EXCEPTION 'cost alloc references layers'; END IF;
  UPDATE stock_move_line SET quantity=195, quantity_product_uom=195 WHERE id=335077 AND move_id=363828 AND quantity=230;
  GET DIAGNOSTICS n=ROW_COUNT; IF n<>1 THEN RAISE EXCEPTION 'move line not as expected'; END IF;
  UPDATE stock_move SET product_uom_qty=195, product_qty=195, quantity=195 WHERE id=363828 AND product_uom_qty=230;
  GET DIAGNOSTICS n=ROW_COUNT; IF n<>1 THEN RAISE EXCEPTION 'move not as expected'; END IF;
  UPDATE stock_valuation_layer SET quantity=-195, value=-16575, remaining_qty=0, remaining_value=NULL WHERE id=297129 AND quantity=-230 AND value=-19550;
  GET DIAGNOSTICS n=ROW_COUNT; IF n<>1 THEN RAISE EXCEPTION 'SVL 297129 not as expected'; END IF;
  DELETE FROM stock_valuation_layer WHERE id=297130 AND quantity=35 AND stock_move_id=363828;
  GET DIAGNOSTICS n=ROW_COUNT; IF n<>1 THEN RAISE EXCEPTION 'SVL 297130 not as expected'; END IF;
  DELETE FROM stock_valuation_layer WHERE id IN (302739,302740) AND description LIKE 'Reverse FIFO Reset Flush (404030004 ledger fix)%';
  GET DIAGNOSTICS n=ROW_COUNT; IF n<>2 THEN RAISE EXCEPTION 'ledger-fix pair not as expected'; END IF;
  UPDATE stock_quant SET quantity=328, write_date=now() AT TIME ZONE 'UTC' WHERE id=46731 AND quantity=363 AND reserved_quantity=0;
  GET DIAGNOSTICS n=ROW_COUNT; IF n<>1 THEN RAISE EXCEPTION 'FXF quant not as expected'; END IF;
  DELETE FROM stock_quant WHERE id=80237 AND quantity=-35 AND reserved_quantity=0;
  GET DIAGNOSTICS n=ROW_COUNT; IF n<>1 THEN RAISE EXCEPTION 'QTL quant not as expected'; END IF;
END \$\$;
\echo AFTER
SELECT * FROM pg_temp.st();
\echo ' (expect quant RM02 0, FXF 328, QTL 0; svl14 all=win=0, win value 0; svl15 all=win=328, value 27614-2975+2975 unchanged)'
$END;
SQL
