#!/usr/bin/env bash
# WB0004A100 @FG10 cosmetic: make buz_new_stock_card look like imex (opening 0, +10 rebaseline row on 2026-03-31).
# Ledger (stock_move_line) FG10: pre-cutoff +10 (backdated MV-0109410), imex shows Initial 0 + header-only IMEX-REBASELINE +10.
# Fix (no quant, no SVL touched; ledger total stays 323 = quant):
#   1) compensating move FG10 -> Inventory adjustment(14) 10, dated 2026-03-30 16:59:59.999999  (opening 10 -> 0)
#   2) set line 303331 of IMEX-REBASELINE move 332745 (+10, 2026-03-31 07:00) from state 'cancel' to 'done' (stock card then shows the row)
# Rollback: UPDATE stock_move_line SET state='cancel' WHERE id=303331;
#           DELETE FROM stock_move_line WHERE reference='STOCKCARD-COSMETIC-WB0004A100';
#           DELETE FROM stock_move WHERE reference='STOCKCARD-COSMETIC-WB0004A100';
# Modes: check | dry (rolls back) | apply (pg_dump backup first)
set -euo pipefail
MODE="${1:-check}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply" >&2; exit 2;; esac
REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'
if [ "$MODE" = apply ]; then
  TS=$(date +%Y%m%d_%H%M%S)
  ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_quant -t stock_valuation_layer -t stock_move -t stock_move_line MOG_LIVE -f ~/db_backups/stockcard_cosmetic_WB0004A100_$TS.dump && ls -l ~/db_backups/stockcard_cosmetic_WB0004A100_$TS.dump"
fi
END=ROLLBACK; [ "$MODE" = apply ] && END=COMMIT
ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -X -v ON_ERROR_STOP=1 -P pager=off" <<SQL
BEGIN;
CREATE FUNCTION pg_temp.st() RETURNS TABLE(what text, v numeric) LANGUAGE sql AS \$f\$
 SELECT 'ledger FG10 opening (<=cut)', coalesce(sum(CASE WHEN location_dest_id=8 THEN quantity ELSE -quantity END),0) FROM stock_move_line WHERE product_id=2087 AND state='done' AND (location_id=8 OR location_dest_id=8) AND date<='2026-03-30 17:00'
 UNION ALL SELECT 'ledger FG10 window', coalesce(sum(CASE WHEN location_dest_id=8 THEN quantity ELSE -quantity END),0) FROM stock_move_line WHERE product_id=2087 AND state='done' AND (location_id=8 OR location_dest_id=8) AND date>'2026-03-30 17:00'
 UNION ALL SELECT 'ledger FG10 total', coalesce(sum(CASE WHEN location_dest_id=8 THEN quantity ELSE -quantity END),0) FROM stock_move_line WHERE product_id=2087 AND state='done' AND (location_id=8 OR location_dest_id=8)
 UNION ALL SELECT 'quant FG10', coalesce(sum(quantity),0) FROM stock_quant WHERE product_id=2087 AND location_id=8
 UNION ALL SELECT 'svl count', count(*) FROM stock_valuation_layer WHERE product_id=2087
 UNION ALL SELECT 'svl value', coalesce(round(sum(value)::numeric,2),0) FROM stock_valuation_layer WHERE product_id=2087
