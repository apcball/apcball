#!/usr/bin/env bash
# PILOT (user 2026-11-09): FCA0003100 (product 1402). The MOGEN_OB docs are correct; imex Initial plugs are fixed by moving the
# excess quant to where the documents say it is:  FG10/Stock (loc 8) has +3 more than OB+moves, RM01/RD (loc 1201) has -3.
#   * stock_quant: FG10/Stock -3; RM01/RD +3 (new quant record cloned from the FG10 one, reserved 0). Total quantity unchanged.
#   * SVL: delete the 2 G2 correction layers of this product (303362 FG10 +3/+1,325.21 and 303369 RM01 -3/-1,325.21), so the
#     ledger equals OB + moves = new quant (FG10 322-ish, RM01 3). Value net 0.
# No stock_move / stock_move_line / OB change. Modes: check | dry (backup, change, post-checks, ROLLBACK) | apply (COMMIT)
# Reverse after apply: UPDATE stock_quant SET quantity=quantity+3 WHERE product_id=1402 AND location_id=8;
#   DELETE FROM stock_quant WHERE product_id=1402 AND location_id=1201 AND quantity=3 AND in_date=(SELECT in_date FROM stock_quant WHERE product_id=1402 AND location_id=8);
#   and re-insert the two G2 layers (backup dump has them): scripts/fix_G2_flush_pairs.sh apply FCA0003100-only is NOT available - restore rows from the svl backup.
set -euo pipefail
MODE="${1:-check}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply" >&2; exit 2;; esac
REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'
BODY=$(cat <<'SQLEOF'
CREATE FUNCTION pg_temp.initial(loc int) RETURNS numeric LANGUAGE sql AS $f$
 SELECT coalesce((SELECT sum(quantity) FROM stock_quant WHERE product_id=1402 AND location_id=loc),0) - coalesce((
  SELECT sum(CASE WHEN ldst=loc THEN q ELSE 0 END)-sum(CASE WHEN lsrc=loc THEN q ELSE 0 END) FROM (
   SELECT sml.location_id lsrc, sml.location_dest_id ldst, sml.quantity_product_uom q FROM stock_move m JOIN stock_move_line sml ON sml.move_id=m.id
     WHERE m.product_id=1402 AND m.state='done' AND m.date>='2026-03-30 17:00' AND sml.quantity<>0 AND loc IN (sml.location_id, sml.location_dest_id)
   UNION ALL
   SELECT m.location_id, m.location_dest_id, m.product_qty FROM stock_move m WHERE m.product_id=1402 AND m.state='done' AND m.date>='2026-03-30 17:00'
     AND loc IN (m.location_id, m.location_dest_id) AND NOT EXISTS (SELECT 1 FROM stock_move_line x WHERE x.move_id=m.id AND x.quantity<>0)) t),0) $f$;
\echo '== preconditions: Initial FG10/Stock +3, RM01/RD -3, FG10 quant - reserved >= 3, no RM01/RD quant, 2 G2 layers'
SELECT pg_temp.initial(8) init_fg10, pg_temp.initial(1201) init_rm01rd,
  (SELECT quantity FROM stock_quant WHERE product_id=1402 AND location_id=8) q_fg10, (SELECT reserved_quantity FROM stock_quant WHERE product_id=1402 AND location_id=8) res_fg10,
  (SELECT count(*) FROM stock_quant WHERE product_id=1402 AND location_id=1201) rd_quants,
  (SELECT count(*) FROM stock_valuation_layer WHERE id IN (303362,303369) AND product_id=1402 AND description LIKE 'Reverse FIFO Reset Flush (G2%') g2_layers;
DO $$ BEGIN
  IF pg_temp.initial(8)<>3 OR pg_temp.initial(1201)<>-3 THEN RAISE EXCEPTION 'Initial not +3 / -3'; END IF;
  IF (SELECT count(*) FROM stock_quant WHERE product_id=1402 AND location_id=8)<>1 OR (SELECT quantity-reserved_quantity FROM stock_quant WHERE product_id=1402 AND location_id=8)<3 THEN RAISE EXCEPTION 'FG10 quant missing or reserved too high'; END IF;
  IF (SELECT count(*) FROM stock_quant WHERE product_id=1402 AND location_id=1201)<>0 THEN RAISE EXCEPTION 'RM01/RD quant already exists'; END IF;
  IF (SELECT count(*) FROM stock_valuation_layer WHERE id IN (303362,303369) AND product_id=1402 AND description LIKE 'Reverse FIFO Reset Flush (G2%' AND abs(quantity)=3)<>2 THEN RAISE EXCEPTION 'G2 layers not as expected'; END IF;
END $$;
SQLEOF
)
WRITE=$(cat <<'SQLEOF'
CREATE TEMP TABLE b AS SELECT (SELECT sum(quantity) FROM stock_quant WHERE product_id=1402) q_tot,
  (SELECT round(sum(value)::numeric,2) FROM stock_valuation_layer WHERE product_id=1402) v_tot,
  (SELECT round(sum(quantity),4) FROM stock_valuation_layer WHERE product_id=1402) svl_q_tot;
UPDATE stock_quant SET quantity=quantity-3, write_date=now() AT TIME ZONE 'UTC' WHERE product_id=1402 AND location_id=8;
CREATE TEMP TABLE qn AS SELECT * FROM stock_quant WHERE product_id=1402 AND location_id=8;
UPDATE qn SET id=nextval(pg_get_serial_sequence('stock_quant','id')), location_id=1201, quantity=3, reserved_quantity=0, create_date=now() AT TIME ZONE 'UTC', write_date=now() AT TIME ZONE 'UTC';
INSERT INTO stock_quant SELECT * FROM qn;
DELETE FROM stock_valuation_layer WHERE id IN (303362,303369);
\echo '== post-check'
SELECT pg_temp.initial(8) init_fg10, pg_temp.initial(1201) init_rm01rd,
 (SELECT round(sum(quantity),4) FROM stock_valuation_layer WHERE product_id=1402 AND warehouse_id=1) svl_fg10, (SELECT quantity FROM stock_quant WHERE product_id=1402 AND location_id=8) q_fg10,
 (SELECT round(sum(quantity),4) FROM stock_valuation_layer WHERE product_id=1402 AND warehouse_id=13) svl_rm01, (SELECT quantity FROM stock_quant WHERE product_id=1402 AND location_id=1201) q_rm01rd;
DO $$ BEGIN
  IF pg_temp.initial(8)<>0 OR pg_temp.initial(1201)<>0 THEN RAISE EXCEPTION 'Initial not zero'; END IF;
  IF (SELECT sum(quantity) FROM stock_quant WHERE product_id=1402) IS DISTINCT FROM (SELECT q_tot FROM b) THEN RAISE EXCEPTION 'total quant changed'; END IF;
  IF (SELECT round(sum(value)::numeric,2) FROM stock_valuation_layer WHERE product_id=1402) IS DISTINCT FROM (SELECT v_tot FROM b) THEN RAISE EXCEPTION 'total SVL value changed'; END IF;
  IF (SELECT round(sum(quantity),4) FROM stock_valuation_layer WHERE product_id=1402) IS DISTINCT FROM (SELECT svl_q_tot FROM b) THEN RAISE EXCEPTION 'total SVL qty changed'; END IF;
  IF (SELECT round(sum(quantity),4) FROM stock_valuation_layer WHERE product_id=1402 AND warehouse_id=1) <> (SELECT quantity FROM stock_quant WHERE product_id=1402 AND location_id=8)
     OR (SELECT round(sum(quantity),4) FROM stock_valuation_layer WHERE product_id=1402 AND warehouse_id=13) <> (SELECT quantity FROM stock_quant WHERE product_id=1402 AND location_id=1201) THEN RAISE EXCEPTION 'SVL != quant at FG10 or RM01'; END IF;
  RAISE NOTICE 'post-check ok: Initial 0 at FG10/Stock and RM01/RD, totals unchanged, SVL == quant';
END $$;
SQLEOF
)
if [ "$MODE" = check ]; then
  { printf 'BEGIN;\n%s\nROLLBACK;\n' "$BODY"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q"; echo "== check ok"; exit 0
fi
COMMIT_OR_ROLLBACK=$([ "$MODE" = apply ] && echo COMMIT || echo ROLLBACK)
STAMP=$(date +%Y%m%d_%H%M%S)
echo ">>> backup stock_quant + stock_valuation_layer on mog-prod (~/db_backups/quantshift_FCA0003100_${STAMP}.dump)"
ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_quant -t stock_valuation_layer MOG_LIVE -f ~/db_backups/quantshift_FCA0003100_${STAMP}.dump && ls -l ~/db_backups/quantshift_FCA0003100_${STAMP}.dump"
{ printf 'BEGIN;\n%s\n%s\n%s;\n' "$BODY" "$WRITE" "$COMMIT_OR_ROLLBACK"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q"
echo ">>> $MODE finished ($COMMIT_OR_ROLLBACK)"
