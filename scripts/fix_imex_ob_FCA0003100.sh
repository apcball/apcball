#!/usr/bin/env bash
# FCA0003100: accounting OB count is FG10/Stock=149 and RM01/RD=3, but the MOGEN_OB reseed docs carry 152 / 0.
# The G2 ledger-fix SVL pair (303362 FG10 +3 / 303369 RM01 -3, dated 03-31 01:00) then moves the ending balance to 152 / 0.
# Fix IN the OB documents only (same rule as fix_imex_ob_qty.sh):
#   FG10/Stock  OB line 150464 (move 160654, FG10/FG10/00053)  144 -> 141   (delta -3)
#   RM01/RD     OB line 195949 (move 206173, RM01/RM01/00121)    0 ->   3   (delta +3)
# Only stock_move.product_uom_qty/product_qty/quantity and stock_move_line.quantity/quantity_product_uom change.
# quants, SVL, FIFO queue, journal entries are NOT touched (post-check asserts it).
# Modes: check (preconditions, rolls back) | dry (backup, update + post-checks, ROLLBACK) | apply (COMMIT)
set -euo pipefail
MODE="${1:-check}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply" >&2; exit 2;; esac
REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'

BODY=$(cat <<'SQLEOF'
CREATE TEMP TABLE chg(mlid int, mvid int, delta numeric, exp_q numeric, exp_loc int);
INSERT INTO chg VALUES (150464,160654,-3,144,8),(195949,206173,3,0,1201);
\echo '== current state of the 2 OB lines + their moves'
SELECT c.mlid, ml.state, ml.date, ml.reference, ml.location_dest_id, ml.quantity, ml.quantity_product_uom, ml.product_id,
       m.id mvid, m.state mstate, m.product_uom_qty, m.product_qty, m.quantity mq, m.product_id mpid, m.picking_id
FROM chg c JOIN stock_move_line ml ON ml.id=c.mlid JOIN stock_move m ON m.id=ml.move_id ORDER BY c.mlid;
\echo '== preconditions that FAIL (expect none)'
SELECT c.mlid, 'precondition' FROM chg c JOIN stock_move_line ml ON ml.id=c.mlid JOIN stock_move m ON m.id=ml.move_id
 JOIN product_product p ON p.id=ml.product_id
 WHERE NOT (p.default_code='FCA0003100' AND ml.move_id=c.mvid AND ml.state='done' AND m.state='done'
   AND ml.location_dest_id=c.exp_loc AND ml.quantity=c.exp_q AND ml.quantity_product_uom=c.exp_q
   AND m.quantity=c.exp_q AND m.product_qty=c.exp_q AND m.product_uom_qty=c.exp_q
   AND ml.date>='2026-03-31 00:50' AND ml.date<'2026-03-31 01:00' AND ml.reference NOT LIKE 'IMEX%');
DO $$
DECLARE bad int;
BEGIN
  IF (SELECT count(*) FROM chg c JOIN stock_move_line ml ON ml.id=c.mlid)<>2 THEN RAISE EXCEPTION 'OB lines not found'; END IF;
  SELECT count(*) INTO bad FROM chg c JOIN stock_move_line ml ON ml.id=c.mlid JOIN stock_move m ON m.id=ml.move_id
   JOIN product_product p ON p.id=ml.product_id
   WHERE NOT (p.default_code='FCA0003100' AND ml.move_id=c.mvid AND ml.state='done' AND m.state='done'
     AND ml.location_dest_id=c.exp_loc AND ml.quantity=c.exp_q AND ml.quantity_product_uom=c.exp_q
     AND m.quantity=c.exp_q AND m.product_qty=c.exp_q AND m.product_uom_qty=c.exp_q
     AND ml.date>='2026-03-31 00:50' AND ml.date<'2026-03-31 01:00' AND ml.reference NOT LIKE 'IMEX%');
  IF bad<>0 THEN RAISE EXCEPTION 'precondition failed on % lines', bad; END IF;
  IF (SELECT sum(delta) FROM chg)<>0 THEN RAISE EXCEPTION 'delta not balanced'; END IF;
END $$;
SQLEOF
)

