#!/usr/bin/env bash
# 403030003 @RM03/FXF stock card opening/balance 12 below imex/quant at cutoff 2026-03-30 17:00 UTC.
# Cause: BMV-0000484 (+35 RM02->FXF) and BROJ0006938/0006940 (-12 FXF->PD01) pre-cutoff; the 03-30 reset wiped 35 (quant)
# while the move ledger held 23 -> ledger at cutoff = -12 at FXF; imex/SVL window ignore it. 
# Fix: ONE no-quant / no-SVL mirror-pair move RM02/Stock -> RM03/FXF(1205) qty 12 (line-level residue RM02 +12 / FXF -12), dated 2026-03-30 16:59:59.999999.
# Usage: bash fix_stockcard_opening_403030003.sh check|dry|apply
#   check = read-only preconditions; dry = executes in a transaction then ROLLBACK; apply = pg_dump backup then COMMIT.
# Rollback after apply: DELETE FROM stock_move_line WHERE reference='STOCKCARD-OPENING-FIX-403030003';
#                       DELETE FROM stock_move WHERE reference='STOCKCARD-OPENING-FIX-403030003';
set -euo pipefail
MODE="${1:-check}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply" >&2; exit 2;; esac
REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'
CUT="2026-03-30 16:59:59.999999"
REF="STOCKCARD-OPENING-FIX-403030003"
CODE="403030003"

if [ "$MODE" = apply ]; then
  TS=$(date +%Y%m%d_%H%M%S)
  ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_quant -t stock_valuation_layer -t stock_move -t stock_move_line MOG_LIVE -f ~/db_backups/stockcard_opening_403030003_$TS.dump && ls -l ~/db_backups/stockcard_opening_403030003_$TS.dump"
fi
CHK=0; [ "$MODE" = check ] && CHK=1
END=ROLLBACK; [ "$MODE" = apply ] && END=COMMIT

ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -X -v ON_ERROR_STOP=1 -v check=$CHK -P pager=off" <<SQL
BEGIN;
CREATE TEMP TABLE pr AS
SELECT p.id pid, pt.uom_id uom, (SELECT id FROM stock_location WHERE complete_name='RM02/Stock' AND usage='internal') loc_src, 1205 loc_dst, 12::numeric q
FROM product_product p JOIN product_template pt ON pt.id=p.product_tmpl_id WHERE p.default_code='$CODE';

\echo '== ledger balance per internal location at cutoff end (before) =='
SELECT l.complete_name, sum(CASE WHEN ml.location_dest_id=l.id THEN ml.quantity ELSE -ml.quantity END) opening
FROM pr JOIN stock_move_line ml ON ml.product_id=pr.pid AND ml.state='done' AND ml.date<='2026-03-30 17:00'
JOIN stock_location l ON l.usage='internal' AND (l.id=ml.location_id OR l.id=ml.location_dest_id) AND NOT (ml.location_id=l.id AND ml.location_dest_id=l.id)
GROUP BY 1 HAVING abs(sum(CASE WHEN ml.location_dest_id=l.id THEN ml.quantity ELSE -ml.quantity END))>0.0001;

DO \$\$
DECLARE o numeric; n int; bad int;
BEGIN
  SELECT sum(CASE WHEN ml.location_dest_id=1205 THEN ml.quantity ELSE -ml.quantity END) INTO o
    FROM stock_move_line ml WHERE ml.product_id=(SELECT pid FROM pr) AND ml.state='done' AND ml.date<='2026-03-30 17:00'
     AND (ml.location_id=1205 OR ml.location_dest_id=1205) AND NOT (ml.location_id=1205 AND ml.location_dest_id=1205);
  IF o IS DISTINCT FROM -12 THEN RAISE EXCEPTION 'RM03/FXF opening is %, expected -12', o; END IF;
  SELECT count(*) INTO bad FROM (
    SELECT l.id FROM stock_move_line ml JOIN stock_location l ON l.usage='internal' AND (l.id=ml.location_id OR l.id=ml.location_dest_id) AND NOT (ml.location_id=l.id AND ml.location_dest_id=l.id)
    WHERE ml.product_id=(SELECT pid FROM pr) AND ml.state='done' AND ml.date<='2026-03-30 17:00' AND l.id<>1205
    GROUP BY l.id HAVING abs(sum(CASE WHEN ml.location_dest_id=l.id THEN ml.quantity ELSE -ml.quantity END))>0.0001) z;
  IF bad<>1 THEN RAISE EXCEPTION 'expected exactly 1 other residue row (RM02), got %', bad; END IF;
  SELECT count(*) INTO bad FROM (
    SELECT l.id FROM stock_move_line ml JOIN stock_location l ON l.usage='internal' AND (l.id=ml.location_id OR l.id=ml.location_dest_id) AND NOT (ml.location_id=l.id AND ml.location_dest_id=l.id)
    WHERE ml.product_id=(SELECT pid FROM pr) AND ml.state='done' AND ml.date<='2026-03-30 17:00' AND l.id=(SELECT loc_src FROM pr)
    GROUP BY l.id HAVING abs(sum(CASE WHEN ml.location_dest_id=l.id THEN ml.quantity ELSE -ml.quantity END)-12)<0.0001) z2;
  IF bad<>1 THEN RAISE EXCEPTION 'RM02/Stock opening is not +12'; END IF;
  SELECT count(*) INTO n FROM stock_move WHERE reference='$REF';
  IF n<>0 THEN RAISE EXCEPTION 'fix already applied'; END IF;
  SELECT count(*) INTO n FROM stock_move WHERE id IN (95893,95896) AND state='done' AND location_id=1205 AND quantity IN (7,5) AND date<='2026-03-30 17:00';
  IF n<>2 THEN RAISE EXCEPTION 'causal BROJ moves not as expected'; END IF;
