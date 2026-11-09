#!/usr/bin/env bash
# 509030002 @ RM02 (product 11446, loc 116, wh 14): user chose option 1 (2026-11-09) - count matched docs (10 on hand).
# Reverse the 2026-09-09 BGD-002224 compensation: delete SVL 265635 (-10/-900), give layer 174754 remaining 10/900,
# create RM02/Stock quant = 10 (cloned record). Result: docs 10 == SVL 10 == quant 10, Initial 0.
# Modes: check | dry (rolls back) | apply (pg_dump backup first).
set -euo pipefail
MODE="${1:-check}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply" >&2; exit 2;; esac
REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'
if [ "$MODE" = apply ]; then
  TS=$(date +%Y%m%d_%H%M%S)
  ssh mog-prod "$REMOTE_ENV; pg_dump -h localhost -U odoo -Fc -t stock_quant -t stock_valuation_layer MOG_LIVE > ~/db_backups/bgd002224_509030002_$TS.dump && ls -l ~/db_backups/bgd002224_509030002_$TS.dump"
fi
END=COMMIT; [ "$MODE" = apply ] || END=ROLLBACK
ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -P pager=off" <<SQL
BEGIN;
\echo BEFORE
SELECT (SELECT coalesce(sum(quantity),0) FROM stock_quant WHERE product_id=11446 AND location_id=116) quant,
       (SELECT sum(quantity) FROM stock_valuation_layer WHERE product_id=11446 AND warehouse_id=14) svl_q,
       (SELECT sum(value) FROM stock_valuation_layer WHERE product_id=11446 AND warehouse_id=14) svl_v;
DO \$\$
DECLARE n int; qid int;
BEGIN
  IF (SELECT count(*) FROM stock_quant WHERE product_id=11446 AND location_id=116)<>0 THEN RAISE EXCEPTION 'quant record already exists'; END IF;
  DELETE FROM stock_valuation_layer WHERE id=265635 AND quantity=-10 AND value=-900 AND stock_move_id=210382;
  GET DIAGNOSTICS n = ROW_COUNT; IF n<>1 THEN RAISE EXCEPTION 'SVL 265635 not as expected'; END IF;
  UPDATE stock_valuation_layer SET remaining_qty=10, remaining_value=900 WHERE id=174754 AND remaining_qty=0;
  GET DIAGNOSTICS n = ROW_COUNT; IF n<>1 THEN RAISE EXCEPTION 'SVL 174754 not as expected'; END IF;
  SELECT id INTO qid FROM stock_quant WHERE product_id=11446 AND lot_id IS NULL ORDER BY id LIMIT 1;
  IF qid IS NULL THEN SELECT id INTO qid FROM stock_quant WHERE lot_id IS NULL AND package_id IS NULL AND owner_id IS NULL AND quantity>0 ORDER BY id LIMIT 1; END IF;
  IF qid IS NULL THEN RAISE EXCEPTION 'no quant to clone'; END IF;
  CREATE TEMP TABLE qn AS SELECT * FROM stock_quant WHERE id=qid;
  UPDATE qn SET id=nextval(pg_get_serial_sequence('stock_quant','id')), product_id=11446, location_id=116, quantity=10, reserved_quantity=0, lot_id=NULL, package_id=NULL, owner_id=NULL, in_date=now() AT TIME ZONE 'UTC';
  INSERT INTO stock_quant SELECT * FROM qn;
END \$\$;
\echo AFTER
SELECT (SELECT sum(quantity) FROM stock_quant WHERE product_id=11446 AND location_id=116) quant,
       (SELECT sum(quantity) FROM stock_valuation_layer WHERE product_id=11446 AND warehouse_id=14) svl_q,
       (SELECT sum(value) FROM stock_valuation_layer WHERE product_id=11446 AND warehouse_id=14) svl_v,
       (SELECT sum(remaining_qty) FROM stock_valuation_layer WHERE product_id=11446 AND warehouse_id=14) rem_q;
$END;
SQL
