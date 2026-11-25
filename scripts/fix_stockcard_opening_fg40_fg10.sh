#!/usr/bin/env bash
# Stock card opening residue at cutoff for backdated FG40<->FG10 transfers (MV-01094xx) created AFTER the 2026-03-30 reset.
# Ledger (stock_move_line) at cutoff end: FG10 +q / FG40 -q while quant, SVL window and imex Initial are 0.
# Fix: ONE no-quant / no-SVL internal move  (+side -> -side) qty q, dated 2026-03-30 16:59:59.999999 (before the report
# window start 17:00 UTC, so it only changes the stock card opening; quants and SVL untouched).
# Default products = clean mirror pairs only. WB0004A100 (FG10 +10, FG40 side 0) is NOT a mirror pair -> excluded.
# Usage:  CODES="FU0033FC1560" bash fix_stockcard_opening_fg40_fg10.sh check|dry|apply
#   check = read-only preconditions + proposal; dry = executes in a transaction then ROLLBACK; apply = pg_dump backup then COMMIT.
# Rollback after apply: DELETE FROM stock_move_line WHERE reference='STOCKCARD-OPENING-FIX-20260330';
#                       DELETE FROM stock_move WHERE reference='STOCKCARD-OPENING-FIX-20260330';
# Pilot first (one product), verify stock card + imex in UI, then run the rest.
set -euo pipefail
MODE="${1:-check}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: CODES='A B' $0 check|dry|apply" >&2; exit 2;; esac
CODES="${CODES:-FU0033FC1560 MA332B1101 MO006901110}"
CODE_VALUES=$(for c in $CODES; do printf "('%s')," "$c"; done); CODE_VALUES="${CODE_VALUES%,}"
REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'
CUT="2026-03-30 16:59:59.999999"
REF="STOCKCARD-OPENING-FIX-20260330"

if [ "$MODE" = apply ]; then
  TS=$(date +%Y%m%d_%H%M%S)
  ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_quant -t stock_valuation_layer -t stock_move -t stock_move_line MOG_LIVE -f ~/db_backups/stockcard_opening_fg40_fg10_$TS.dump && ls -l ~/db_backups/stockcard_opening_fg40_fg10_$TS.dump"
fi
END=ROLLBACK; [ "$MODE" = apply ] && END=COMMIT

ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -X -v ON_ERROR_STOP=1 -P pager=off" <<SQL
BEGIN;
CREATE TEMP TABLE codes(code text);
INSERT INTO codes VALUES $CODE_VALUES;

-- ledger balance per internal location at cutoff end (stock card opening basis)
CREATE TEMP TABLE bal AS
SELECT p.id pid, p.default_code code, l.id loc, l.complete_name lname, pt.uom_id uom,
  sum(CASE WHEN ml.location_dest_id=l.id THEN ml.quantity ELSE -ml.quantity END) opening
FROM codes c JOIN product_product p ON p.default_code=c.code JOIN product_template pt ON pt.id=p.product_tmpl_id
JOIN stock_move_line ml ON ml.product_id=p.id AND ml.state='done' AND ml.date <= '2026-03-30 17:00'
JOIN stock_location l ON l.usage='internal' AND (l.id=ml.location_id OR l.id=ml.location_dest_id) AND NOT (ml.location_id=l.id AND ml.location_dest_id=l.id)
GROUP BY 1,2,3,4,5 HAVING abs(sum(CASE WHEN ml.location_dest_id=l.id THEN ml.quantity ELSE -ml.quantity END))>0.0001;

-- one row per product: +side (src) and -side (dst)
CREATE TEMP TABLE pr AS
SELECT a.pid, a.code, a.uom, a.loc loc_src, b.loc loc_dst, a.lname sname, b.lname dname, a.opening q
FROM bal a JOIN bal b ON b.pid=a.pid AND a.opening>0 AND b.opening=-a.opening;

\echo '== proposal (src = location with +residue, dst = location with -residue) =='
SELECT code, sname src, dname dst, q FROM pr ORDER BY code;
\echo '== all residual rows of requested codes (every row must be in a pair above, nothing else) =='
SELECT code, lname, opening FROM bal ORDER BY code, lname;

