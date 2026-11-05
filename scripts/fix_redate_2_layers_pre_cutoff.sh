#!/usr/bin/env bash
# Same remedy as fix_redate_5_layers_pre_cutoff.sh for 2 more products found afterwards (2026-11-05):
# their flush-repair layers were dated 2026-03-30 17:00:00 UTC = INSIDE the FIFO-report window, but the
# report window already equalled quant before the repair, so the report is now off by the repaired qty.
#
#   product      layers (wh)                              report off by today
#   SPW040100    302827 FG50 +1 / 302828 RM01 -1           FG50 +1, RM01 -1
#   403010001    302950 PD01 -0.4 / 302951 RM02 +0.4       PD01 -0.4, RM02 +0.4
#
# Moves create_date + accounting_date of these 4 rows to 2026-03-30 16:59:59.999999 UTC (like the flush
# itself). qty/value/warehouse/remaining untouched; totals per product unchanged; all 4 move or none.
# After: every warehouse of both products has all-time == report window == quant.
#
# Modes (first arg): check (read-only) | dry (backup, UPDATE + post-checks, ROLLBACK) | apply (COMMIT).
# Rollback after apply: UPDATE stock_valuation_layer SET create_date='2026-03-30 17:00:00',
#   accounting_date='2026-03-30 17:00:00' WHERE id IN (302827,302828,302950,302951);
set -euo pipefail
MODE="${1:-check}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply" >&2; exit 2;; esac
IDS="302827,302828,302950,302951"
PIDS="6342,10224"
OLD="2026-03-30 17:00:00"
NEW="2026-03-30 16:59:59.999999"

REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'

read -r -d '' PRE <<SQLEOF || true
\echo '== the 4 layers (expect 4 rows, all at $OLD)'
SELECT l.id, p.default_code, w.code wh, l.quantity, l.value, l.create_date, l.accounting_date
FROM stock_valuation_layer l JOIN product_product p ON p.id=l.product_id JOIN stock_warehouse w ON w.id=l.warehouse_id
WHERE l.id IN ($IDS) ORDER BY l.id;
\echo '== per product/warehouse: all-time, report window, quant (window = acct >= 2026-03-30 17:00 UTC)'
WITH s AS (SELECT product_id, warehouse_id, sum(quantity) aq, sum(quantity) FILTER (WHERE COALESCE(accounting_date,create_date)>='2026-03-30 17:00') wq
  FROM stock_valuation_layer WHERE product_id IN ($PIDS) AND warehouse_id IS NOT NULL GROUP BY 1,2),
q AS (SELECT q.product_id, sl.warehouse_id, sum(q.quantity) qq FROM stock_quant q JOIN stock_location sl ON sl.id=q.location_id
  WHERE q.product_id IN ($PIDS) AND sl.usage IN ('internal','transit') AND sl.warehouse_id IS NOT NULL GROUP BY 1,2)
SELECT p.default_code, w.code wh, coalesce(s.aq,0) all_time, coalesce(s.wq,0) window_q, coalesce(q.qq,0) quant, coalesce(s.wq,0)-coalesce(q.qq,0) window_gap
FROM s FULL JOIN q USING (product_id, warehouse_id) JOIN product_product p ON p.id=coalesce(s.product_id,q.product_id) JOIN stock_warehouse w ON w.id=coalesce(s.warehouse_id,q.warehouse_id)
ORDER BY 1,2;
SQLEOF

if [ "$MODE" = check ]; then
  printf '%s\n' "$PRE" | ssh mog-prod "$REMOTE_ENV; PGOPTIONS='-c default_transaction_read_only=on' psql -h localhost -U odoo MOG_LIVE -q"
  echo "== proposed (not written): create_date + accounting_date of the 4 layers  $OLD -> $NEW"
  exit 0
fi

COMMIT_OR_ROLLBACK=$([ "$MODE" = apply ] && echo COMMIT || echo ROLLBACK)
STAMP=$(date +%Y%m%d_%H%M%S)
echo ">>> backup stock_valuation_layer on mog-prod (~/db_backups/svl_redate2_${STAMP}.dump)"
ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_valuation_layer MOG_LIVE -f ~/db_backups/svl_redate2_${STAMP}.dump && ls -l ~/db_backups/svl_redate2_${STAMP}.dump"

ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q" <<SQL
BEGIN;
$PRE
DO \$\$
DECLARE n int; tot_before numeric;
BEGIN
  SELECT count(*) INTO n FROM stock_valuation_layer WHERE id IN ($IDS)
    AND accounting_date = '$OLD' AND create_date = '$OLD' AND description LIKE 'Reverse FIFO Reset Flush (%' AND stock_move_id IS NULL;
  IF n <> 4 THEN RAISE EXCEPTION 'precondition failed: % of 4 layers in expected state', n; END IF;
END \$\$;
CREATE TEMP TABLE tot_before AS SELECT product_id, round(sum(value),2) v, sum(quantity) q FROM stock_valuation_layer WHERE product_id IN ($PIDS) GROUP BY 1;
UPDATE stock_valuation_layer
   SET create_date = '$NEW', accounting_date = '$NEW', write_date = now() AT TIME ZONE 'UTC'
 WHERE id IN ($IDS);
DO \$\$
DECLARE bad int; chg int;
BEGIN
  -- every warehouse of the 2 products: all-time == quant AND report window == quant
  SELECT count(*) INTO bad FROM (
    SELECT coalesce(s.product_id,q.product_id) pid, coalesce(s.warehouse_id,q.warehouse_id) wh, coalesce(s.aq,0) aq, coalesce(s.wq,0) wq, coalesce(q.qq,0) qq
    FROM (SELECT product_id, warehouse_id, sum(quantity) aq, sum(quantity) FILTER (WHERE COALESCE(accounting_date,create_date)>='2026-03-30 17:00') wq
            FROM stock_valuation_layer WHERE product_id IN ($PIDS) AND warehouse_id IS NOT NULL GROUP BY 1,2) s
    FULL JOIN (SELECT q.product_id, sl.warehouse_id, sum(q.quantity) qq FROM stock_quant q JOIN stock_location sl ON sl.id=q.location_id
            WHERE q.product_id IN ($PIDS) AND sl.usage IN ('internal','transit') AND sl.warehouse_id IS NOT NULL GROUP BY 1,2) q
      ON q.product_id=s.product_id AND q.warehouse_id=s.warehouse_id) z
  WHERE abs(z.aq - z.qq) > 0.0001 OR abs(z.wq - z.qq) > 0.0001;
  IF bad <> 0 THEN RAISE EXCEPTION 'post-check failed: % product/warehouse rows where all-time or window != quant', bad; END IF;
  SELECT count(*) INTO chg FROM tot_before b JOIN (SELECT product_id, round(sum(value),2) v, sum(quantity) q FROM stock_valuation_layer WHERE product_id IN ($PIDS) GROUP BY 1) a USING (product_id) WHERE a.v <> b.v OR a.q <> b.q;
  IF chg <> 0 THEN RAISE EXCEPTION 'post-check failed: total qty/value changed on % products', chg; END IF;
  RAISE NOTICE 'post-check ok: all-time == window == quant on every warehouse of the 2 products; totals unchanged';
END \$\$;
$COMMIT_OR_ROLLBACK;
SQL
echo ">>> $MODE finished ($COMMIT_OR_ROLLBACK)"
