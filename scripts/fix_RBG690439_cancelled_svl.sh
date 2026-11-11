#!/usr/bin/env bash
# RBG-690439: picking 27602 cancelled but its SVL 217944/217945 (showroom -1/-3100, NC +1/+3100) were never reversed.
# Picking 29668 (done, SVL 264010/11) is the live doc. Adds ONE plain reversing SVL pair (no stock_move, remaining 0),
# sets remaining of 217945 to 0. No quant/move/journal touched.
# Rollback: DELETE FROM stock_valuation_layer WHERE description LIKE 'Reverse cancelled RBG-690439 (27602)%';
#           UPDATE stock_valuation_layer SET remaining_qty=1, remaining_value=3100 WHERE id=217945;
# Modes: check | apply
set -euo pipefail
MODE="${1:-check}"
case "$MODE" in check|apply) ;; *) echo "usage: $0 check|apply" >&2; exit 2;; esac
REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'
STAMP=$(date +%Y%m%d_%H%M%S)
if [ "$MODE" = apply ]; then
  ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_valuation_layer MOG_LIVE -f ~/db_backups/svl_rbg690439_${STAMP}.dump && ls -l ~/db_backups/svl_rbg690439_${STAMP}.dump"
  SQLEND='COMMIT;'
else
  SQLEND='ROLLBACK;'
fi
ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1" <<SQL
BEGIN;
DO \$\$
DECLARE n int; r numeric;
BEGIN
  SELECT count(*) INTO n FROM stock_valuation_layer WHERE description LIKE 'Reverse cancelled RBG-690439 (27602)%';
  SELECT remaining_qty INTO r FROM stock_valuation_layer WHERE id=217945;
  IF n<>0 OR r<>1 THEN RAISE EXCEPTION 'precondition failed n=% r=%', n, r; END IF;
END \$\$;
INSERT INTO stock_valuation_layer
  (company_id, product_id, description, quantity, unit_cost, value, remaining_qty, remaining_value,
   warehouse_id, current_warehouse_id, create_uid, write_uid, create_date, write_date, accounting_date)
SELECT company_id, product_id, 'Reverse cancelled RBG-690439 (27602) - ' || CASE WHEN id=217944 THEN 'showroom' ELSE 'NC' END,
   -quantity, unit_cost, -value, 0, 0, warehouse_id, current_warehouse_id, 2, 2, create_date, now() AT TIME ZONE 'UTC', accounting_date
FROM stock_valuation_layer WHERE id IN (217944,217945);
UPDATE stock_valuation_layer SET remaining_qty=0, remaining_value=0 WHERE id=217945;
\echo '== after: per-warehouse SVL for MF025R123'
SELECT w.name, sum(l.quantity) q, round(sum(l.value),2) v FROM stock_valuation_layer l JOIN stock_warehouse w ON w.id=l.warehouse_id
 JOIN product_product p ON p.id=l.product_id WHERE p.default_code='MF025R123' GROUP BY 1 ORDER BY 1;
\echo '== RBG-690439 net by move state'
SELECT m.state, sum(l.quantity) q FROM stock_valuation_layer l JOIN stock_move m ON m.id=l.stock_move_id WHERE m.id IN (269640,273370,273371,281881) GROUP BY 1;
$SQLEND
SQL
