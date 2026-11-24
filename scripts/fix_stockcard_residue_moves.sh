#!/usr/bin/env bash
# MOG_LIVE: buz_new_stock_card (move-line based) vs quant for the 'pre-cutoff residue fix' pairs (all except 504110001, done separately).
# Targets = pairs whose card qty gap (card - quant, warehouse internal locs) == -(sum of the pair's residue-layer qty), gap != 0.
# Per target: ONE done stock.move + ONE move line (wh lot_stock <-> Inventory adjustment, |gap| qty, dated 2026-03-30 16:59:59.999999,
# SQL-cloned from move 375009 so quants are NOT touched, no SVL created), and the residue SVL layer R is linked to it
# (stock_move_id, location_id=lot_stock). If a group-B value layer G (qty 0, no move, 'groupB ledger fix') exists for the pair,
# its value is merged into R and G deleted (per-pair SVL qty/value totals unchanged).
# Also repairs stale cloned fields on move 375009 (product_qty 122 -> 50, line quantity_product_uom 122 -> 50).
# Modes: check | dry (backup stock_move/_line/SVL, apply + post-check, ROLLBACK) | apply (COMMIT)
# Rollback: DELETE FROM stock_move_line WHERE reference LIKE 'STOCKCARD-FIX-%' AND move_id<>375009; DELETE FROM stock_move WHERE reference LIKE 'STOCKCARD-FIX-%' AND id<>375009;
#           + restore residue layers (stock_move_id/location_id NULL, value 0) and deleted G layers from the backup dump.
set -euo pipefail
MODE="${1:-check}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply" >&2; exit 2;; esac
REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'

BODY=$(cat <<'SQLEOF'
CREATE TEMP TABLE pair AS
SELECT s.product_id pid, s.warehouse_id wid, count(*) n_r, min(s.id) rid, sum(s.quantity) tq
FROM stock_valuation_layer s
WHERE s.quantity<>0 AND s.value=0 AND s.stock_move_id IS NULL AND s.product_id<>11535
  AND s.description ILIKE 'Reverse FIFO Reset Flush (pre-cutoff residue fix)%'
GROUP BY 1,2;
CREATE TEMP TABLE locs AS
SELECT p.pid, p.wid, array_agg(sl.id) ids FROM pair p JOIN stock_location sl ON sl.warehouse_id=p.wid AND sl.usage='internal' GROUP BY 1,2;
CREATE TEMP TABLE tg AS
SELECT p.pid, p.wid, p.rid, p.n_r, p.tq, pp.default_code code, sw.code whc, sw.lot_stock_id stk, pt.uom_id uom, cat.complete_name catname,
  (SELECT coalesce(sum(CASE WHEN ml.location_dest_id=ANY(l.ids) AND NOT ml.location_id=ANY(l.ids) THEN ml.quantity
                            WHEN ml.location_id=ANY(l.ids) AND NOT ml.location_dest_id=ANY(l.ids) THEN -ml.quantity ELSE 0 END),0)
     FROM stock_move_line ml WHERE ml.product_id=p.pid AND ml.state='done' AND (ml.location_id=ANY(l.ids) OR ml.location_dest_id=ANY(l.ids))) card_q,
  (SELECT coalesce(sum(q.quantity),0) FROM stock_quant q WHERE q.product_id=p.pid AND q.location_id=ANY(l.ids)) quant_q,
  (SELECT g.id FROM stock_valuation_layer g WHERE g.product_id=p.pid AND g.warehouse_id=p.wid AND g.quantity=0 AND g.stock_move_id IS NULL AND g.description LIKE 'Reverse FIFO Reset Flush (groupB ledger fix%' ORDER BY g.id LIMIT 1) gid,
  (SELECT g.value FROM stock_valuation_layer g WHERE g.product_id=p.pid AND g.warehouse_id=p.wid AND g.quantity=0 AND g.stock_move_id IS NULL AND g.description LIKE 'Reverse FIFO Reset Flush (groupB ledger fix%' ORDER BY g.id LIMIT 1) gval,
  (SELECT count(*) FROM stock_valuation_layer g WHERE g.product_id=p.pid AND g.warehouse_id=p.wid AND g.stock_move_id IS NULL AND g.description LIKE 'Reverse FIFO Reset Flush (groupB ledger fix%') n_g,
  (SELECT count(*) FROM stock_move m WHERE m.product_id=p.pid AND m.reference LIKE 'STOCKCARD-FIX-%') done_n,
  (SELECT round(sum(value),2) FROM stock_valuation_layer x WHERE x.product_id=p.pid AND x.warehouse_id=p.wid) svl_v,
  (SELECT sum(quantity) FROM stock_valuation_layer x WHERE x.product_id=p.pid AND x.warehouse_id=p.wid) svl_q
FROM pair p JOIN locs l ON l.pid=p.pid AND l.wid=p.wid
 JOIN product_product pp ON pp.id=p.pid JOIN product_template pt ON pt.id=pp.product_tmpl_id JOIN product_category cat ON cat.id=pt.categ_id
 JOIN stock_warehouse sw ON sw.id=p.wid;
ALTER TABLE tg ADD COLUMN gap numeric, ADD COLUMN ok boolean;
UPDATE tg SET gap=round(card_q-quant_q,4), ok=(abs((card_q-quant_q)+tq)<0.0001 AND abs(card_q-quant_q)>0.0001 AND n_r=1 AND n_g<=1 AND done_n=0 AND tq<>0);
\echo '== all pairs: ok = gap == -residue qty (targets) ; others are NOT touched'
SELECT code, whc, tq, card_q, quant_q, gap, gid, gval, ok FROM tg ORDER BY ok DESC, code, whc;
DELETE FROM tg WHERE NOT ok;
\echo '== targets'
SELECT count(*) targets, sum((gid IS NOT NULL)::int) with_groupB FROM tg;
SQLEOF
)

