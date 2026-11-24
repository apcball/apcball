#!/usr/bin/env bash
# WB0004A100 @FG10: bring the PRE-cutoff SVL balance to 0 (qty and value), matching the ledger (stock-card opening 0 after
# fix_stockcard_cosmetic_WB0004A100.sh). Pre-cutoff wh1 SVL = +10 / +1,023.23 (layer 209585, backdated MV-0109410 transfer-in
# FG40->FG10, booked after the 2026-03-30 reset); the reset removed 174 vs 184 ledger.
# Fix: ONE move-less reverse layer wh1/FG10 qty -10, value -1,023.23, dated 2026-03-30 16:59:59.999999 (before the report window
# start 17:00 UTC) -> imex / FIFO-valuation window sums are unchanged; stock card opening value ~0; all-time SVL wh1 333 -> 323 = quant.
# Same pattern as the 'Reverse FIFO Reset Flush (pre-cutoff residue fix)' layers (template: layer 305107). Inserted directly
# (no ORM) so no FIFO queue / remaining_qty effect (remaining 0). IMEX-REBASELINE layer 265536 is NOT touched.
# Rollback: DELETE FROM stock_valuation_layer WHERE description LIKE 'Reverse pre-cutoff transfer-in 209585 (WB0004A100)%';
# Modes: check | dry (rolls back) | apply (pg_dump backup first)
set -euo pipefail
MODE="${1:-check}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply" >&2; exit 2;; esac
REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'
if [ "$MODE" = apply ]; then
  TS=$(date +%Y%m%d_%H%M%S)
  ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_valuation_layer -t stock_quant MOG_LIVE -f ~/db_backups/svl_WB0004A100_reverse_pre_$TS.dump && ls -l ~/db_backups/svl_WB0004A100_reverse_pre_$TS.dump"
fi
END=ROLLBACK; [ "$MODE" = apply ] && END=COMMIT
ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -X -v ON_ERROR_STOP=1 -P pager=off" <<SQL
BEGIN;
CREATE FUNCTION pg_temp.st() RETURNS TABLE(what text, v numeric) LANGUAGE sql AS \$f\$
 SELECT 'svl wh1 all qty', coalesce(sum(quantity),0) FROM stock_valuation_layer WHERE product_id=2087 AND warehouse_id=1
 UNION ALL SELECT 'svl wh1 all value', coalesce(round(sum(value)::numeric,2),0) FROM stock_valuation_layer WHERE product_id=2087 AND warehouse_id=1
 UNION ALL SELECT 'svl wh1 PRE qty', coalesce(sum(quantity),0) FROM stock_valuation_layer WHERE product_id=2087 AND warehouse_id=1 AND coalesce(accounting_date,create_date)<'2026-03-30 17:00'
 UNION ALL SELECT 'svl wh1 PRE value', coalesce(round(sum(value)::numeric,2),0) FROM stock_valuation_layer WHERE product_id=2087 AND warehouse_id=1 AND coalesce(accounting_date,create_date)<'2026-03-30 17:00'
 UNION ALL SELECT 'svl wh1 WINDOW qty', coalesce(sum(quantity),0) FROM stock_valuation_layer WHERE product_id=2087 AND warehouse_id=1 AND coalesce(accounting_date,create_date)>='2026-03-30 17:00'
 UNION ALL SELECT 'svl wh1 WINDOW value', coalesce(round(sum(value)::numeric,2),0) FROM stock_valuation_layer WHERE product_id=2087 AND warehouse_id=1 AND coalesce(accounting_date,create_date)>='2026-03-30 17:00'
 UNION ALL SELECT 'svl other wh (qty+value)', coalesce(sum(quantity),0)+coalesce(round(sum(value)::numeric,2),0) FROM stock_valuation_layer WHERE product_id=2087 AND warehouse_id IS DISTINCT FROM 1
 UNION ALL SELECT 'quant FG10', coalesce(sum(quantity),0) FROM stock_quant WHERE product_id=2087 AND location_id=8