END \$\$;
\\if :check
\\echo 'check ok (read-only, no insert)'
ROLLBACK;
\\q
\\endif
CREATE TEMP TABLE snap AS SELECT
  (SELECT round(sum(quantity),4) FROM stock_quant WHERE product_id IN (SELECT pid FROM pr)) q,
  (SELECT count(*) FROM stock_valuation_layer WHERE product_id IN (SELECT pid FROM pr)) c,
  (SELECT round(sum(value)::numeric,2) FROM stock_valuation_layer WHERE product_id IN (SELECT pid FROM pr)) v;

DO \$\$
DECLARE r record; mid int; bad int; q2 numeric; c2 int; v2 numeric;
BEGIN
  SELECT * INTO r FROM pr;
  CREATE TEMP TABLE m AS SELECT * FROM stock_move WHERE id=141826;
  UPDATE m SET id=nextval(pg_get_serial_sequence('stock_move','id')), product_id=r.pid, product_uom=r.uom,
    name='Stock card opening fix $CODE 1 (RM02/Stock -> RM03/FXF, 2026-03-30)',
    reference='$REF', location_id=r.loc_src, location_dest_id=r.loc_dst,
    product_qty=r.q, product_uom_qty=r.q, quantity=r.q, picked=true, state='done', is_inventory=false, is_done=true,
    date=TIMESTAMP '$CUT', weight=coalesce((SELECT weight FROM product_product WHERE id=r.pid),0)*r.q,
    create_date=now() AT TIME ZONE 'UTC', write_date=now() AT TIME ZONE 'UTC';
  INSERT INTO stock_move SELECT * FROM m;
  SELECT id INTO mid FROM m;
  CREATE TEMP TABLE l AS SELECT * FROM stock_move_line WHERE id=131638;
  UPDATE l SET id=nextval(pg_get_serial_sequence('stock_move_line','id')), move_id=mid, product_id=r.pid, product_uom_id=r.uom,
    location_id=r.loc_src, location_dest_id=r.loc_dst, quantity=r.q, quantity_product_uom=r.q, state='done', reference='$REF', picked=true,
    date=TIMESTAMP '$CUT', create_date=now() AT TIME ZONE 'UTC', write_date=now() AT TIME ZONE 'UTC';
  INSERT INTO stock_move_line SELECT * FROM l;
  DROP TABLE m; DROP TABLE l;

  SELECT count(*) INTO bad FROM (
    SELECT l2.id FROM stock_move_line ml JOIN stock_location l2 ON l2.usage='internal' AND (l2.id=ml.location_id OR l2.id=ml.location_dest_id) AND NOT (ml.location_id=l2.id AND ml.location_dest_id=l2.id)
    WHERE ml.product_id=r.pid AND ml.state='done' AND ml.date<='2026-03-30 17:00'
    GROUP BY l2.id HAVING abs(sum(CASE WHEN ml.location_dest_id=l2.id THEN ml.quantity ELSE -ml.quantity END))>0.0001) z;
  SELECT round(sum(quantity),4) INTO q2 FROM stock_quant WHERE product_id=r.pid;
  SELECT count(*), round(sum(value)::numeric,2) INTO c2, v2 FROM stock_valuation_layer WHERE product_id=r.pid;
  IF bad<>0 OR q2 IS DISTINCT FROM (SELECT q FROM snap) OR c2<>(SELECT c FROM snap) OR v2 IS DISTINCT FROM (SELECT v FROM snap) THEN
    RAISE EXCEPTION 'post-check failed: residual rows %, quant % vs %, svl %/% vs %/%', bad, q2, (SELECT q FROM snap), c2, v2, (SELECT c FROM snap), (SELECT v FROM snap);
  END IF;
  RAISE NOTICE 'post-check ok: opening 0 at RM02 + FXF, quants + SVL unchanged';
END \$\$;

\echo '== inserted move =='
SELECT m.id, m.date, sl.complete_name src, dl.complete_name dst, m.quantity
FROM stock_move m JOIN stock_location sl ON sl.id=m.location_id JOIN stock_location dl ON dl.id=m.location_dest_id WHERE m.reference='$REF';
$END;
SQL
