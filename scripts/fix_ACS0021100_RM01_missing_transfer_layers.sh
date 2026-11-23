#!/usr/bin/env bash
# ACS0021100 (product 1964) RM01 ledger -1 vs quant 0 (found 2026-11-23 while force-validating FG10/INT/26/11/00095).
# Cause: move 236614 (ROJ0133216, 2026-04-21, FG40/Stock(76) -> RM01/QC(1204), wh NC(9) -> RM01(13)) was validated with
#   demand 0, then done qty set to 1 afterwards (write_date 2026-08-21). Its SVL pair 192729 (OUT, NC) / 192730 (IN, NC->RM01)
#   were booked qty 0 / value 0 @171.1461. Quants moved 1 unit, ledger did not. Later LOJ0078985 consumed that unit from RM01/QC
#   (layer 192739 -1 / -177.65) and the ledger went -1 at RM01 (+1 surplus at NC: ledger 6 vs quant 5).
# Fix: plain SVL pair, no quant/header/queue touch (remaining_qty 0):
#   NC  (wh 9,  loc 76)   -1 / -171.15
#   RM01(wh 13, loc 1204) +1 / +171.15
#   dated 2026-04-21 17:00 UTC (same as move; inside report window >= 2026-03-30 17:00).
# NOT fixed: RM01 ledger value stays stranded (-> qty 0 with value ~986.67 after the pair; was 815.52). Needs accounting
#   (see transfer cost asymmetry notes). FIFO open queue at NC keeps 1 extra remaining unit (queue drift, separate).
# Modes: check (read-only) | dry (backup, insert + post-check, ROLLBACK) | apply (COMMIT, needs user approval)
# Rollback: DELETE FROM stock_valuation_layer WHERE description LIKE 'Fix missing transfer layers (ACS0021100 move 236614%';
set -euo pipefail
MODE="${1:-check}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply" >&2; exit 2;; esac
REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'

BODY=$(cat <<'SQLEOF'
CREATE TEMP TABLE st AS SELECT p.id pid,
 (SELECT count(*) FROM product_product x WHERE x.default_code='ACS0021100') n_prod,
 (SELECT coalesce(sum(quantity),0) FROM stock_valuation_layer l WHERE l.product_id=p.id AND l.warehouse_id=13) rm01_q,
 (SELECT round(coalesce(sum(value),0),2) FROM stock_valuation_layer l WHERE l.product_id=p.id AND l.warehouse_id=13) rm01_v,
 (SELECT coalesce(sum(quantity),0) FROM stock_valuation_layer l WHERE l.product_id=p.id AND l.warehouse_id=9) nc_q,
 (SELECT round(coalesce(sum(value),0),2) FROM stock_valuation_layer l WHERE l.product_id=p.id AND l.warehouse_id=9) nc_v,
 (SELECT count(*) FROM stock_valuation_layer l WHERE l.id IN (192729,192730) AND l.quantity=0 AND l.value=0 AND l.stock_move_id=236614) zero_pair,
 (SELECT count(*) FROM stock_valuation_layer l WHERE l.product_id=p.id AND l.description LIKE 'Fix missing transfer layers (ACS0021100 move 236614%') done
FROM product_product p WHERE p.default_code='ACS0021100';
\echo '== preconditions'
SELECT * FROM st;
\echo '== quants (internal, by warehouse)'
SELECT l.warehouse_id, sum(q.quantity) FROM stock_quant q JOIN stock_location l ON l.id=q.location_id
 WHERE q.product_id=(SELECT pid FROM st) AND l.usage='internal' AND l.warehouse_id IN (9,13) GROUP BY 1 ORDER BY 1;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM st WHERE n_prod=1 AND rm01_q=-1 AND nc_q=6 AND zero_pair=2 AND done=0) THEN
    RAISE EXCEPTION 'precondition failed (need RM01 ledger -1, NC ledger 6, zero pair 192729/30 intact, not applied yet)';
  END IF;
END $$;
SQLEOF
)

WRITE=$(cat <<'SQLEOF'
INSERT INTO stock_valuation_layer
  (company_id, product_id, description, quantity, unit_cost, value, remaining_qty, remaining_value,
   warehouse_id, current_warehouse_id, location_id, create_uid, write_uid, create_date, write_date, accounting_date)
SELECT 1, pid, 'Fix missing transfer layers (ACS0021100 move 236614 OUT NC, -1 / -171.15)', -1, 171.1461, -171.15, 0, 0,
       9, 9, 76, 2, 2, TIMESTAMP '2026-04-21 17:00:00', now() AT TIME ZONE 'UTC', TIMESTAMP '2026-04-21 17:00:00' FROM st
UNION ALL
SELECT 1, pid, 'Fix missing transfer layers (ACS0021100 move 236614 IN RM01, +1 / +171.15)', 1, 171.1461, 171.15, 0, 0,
       13, 13, 1204, 2, 2, TIMESTAMP '2026-04-21 17:00:00', now() AT TIME ZONE 'UTC', TIMESTAMP '2026-04-21 17:00:00' FROM st;
\echo '== post-check'
SELECT warehouse_id, sum(quantity) q, round(sum(value),2) v FROM stock_valuation_layer
 WHERE product_id=(SELECT pid FROM st) AND warehouse_id IN (9,13) GROUP BY 1 ORDER BY 1;
DO $$
DECLARE r13q numeric; r13v numeric; n9q numeric; n9v numeric; tv numeric; nrows int;
BEGIN
  SELECT sum(quantity), round(sum(value),2) INTO r13q, r13v FROM stock_valuation_layer WHERE product_id=(SELECT pid FROM st) AND warehouse_id=13;
  SELECT sum(quantity), round(sum(value),2) INTO n9q, n9v FROM stock_valuation_layer WHERE product_id=(SELECT pid FROM st) AND warehouse_id=9;
  SELECT round(sum(value),2) INTO tv FROM stock_valuation_layer WHERE product_id=(SELECT pid FROM st);
  SELECT count(*) INTO nrows FROM stock_valuation_layer WHERE product_id=(SELECT pid FROM st) AND description LIKE 'Fix missing transfer layers (ACS0021100 move 236614%';
  IF r13q<>0 OR n9q<>5 OR nrows<>2 OR r13v<>(SELECT rm01_v+171.15 FROM st) OR n9v<>(SELECT nc_v-171.15 FROM st) THEN
    RAISE EXCEPTION 'post-check failed: rm01 q=% v=% nc q=% v=% rows=%', r13q, r13v, n9q, n9v, nrows;
  END IF;
  RAISE NOTICE 'post-check ok: RM01 q 0 value %, NC q 5 value %, product total value % unchanged', r13v, n9v, tv;
END $$;
SQLEOF
)

if [ "$MODE" = check ]; then
  { printf 'BEGIN;\n%s\nROLLBACK;\n' "$BODY"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q"
  exit 0
fi
COMMIT_OR_ROLLBACK=$([ "$MODE" = apply ] && echo COMMIT || echo ROLLBACK)
STAMP=$(date +%Y%m%d_%H%M%S)
echo ">>> backup stock_valuation_layer (~/db_backups/svl_ACS0021100_${STAMP}.dump)"
ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_valuation_layer MOG_LIVE -f ~/db_backups/svl_ACS0021100_${STAMP}.dump && ls -l ~/db_backups/svl_ACS0021100_${STAMP}.dump"
{ printf 'BEGIN;\n%s\n%s\n%s;\n' "$BODY" "$WRITE" "$COMMIT_OR_ROLLBACK"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q"
echo ">>> $MODE finished ($COMMIT_OR_ROLLBACK)"