WRITE=$(cat <<'SQLEOF'
-- stale cloned fields of 375009
UPDATE stock_move SET product_qty=50 WHERE id=375009 AND product_qty<>50;
UPDATE stock_move_line SET quantity_product_uom=50 WHERE move_id=375009 AND quantity_product_uom<>50;
CREATE TEMP TABLE before AS SELECT t.pid, t.wid,
  (SELECT sum(quantity) FROM stock_valuation_layer x WHERE x.product_id=t.pid AND x.warehouse_id=t.wid) q,
  (SELECT round(sum(value),2) FROM stock_valuation_layer x WHERE x.product_id=t.pid AND x.warehouse_id=t.wid) v,
  (SELECT round(sum(value),2) FROM stock_valuation_layer x WHERE x.product_id=t.pid AND x.warehouse_id=t.wid AND COALESCE(accounting_date,create_date)>='2026-03-30 17:00') wv,
  (SELECT sum(quantity) FROM stock_valuation_layer x WHERE x.product_id=t.pid AND x.warehouse_id=t.wid AND x.location_id=t.stk) loc_q_before
FROM tg t;
CREATE TEMP TABLE nm AS SELECT tg.*, nextval(pg_get_serial_sequence('stock_move','id')) mid, nextval(pg_get_serial_sequence('stock_move_line','id')) lid,
  abs(gap) q, CASE WHEN gap>0 THEN stk ELSE 14 END src, CASE WHEN gap>0 THEN 14 ELSE stk END dst FROM tg;
INSERT INTO stock_move
SELECT (jsonb_populate_record(NULL::stock_move, (SELECT to_jsonb(s) FROM stock_move s WHERE s.id=375009) || jsonb_build_object(
  'id',mid,'product_id',pid,'product_uom',uom,'location_id',src,'location_dest_id',dst,'warehouse_id',wid,
  'name','Stock card correction '||code||' (SVL-only residue '||tq::text||')','reference','STOCKCARD-FIX-'||code||'-'||whc,
  'product_uom_qty',q,'product_qty',q,'quantity',q,
  'create_date',to_char(now() AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US'),'write_date',to_char(now() AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US')))).* FROM nm;
INSERT INTO stock_move_line
SELECT (jsonb_populate_record(NULL::stock_move_line, (SELECT to_jsonb(s) FROM stock_move_line s WHERE s.move_id=375009) || jsonb_build_object(
  'id',lid,'move_id',mid,'product_id',pid,'product_uom_id',uom,'location_id',src,'location_dest_id',dst,'product_category_name',catname,
  'reference','STOCKCARD-FIX-'||code||'-'||whc,'quantity',q,'quantity_product_uom',q,
  'create_date',to_char(now() AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US'),'write_date',to_char(now() AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US')))).* FROM nm;
-- link residue layer; merge groupB value
UPDATE stock_valuation_layer r SET stock_move_id=nm.mid, location_id=nm.stk,
  value=coalesce(nm.gval,0), unit_cost=CASE WHEN nm.gval IS NULL OR nm.tq=0 THEN r.unit_cost ELSE abs(nm.gval/nm.tq) END, write_date=now() AT TIME ZONE 'UTC'
FROM nm WHERE r.id=nm.rid;
DELETE FROM stock_valuation_layer WHERE id IN (SELECT gid FROM nm WHERE gid IS NOT NULL);
\echo '== post-check per target (card_q after == quant; SVL per-pair totals unchanged)'
CREATE TEMP TABLE po AS SELECT t.code, t.whc, t.pid, t.wid, t.quant_q,
  (SELECT coalesce(sum(CASE WHEN ml.location_dest_id=ANY(l.ids) AND NOT ml.location_id=ANY(l.ids) THEN ml.quantity
                            WHEN ml.location_id=ANY(l.ids) AND NOT ml.location_dest_id=ANY(l.ids) THEN -ml.quantity ELSE 0 END),0)
     FROM stock_move_line ml WHERE ml.product_id=t.pid AND ml.state='done' AND (ml.location_id=ANY(l.ids) OR ml.location_dest_id=ANY(l.ids))) card_q_after,
  (SELECT coalesce(sum(value),0) FROM stock_valuation_layer s WHERE s.product_id=t.pid AND s.location_id=ANY(l.ids) AND (COALESCE(s.accounting_date,s.create_date)<'2026-03-29 17:00' OR s.stock_move_id IS NOT NULL)) card_v_after,
  b.q bq, b.v bv, b.wv bwv, b.loc_q_before,
  (SELECT sum(quantity) FROM stock_valuation_layer x WHERE x.product_id=t.pid AND x.warehouse_id=t.wid) aq,
  (SELECT round(sum(value),2) FROM stock_valuation_layer x WHERE x.product_id=t.pid AND x.warehouse_id=t.wid) av,
  (SELECT round(sum(value),2) FROM stock_valuation_layer x WHERE x.product_id=t.pid AND x.warehouse_id=t.wid AND COALESCE(accounting_date,create_date)>='2026-03-30 17:00') awv,
  (SELECT sum(quantity) FROM stock_valuation_layer x WHERE x.product_id=t.pid AND x.warehouse_id=t.wid AND x.location_id=t.stk) loc_q_after,
  (SELECT coalesce(sum(q.quantity),0) FROM stock_quant q WHERE q.product_id=t.pid AND q.location_id=t.stk) quant_at_stk
FROM tg t JOIN locs l ON l.pid=t.pid AND l.wid=t.wid JOIN before b ON b.pid=t.pid AND b.wid=t.wid;
SELECT code, whc, quant_q, card_q_after, round(card_v_after,2) card_v_after, av svl_v, round(card_v_after-av,2) card_v_gap_after, bq, aq, bv, av, loc_q_before, loc_q_after, quant_at_stk FROM po ORDER BY code, whc;
DO $$
DECLARE bad int;
BEGIN
  SELECT count(*) INTO bad FROM po WHERE abs(card_q_after-quant_q)>0.0001 OR bq<>aq OR bv<>av OR bwv<>awv;
  IF bad<>0 THEN RAISE EXCEPTION 'post-check failed on % pairs', bad; END IF;
  IF (SELECT count(*) FROM stock_move WHERE reference LIKE 'STOCKCARD-FIX-%')<>(SELECT count(*) FROM tg)+1 THEN RAISE EXCEPTION 'move count'; END IF;
  RAISE NOTICE 'post-check ok: % targets, card qty == quant, per-pair SVL totals unchanged', (SELECT count(*) FROM tg);
END $$;
SQLEOF
)

if [ "$MODE" = check ]; then
  { printf 'BEGIN;\n%s\nROLLBACK;\n' "$BODY"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q"
  exit 0
fi
COMMIT_OR_ROLLBACK=$([ "$MODE" = apply ] && echo COMMIT || echo ROLLBACK)
STAMP=$(date +%Y%m%d_%H%M%S)
echo ">>> backup stock_move, stock_move_line, stock_valuation_layer (~/db_backups/scresidue_${STAMP}.dump)"
ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_move -t stock_move_line -t stock_valuation_layer MOG_LIVE -f ~/db_backups/scresidue_${STAMP}.dump && ls -l ~/db_backups/scresidue_${STAMP}.dump"
{ printf 'BEGIN;\n%s\n%s\n%s;\n' "$BODY" "$WRITE" "$COMMIT_OR_ROLLBACK"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q"
echo ">>> $MODE finished ($COMMIT_OR_ROLLBACK)"