\$f\$;
\echo BEFORE
SELECT * FROM pg_temp.st();
CREATE TEMP TABLE snap AS SELECT * FROM pg_temp.st();
DO \$\$
DECLARE n int;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM stock_valuation_layer WHERE id=209585 AND product_id=2087 AND warehouse_id=1 AND quantity=10 AND value=1023.23 AND remaining_qty=0) THEN
    RAISE EXCEPTION 'layer 209585 not as expected'; END IF;
  IF NOT EXISTS (SELECT 1 FROM stock_valuation_layer WHERE id=305107) THEN RAISE EXCEPTION 'template layer 305107 missing'; END IF;
  IF (SELECT count(*) FROM stock_valuation_layer WHERE description LIKE 'Reverse pre-cutoff transfer-in 209585 (WB0004A100)%')<>0 THEN RAISE EXCEPTION 'already applied'; END IF;
  -- 209585 was consumed by later sales (usage rows 105415: 9 / 920.91, 105155: 1 / 102.32). The script never edits 209585 or
  -- those rows; the reverse layer is a separate qty/value-only layer dated before the report window. Only report them.
  RAISE NOTICE 'FIFO usage rows on 209585 (left untouched): %', (SELECT count(*) FROM stock_valuation_layer_usage WHERE stock_valuation_layer_id=209585);
  IF (SELECT v FROM pg_temp.st() WHERE what='svl wh1 PRE qty')<>10 THEN RAISE EXCEPTION 'pre-cutoff qty is not 10'; END IF;

  DROP TABLE IF EXISTS t;
  CREATE TEMP TABLE t AS SELECT * FROM stock_valuation_layer WHERE id=305107;
  UPDATE t SET id=nextval(pg_get_serial_sequence('stock_valuation_layer','id')), stock_move_id=NULL,
    description='Reverse pre-cutoff transfer-in 209585 (WB0004A100) - WH FG10 (stock card opening 0)',
    quantity=-10, unit_cost=(SELECT unit_cost FROM stock_valuation_layer WHERE id=209585), value=-1023.23,
    remaining_qty=0, remaining_value=0, location_id=8, warehouse_id=1, current_warehouse_id=1,
    create_date='2026-03-30 16:59:59.999999', write_date=now() AT TIME ZONE 'UTC', accounting_date='2026-03-30 16:59:59.999999';
  INSERT INTO stock_valuation_layer SELECT * FROM t;
  GET DIAGNOSTICS n=ROW_COUNT;
  DROP TABLE t;
  IF n<>1 THEN RAISE EXCEPTION 'insert failed'; END IF;
END \$\$;
\echo AFTER
SELECT * FROM pg_temp.st();
\echo '--- inserted layer'
SELECT id, quantity, value, unit_cost, location_id, warehouse_id, accounting_date, stock_move_id, left(description,70) d FROM stock_valuation_layer WHERE description LIKE 'Reverse pre-cutoff transfer-in 209585 (WB0004A100)%';
DO \$\$
BEGIN
  IF (SELECT v FROM pg_temp.st() WHERE what='svl wh1 PRE qty')<>0
     OR abs((SELECT v FROM pg_temp.st() WHERE what='svl wh1 PRE value'))>1
     OR (SELECT v FROM pg_temp.st() WHERE what='svl wh1 all qty')<>(SELECT v FROM pg_temp.st() WHERE what='quant FG10')
     OR EXISTS (SELECT 1 FROM pg_temp.st() a JOIN snap b USING (what) WHERE a.what IN ('svl wh1 WINDOW qty','svl wh1 WINDOW value','svl other wh (qty+value)','quant FG10') AND a.v IS DISTINCT FROM b.v)
  THEN RAISE EXCEPTION 'post-check failed'; END IF;
  RAISE NOTICE 'post-check ok: pre-cutoff qty 0, all-time qty = quant, window and other warehouses unchanged';
END \$\$;
$END;
SQL
