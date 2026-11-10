#!/usr/bin/env bash
# Part 2 of fix_imex_zero_line_moves_qc_tci.sh (applied 2026-11-10): same defect at RM01/Stock and FG10/Stock.
# imex falls back to the move HEADER qty when a done move has no move line with quantity<>0. 49 such zero-line moves
# (UB unbuilds 26, POJ 21, LOJ 1, ROJ0132986 1) touch RM01/Stock / FG10/Stock; quants never moved, so imex Initial = -header qty
# (RM01/Stock -1,073 on 19 pairs, FG10/Stock -73 on 21 pairs).
# Option 1: set product_qty / product_uom_qty / quantity of these moves to 0. SVL layers NOT touched (98 layers, net qty 0, net value -291.40 -> tell accounting). Quants untouched.
# Not covered (quant-side, need count): LTL12010 FG10 -1, MO010S101 FG10 -1; service SER0003R0010000.
# Modes: check | dry (backup, update, post-checks, ROLLBACK) | apply (COMMIT)
# Reverse after apply: the script prints "UPDATE ... FROM (VALUES ...)" with the original qtys (save them) and the backup dump holds stock_move.
#   Moves are tagged stock_move.backdate_remark='zero-line qty zeroed 2026-11-10 p2'.
set -euo pipefail
MODE="${1:-check}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply" >&2; exit 2;; esac
REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'
BODY=$(cat <<'SQLEOF'
CREATE FUNCTION pg_temp.initial(p int, loc int) RETURNS numeric LANGUAGE sql AS $f$
 SELECT coalesce((SELECT sum(quantity) FROM stock_quant WHERE product_id=p AND location_id=loc),0) - coalesce((
  SELECT sum(CASE WHEN ldst=loc THEN q ELSE 0 END)-sum(CASE WHEN lsrc=loc THEN q ELSE 0 END) FROM (
   SELECT sml.location_id lsrc, sml.location_dest_id ldst, sml.quantity_product_uom q FROM stock_move m JOIN stock_move_line sml ON sml.move_id=m.id
     WHERE m.product_id=p AND m.state='done' AND m.date>='2026-03-30 17:00' AND sml.quantity<>0 AND loc IN (sml.location_id, sml.location_dest_id)
   UNION ALL
   SELECT m.location_id, m.location_dest_id, m.product_qty FROM stock_move m WHERE m.product_id=p AND m.state='done' AND m.date>='2026-03-30 17:00'
     AND loc IN (m.location_id, m.location_dest_id) AND NOT EXISTS (SELECT 1 FROM stock_move_line x WHERE x.move_id=m.id AND x.quantity<>0)) t),0) $f$;
CREATE TEMP TABLE tgt AS
SELECT m.id mid, m.product_id pid, m.product_qty, m.product_uom_qty, m.quantity, m.location_id, m.location_dest_id, m.reference
FROM stock_move m
WHERE m.state='done' AND m.date>='2026-03-30 17:00' AND m.product_qty>0
  AND NOT EXISTS (SELECT 1 FROM stock_move_line x WHERE x.move_id=m.id AND x.quantity<>0)
  AND EXISTS (SELECT 1 FROM stock_location l WHERE l.id IN (m.location_id,m.location_dest_id) AND l.usage='internal' AND (l.complete_name LIKE '%RM01/Stock' OR l.complete_name LIKE '%FG10/Stock'))
  AND (m.reference LIKE 'UB/%' OR m.reference LIKE 'LOJ%' OR m.reference LIKE 'POJ%' OR m.reference LIKE 'ROJ%')
  AND m.reference NOT LIKE 'IMEX-REBASELINE%';
CREATE TEMP TABLE pairs AS
SELECT DISTINCT t.pid, l.id lid FROM tgt t JOIN stock_location l ON l.id IN (t.location_id,t.location_dest_id) AND l.usage='internal' AND (l.complete_name LIKE '%RM01/Stock' OR l.complete_name LIKE '%FG10/Stock');
CREATE TEMP TABLE before AS SELECT p.pid, p.lid, pg_temp.initial(p.pid,p.lid) init FROM pairs p;
CREATE TEMP TABLE chk AS SELECT
  (SELECT count(*) FROM tgt) n_moves,
  (SELECT count(*) FROM pairs) n_pairs,
  (SELECT count(*) FROM tgt WHERE product_qty<>product_uom_qty) uom_diff,
  (SELECT count(*) FROM tgt t WHERE NOT EXISTS (SELECT 1 FROM stock_valuation_layer v WHERE v.stock_move_id=t.mid)) no_svl,
  (SELECT count(*) FROM stock_move WHERE backdate_remark='zero-line qty zeroed 2026-11-10 p2') already;
\echo '== preconditions (expect 49 moves, 0 uom_diff, 0 no_svl, 0 already; 40 pairs with Initial<>0)'
SELECT * FROM chk;
\echo '== internal-pair Initial before (RM01/Stock and FG10/Stock), sum'
SELECT l.complete_name loc, count(*) FILTER (WHERE init<>0) nonzero, sum(init) FROM before b JOIN stock_location l ON l.id=b.lid GROUP BY 1;
DO $$ BEGIN
  IF (SELECT n_moves FROM chk)<>49 OR (SELECT count(*) FROM before WHERE init<>0)<>40 OR (SELECT uom_diff FROM chk)<>0 OR (SELECT no_svl FROM chk)<>0 OR (SELECT already FROM chk)<>0 THEN RAISE EXCEPTION 'preconditions failed'; END IF;
END $$;
SQLEOF
)
WRITE=$(cat <<'SQLEOF'
CREATE TEMP TABLE svl_before AS SELECT count(*) c, round(sum(quantity),4) q, round(sum(value)::numeric,2) v FROM stock_valuation_layer WHERE stock_move_id IN (SELECT mid FROM tgt);
CREATE TEMP TABLE quant_before AS SELECT round(sum(quantity),4) q, count(*) c FROM stock_quant;
\echo '== reverse statements (save these)'
SELECT format('UPDATE stock_move SET product_qty=%s, product_uom_qty=%s, quantity=%s, backdate_remark=NULL WHERE id=%s;', product_qty, product_uom_qty, quantity, mid) FROM tgt ORDER BY mid;
UPDATE stock_move SET product_qty=0, product_uom_qty=0, quantity=0, backdate_remark='zero-line qty zeroed 2026-11-10 p2', write_date=now() AT TIME ZONE 'UTC' WHERE id IN (SELECT mid FROM tgt);
\echo '== Initial after, sum per location (expect 0 nonzero)'
CREATE TEMP TABLE after AS SELECT p.pid, p.lid, pg_temp.initial(p.pid,p.lid) init FROM pairs p;
SELECT l.complete_name loc, count(*) FILTER (WHERE init<>0) nonzero, sum(init) FROM after a JOIN stock_location l ON l.id=a.lid GROUP BY 1;
DO $$ DECLARE c2 int; q2 numeric; v2 numeric; qq numeric; qc int;
BEGIN
  SELECT count(*), round(sum(quantity),4), round(sum(value)::numeric,2) INTO c2,q2,v2 FROM stock_valuation_layer WHERE stock_move_id IN (SELECT mid FROM tgt);
  SELECT round(sum(quantity),4), count(*) INTO qq, qc FROM stock_quant;
  IF (SELECT count(*) FROM after WHERE init<>0)<>0 THEN RAISE EXCEPTION 'Initial still nonzero for % pairs', (SELECT count(*) FROM after WHERE init<>0); END IF;
  IF c2<>(SELECT c FROM svl_before) OR q2 IS DISTINCT FROM (SELECT q FROM svl_before) OR v2 IS DISTINCT FROM (SELECT v FROM svl_before) THEN RAISE EXCEPTION 'SVL changed'; END IF;
  IF qq IS DISTINCT FROM (SELECT q FROM quant_before) OR qc<>(SELECT c FROM quant_before) THEN RAISE EXCEPTION 'quant changed'; END IF;
  RAISE NOTICE 'post-check ok: 49 moves zeroed, touched pairs Initial=0, SVL (% layers, net value %) and quants unchanged', c2, v2;
END $$;
SQLEOF
)
if [ "$MODE" = check ]; then
  { printf 'BEGIN;\n%s\nROLLBACK;\n' "$BODY"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q"; echo "== check ok"; exit 0
fi
COMMIT_OR_ROLLBACK=$([ "$MODE" = apply ] && echo COMMIT || echo ROLLBACK)
STAMP=$(date +%Y%m%d_%H%M%S)
echo ">>> backup stock_move on mog-prod (~/db_backups/imex_zl_stock_p2_${STAMP}.dump)"
ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_move MOG_LIVE -f ~/db_backups/imex_zl_stock_p2_${STAMP}.dump && ls -l ~/db_backups/imex_zl_stock_p2_${STAMP}.dump"
{ printf 'BEGIN;\n%s\n%s\n%s;\n' "$BODY" "$WRITE" "$COMMIT_OR_ROLLBACK"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q" | tee /tmp/imex_zl_stock_p2_${STAMP}.out | grep -v '^UPDATE stock_move SET product_qty' || true
echo ">>> $MODE finished ($COMMIT_OR_ROLLBACK); full output (incl. reverse stmts) /tmp/imex_zl_stock_p2_${STAMP}.out"