\$f\$;
\echo BEFORE
SELECT * FROM pg_temp.st();
CREATE TEMP TABLE snap AS SELECT * FROM pg_temp.st();
DO \$\$
DECLARE n int; mid int; pu int;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM stock_move WHERE id=332745 AND product_id=2087 AND reference='IMEX-REBASELINE-20260331' AND state='done' AND quantity=10 AND location_dest_id=8) THEN RAISE EXCEPTION 'move 332745 not as expected'; END IF;
  IF (SELECT count(*) FROM stock_move_line WHERE move_id=332745 AND state='cancel')<>1 THEN RAISE EXCEPTION 'expected exactly one cancelled line on 332745'; END IF;
  IF (SELECT count(*) FROM stock_move WHERE reference='STOCKCARD-COSMETIC-WB0004A100')<>0 THEN RAISE EXCEPTION 'already applied'; END IF;
  IF (SELECT coalesce(sum(CASE WHEN location_dest_id=8 THEN quantity ELSE -quantity END),0) FROM stock_move_line WHERE product_id=2087 AND state='done' AND (location_id=8 OR location_dest_id=8) AND date<='2026-03-30 17:00')<>10 THEN RAISE EXCEPTION 'FG10 opening is not 10'; END IF;
  SELECT product_uom INTO pu FROM stock_move WHERE id=332745;

  -- 1) compensating move FG10 -> Inventory adjustment (opening 10 -> 0)
  DROP TABLE IF EXISTS m; DROP TABLE IF EXISTS l;
  CREATE TEMP TABLE m AS SELECT * FROM stock_move WHERE id=141826;
  UPDATE m SET id=nextval(pg_get_serial_sequence('stock_move','id')), product_id=2087, product_uom=pu,
    name='Stock card cosmetic WB0004A100 opening 10 -> 0 (see IMEX-REBASELINE-20260331)', reference='STOCKCARD-COSMETIC-WB0004A100',
    location_id=8, location_dest_id=14, product_qty=10, product_uom_qty=10, quantity=10, picked=true, state='done', is_inventory=false, is_done=true,
    date=TIMESTAMP '2026-03-30 16:59:59.999999', weight=coalesce((SELECT weight FROM product_product WHERE id=2087),0)*10,
    create_date=now() AT TIME ZONE 'UTC', write_date=now() AT TIME ZONE 'UTC';
  INSERT INTO stock_move SELECT * FROM m;
  SELECT id INTO mid FROM m;
  CREATE TEMP TABLE l AS SELECT * FROM stock_move_line WHERE id=131638;
  UPDATE l SET id=nextval(pg_get_serial_sequence('stock_move_line','id')), move_id=mid, product_id=2087, product_uom_id=pu,
    location_id=8, location_dest_id=14, quantity=10, quantity_product_uom=10, state='done', reference='STOCKCARD-COSMETIC-WB0004A100', picked=true,
    date=TIMESTAMP '2026-03-30 16:59:59.999999', create_date=now() AT TIME ZONE 'UTC', write_date=now() AT TIME ZONE 'UTC';
  INSERT INTO stock_move_line SELECT * FROM l;
  DROP TABLE m; DROP TABLE l;

  -- 2) rebaseline line 303331 exists but state='cancel' (stock card reads done lines only) -> set done
  UPDATE stock_move_line SET state='done', write_date=now() AT TIME ZONE 'UTC'
   WHERE id=303331 AND move_id=332745 AND state='cancel' AND quantity=10 AND location_id=14 AND location_dest_id=8;
  GET DIAGNOSTICS n=ROW_COUNT;
  IF n<>1 THEN RAISE EXCEPTION 'rebaseline line 303331 not as expected'; END IF;
END \$\$;
\echo AFTER
SELECT * FROM pg_temp.st();
DO \$\$
BEGIN
  IF (SELECT v FROM pg_temp.st() WHERE what='ledger FG10 opening (<=cut)')<>0
     OR (SELECT v FROM pg_temp.st() WHERE what='ledger FG10 window')<>323
     OR (SELECT v FROM pg_temp.st() WHERE what='ledger FG10 total')<>323
     OR EXISTS (SELECT 1 FROM pg_temp.st() a JOIN snap b USING (what) WHERE a.what IN ('quant FG10','svl count','svl value') AND a.v IS DISTINCT FROM b.v)
  THEN RAISE EXCEPTION 'post-check failed'; END IF;
  RAISE NOTICE 'post-check ok: opening 0, window 323, total 323, quant+SVL unchanged';
END \$\$;
$END;
SQL
