#!/usr/bin/env bash
# Move the 10 flush-repair SVL layers of 5 products from INSIDE the FIFO-report window to JUST BEFORE
# the cut-off, so that both views agree with stock_quant:
#   all-time SVL (guard/ledger)  == quant   (kept: layers still exist, same qty/value)
#   report window (>= 2026-03-30 17:00 UTC, what stock_fifo_valuation_report sums) == quant
#
# Why: stock_fifo_valuation_report drops every layer with acct_date < utc_cutoff (opening included).
# For these 5 products the window already equalled quant BEFORE the repair (the 2026-03-30 flush pair was
# pre-cutoff, so the report never saw it). The repair layers were dated 2026-03-30 17:00:00 UTC = inside the
# window, so the report is now off by exactly the repaired qty. Dating them like the flush itself
# (2026-03-30 16:59:59.999999 UTC) restores the report and keeps the ledger repaired.
#
#   product      layers (wh)                              report off by today
#   SPW0651100   302743 FG10 +3 / 302744 RM01 -3          FG10 +3, RM01 -3
#   SPW0653100   302821 FG10 +3 / 302822 RM01 -3          FG10 +3, RM01 -3
#   301010069    302898 PD01 +4 / 302899 RM02 -4           PD01 +4, RM02 -4
#   MO042S101    302843 FG50 +2 / 302844 RM01 -2           FG50 +2, RM01 -2
#   SPW042100    302871 FG50 +2 / 302872 RM01 -2           FG50 +2, RM01 -2
#
# Only create_date, accounting_date and write_date of those 10 rows change. qty/value/warehouse/remaining
# are untouched; total value per product unchanged. Both rows of a pair move together (all 10 or none).
#
# Modes (first arg): check (read-only) | dry (backup, UPDATE + post-checks, ROLLBACK) | apply (COMMIT).
# Rollback after apply: UPDATE stock_valuation_layer SET create_date='2026-03-30 17:00:00',
#   accounting_date='2026-03-30 17:00:00' WHERE id IN (302743,302744,302821,302822,302898,302899,302843,302844,302871,302872);
set -euo pipefail
MODE="${1:-check}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply" >&2; exit 2;; esac
IDS="302743,302744,302821,302822,302898,302899,302843,302844,302871,302872"
PIDS="6391,6392,9632,5532,6357"
OLD="2026-03-30 17:00:00"
NEW="2026-03-30 16:59:59.999999"

REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'

read -r -d '' PRE <<SQLEOF || true
\echo '== the 10 layers (expect 10 rows, all at $OLD)'
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
  echo "== proposed (not written): create_date + accounting_date of the 10 layers  $OLD -> $NEW"
  exit 0
fi

COMMIT_OR_ROLLBACK=$([ "$MODE" = apply ] && echo COMMIT || echo ROLLBACK)
STAMP=$(date +%Y%m%d_%H%M%S)
echo ">>> backup stock_valuation_layer on mog-prod (~/db_backups/svl_redate5_${STAMP}.dump)"
ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_valuation_layer MOG_LIVE -f ~/db_backups/svl_redate5_${STAMP}.dump && ls -l ~/db_backups/svl_redate5_${STAMP}.dump"

ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q" <<SQL
BEGIN;
$PRE
DO \$\$
DECLARE n int; tot_before numeric;
BEGIN
  SELECT count(*) INTO n FROM stock_valuation_layer WHERE id IN ($IDS)
    AND accounting_date = '$OLD' AND create_date = '$OLD' AND description LIKE 'Reverse FIFO Reset Flush (%' AND stock_move_id IS NULL;
  IF n <> 10 THEN RAISE EXCEPTION 'precondition failed: % of 10 layers in expected state', n; END IF;
END \$\$;
CREATE TEMP TABLE tot_before AS SELECT product_id, round(sum(value),2) v, sum(quantity) q FROM stock_valuation_layer WHERE product_id IN ($PIDS) GROUP BY 1;
UPDATE stock_valuation_layer
   SET create_date = '$NEW', accounting_date = '$NEW', write_date = now() AT TIME ZONE 'UTC'
 WHERE id IN ($IDS);
DO \$\$
DECLARE bad int; chg int;
BEGIN
  -- every warehouse of the 5 products: all-time == quant AND report window == quant
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
  RAISE NOTICE 'post-check ok: all-time == window == quant on every warehouse of the 5 products; totals unchanged';
END \$\$;
$COMMIT_OR_ROLLBACK;
SQL
echo ">>> $MODE finished ($COMMIT_OR_ROLLBACK)"