DO \$\$
DECLARE ncodes int; npairs int; nrows int; npairrows int; bad int; done_before int;
BEGIN
  SELECT count(*) INTO ncodes FROM codes;
  SELECT count(*) INTO npairs FROM pr;
  SELECT count(*) INTO nrows FROM bal;
  IF npairs<>ncodes THEN RAISE EXCEPTION 'only %/% requested products form a mirror pair', npairs, ncodes; END IF;
  IF nrows<>2*npairs THEN RAISE EXCEPTION 'extra residual rows (% rows for % pairs) - not a clean pair', nrows, npairs; END IF;
  SELECT count(*) INTO bad FROM pr WHERE sname NOT IN ('FG10/Stock','FG40/Stock') OR dname NOT IN ('FG10/Stock','FG40/Stock');
  IF bad<>0 THEN RAISE EXCEPTION 'pair outside FG10/FG40'; END IF;
  SELECT count(*) INTO done_before FROM stock_move WHERE reference='$REF' AND product_id IN (SELECT pid FROM pr);
  IF done_before<>0 THEN RAISE EXCEPTION 'fix already applied for % products', done_before; END IF;
  -- the causal pattern: a pre-cutoff-dated MV- transfer created after the cutoff must exist
  SELECT count(*) INTO bad FROM pr WHERE NOT EXISTS (SELECT 1 FROM stock_move m WHERE m.product_id=pr.pid AND m.state='done'
     AND m.reference LIKE 'MV-%' AND m.date<='2026-03-30 17:00' AND m.create_date>'2026-03-30 17:00');
  IF bad<>0 THEN RAISE EXCEPTION '% products lack a late-created MV- transfer', bad; END IF;
END \$\$;

CREATE TEMP TABLE snap AS SELECT
  (SELECT round(sum(quantity),4) FROM stock_quant WHERE product_id IN (SELECT pid FROM pr)) q,
  (SELECT count(*) FROM stock_valuation_layer WHERE product_id IN (SELECT pid FROM pr)) c,
  (SELECT round(sum(value)::numeric,2) FROM stock_valuation_layer WHERE product_id IN (SELECT pid FROM pr)) v;

DO \$\$
DECLARE r record; mid int; bad int; nm int; q2 numeric; c2 int; v2 numeric;
BEGIN
  FOR r IN SELECT * FROM pr ORDER BY code LOOP
    DROP TABLE IF EXISTS m; DROP TABLE IF EXISTS l;
    CREATE TEMP TABLE m AS SELECT * FROM stock_move WHERE id=141826;
    UPDATE m SET id=nextval(pg_get_serial_sequence('stock_move','id')), product_id=r.pid, product_uom=r.uom,
      name='Stock card opening fix '||r.code||' '||r.q||' ('||r.sname||' -> '||r.dname||', 2026-03-30)',
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
  END LOOP;

  -- post-check: opening 0 at both locations, quants + SVL untouched
  SELECT count(*) INTO bad FROM (
    SELECT pz.pid, x.loc, sum(CASE WHEN ml.location_dest_id=x.loc THEN ml.quantity ELSE -ml.quantity END) o
    FROM pr pz CROSS JOIN LATERAL (VALUES (pz.loc_src),(pz.loc_dst)) x(loc)
    JOIN stock_move_line ml ON ml.product_id=pz.pid AND ml.state='done' AND ml.date<='2026-03-30 17:00'
      AND (ml.location_id=x.loc OR ml.location_dest_id=x.loc) AND NOT (ml.location_id=x.loc AND ml.location_dest_id=x.loc)
    GROUP BY 1,2 HAVING abs(sum(CASE WHEN ml.location_dest_id=x.loc THEN ml.quantity ELSE -ml.quantity END))>0.0001) z;
  SELECT count(*) INTO nm FROM stock_move WHERE reference='$REF' AND product_id IN (SELECT pid FROM pr);
  SELECT round(sum(quantity),4) INTO q2 FROM stock_quant WHERE product_id IN (SELECT pid FROM pr);
  SELECT count(*), round(sum(value)::numeric,2) INTO c2, v2 FROM stock_valuation_layer WHERE product_id IN (SELECT pid FROM pr);
  IF bad<>0 OR nm<>(SELECT count(*) FROM pr) OR q2 IS DISTINCT FROM (SELECT q FROM snap) OR c2<>(SELECT c FROM snap) OR v2 IS DISTINCT FROM (SELECT v FROM snap) THEN
    RAISE EXCEPTION 'post-check failed: residual rows %, moves %, quant % vs %, svl %/% vs %/%', bad, nm, q2, (SELECT q FROM snap), c2, v2, (SELECT c FROM snap), (SELECT v FROM snap);
  END IF;
  RAISE NOTICE 'post-check ok: % moves inserted, opening residue 0 at all locations, quants + SVL unchanged', nm;
END \$\$;

\echo '== inserted moves =='
SELECT m.id, p.default_code, m.date, sl.complete_name src, dl.complete_name dst, m.quantity
FROM stock_move m JOIN product_product p ON p.id=m.product_id JOIN stock_location sl ON sl.id=m.location_id JOIN stock_location dl ON dl.id=m.location_dest_id
WHERE m.reference='$REF' ORDER BY p.default_code;
$( [ "$MODE" = check ] && echo ROLLBACK || echo "$END" );
SQL