WRITE=$(cat <<'SQLEOF'
CREATE TEMP TABLE qsum AS SELECT round(sum(quantity),4) q FROM stock_quant WHERE product_id=1402;
CREATE TEMP TABLE svlsum AS SELECT count(*) c, round(sum(value)::numeric,2) v, round(sum(quantity),4) q FROM stock_valuation_layer WHERE product_id=1402;
\echo '== reverse statements (save these):'
SELECT format('UPDATE stock_move_line SET quantity=quantity-(%s), quantity_product_uom=quantity_product_uom-(%s) WHERE id=%s; UPDATE stock_move SET product_uom_qty=product_uom_qty-(%s), product_qty=product_qty-(%s), quantity=quantity-(%s) WHERE id=%s;', delta, delta, mlid, delta, delta, delta, mvid) AS reverse_sql FROM chg ORDER BY mlid;
UPDATE stock_move m SET product_uom_qty=m.product_uom_qty+c.delta, product_qty=m.product_qty+c.delta, quantity=m.quantity+c.delta, write_date=now() AT TIME ZONE 'UTC'
 FROM chg c WHERE m.id=c.mvid;
UPDATE stock_move_line ml SET quantity=ml.quantity+c.delta, quantity_product_uom=ml.quantity_product_uom+c.delta, write_date=now() AT TIME ZONE 'UTC'
 FROM chg c WHERE ml.id=c.mlid;
\echo '== OB totals after (expect FG10/Stock 149, RM01/RD 3)'
SELECT ml.location_dest_id, sum(ml.quantity) ob_qty FROM stock_move_line ml JOIN stock_picking pk ON pk.id=ml.picking_id JOIN res_partner pt ON pt.id=pk.partner_id
 WHERE ml.product_id=1402 AND ml.state='done' AND ml.date>='2026-03-31 00:50' AND ml.date<'2026-03-31 01:00' AND pt.name='MOGEN_OB' AND ml.location_dest_id IN (8,1201) GROUP BY 1 ORDER BY 1;
DO $$
DECLARE fg numeric; rd numeric; mv_bad int; q2 numeric; c2 int; v2 numeric; s2 numeric;
BEGIN
  SELECT coalesce(sum(ml.quantity),0) INTO fg FROM stock_move_line ml JOIN stock_picking pk ON pk.id=ml.picking_id JOIN res_partner pt ON pt.id=pk.partner_id
   WHERE ml.product_id=1402 AND ml.state='done' AND ml.date>='2026-03-31 00:50' AND ml.date<'2026-03-31 01:00' AND pt.name='MOGEN_OB' AND ml.location_dest_id=8;
  SELECT coalesce(sum(ml.quantity),0) INTO rd FROM stock_move_line ml JOIN stock_picking pk ON pk.id=ml.picking_id JOIN res_partner pt ON pt.id=pk.partner_id
   WHERE ml.product_id=1402 AND ml.state='done' AND ml.date>='2026-03-31 00:50' AND ml.date<'2026-03-31 01:00' AND pt.name='MOGEN_OB' AND ml.location_dest_id=1201;
  SELECT count(*) INTO mv_bad FROM chg c JOIN stock_move_line ml ON ml.id=c.mlid JOIN stock_move m ON m.id=ml.move_id
   WHERE m.quantity<>ml.quantity OR m.product_qty<>ml.quantity OR m.product_uom_qty<>ml.quantity OR ml.quantity<>ml.quantity_product_uom OR ml.quantity<0;
  SELECT round(sum(quantity),4) INTO q2 FROM stock_quant WHERE product_id=1402;
  SELECT count(*), round(sum(value)::numeric,2), round(sum(quantity),4) INTO c2, v2, s2 FROM stock_valuation_layer WHERE product_id=1402;
  IF fg<>149 OR rd<>3 OR mv_bad<>0 OR q2 IS DISTINCT FROM (SELECT q FROM qsum) OR c2<>(SELECT c FROM svlsum) OR v2 IS DISTINCT FROM (SELECT v FROM svlsum) OR s2 IS DISTINCT FROM (SELECT q FROM svlsum) THEN
    RAISE EXCEPTION 'post-check failed: FG10 %, RD %, move/line mismatch %, quant %, svl % / % / %', fg, rd, mv_bad, q2, c2, v2, s2;
  END IF;
  RAISE NOTICE 'post-check ok: OB FG10 149, RM01/RD 3, quants and SVL unchanged';
END $$;
SQLEOF
)

if [ "$MODE" = check ]; then
  { printf 'BEGIN;\n%s\nROLLBACK;\n' "$BODY"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q"
  echo "== check ok (no failing rows listed above)"
  exit 0
fi
COMMIT_OR_ROLLBACK=$([ "$MODE" = apply ] && echo COMMIT || echo ROLLBACK)
STAMP=$(date +%Y%m%d_%H%M%S)
echo ">>> backup stock_move + stock_move_line on mog-prod (~/db_backups/imex_ob_FCA0003100_${STAMP}.dump)"
ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_move -t stock_move_line MOG_LIVE -f ~/db_backups/imex_ob_FCA0003100_${STAMP}.dump && ls -l ~/db_backups/imex_ob_FCA0003100_${STAMP}.dump"
{ printf 'BEGIN;\n%s\n%s\n%s;\n' "$BODY" "$WRITE" "$COMMIT_OR_ROLLBACK"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q"
echo ">>> $MODE finished ($COMMIT_OR_ROLLBACK)"
