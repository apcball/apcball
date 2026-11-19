#!/usr/bin/env bash
# 409250054 (product 10710) @RM02 (warehouse 14, lot_stock 116) on MOG_LIVE:
# qty reaches 0 on 2026-10-29 but SVL value stays +27,216.89 (ghost value; qty 0 must be value 0).
# Cause (traced 2026-11-19): RM02 receipts 172,132 / 117,726.19 (avg 0.6839) but outs 172,132 / 90,509.30 (avg 0.5258);
#   171,982 of the outs are PD01/INT transfers whose two legs are booked at different unit costs
#   (107 docs, net -8,589.84 across RM02/PD01, listed in the accounting dry-run xlsx). Value drifts up Jul->Oct
#   (Aug end 14,138 @12,382; Sep end 5,252 @26,009) and is stranded when qty hits 0.
# Fix: ONE qty-0 revaluation layer at RM02 of -27,216.89 dated 2026-10-29 16:00 UTC (23:00 Bangkok, same day qty hit 0).
#   History, quants, FIFO queue (remaining_*) untouched.
# NOT fixed by this layer: months Jul-Sep stay overstated (value/qty inflated before the zero point);
#   PD01 side (-2,357.90 vs lots) and RM02 open-queue drift today (ledger 65,702.41 vs open remaining 42,867.04) remain.
#   Dating at the zero point is an accounting choice; alternative = spread over months (not done here).
# Modes: check (read-only) | dry (backup file, insert + post-check, ROLLBACK) | apply (COMMIT, needs accounting approval)
# Rollback: DELETE FROM stock_valuation_layer WHERE description LIKE 'Revaluation (409250054 RM02%';
set -euo pipefail
MODE="${1:-check}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply" >&2; exit 2;; esac
REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'

BODY=$(cat <<'SQLEOF'
CREATE TEMP TABLE st AS SELECT p.id pid, 14 wid,
 (SELECT count(*) FROM product_product x WHERE x.default_code='409250054') n_prod,
 (SELECT coalesce(sum(quantity),0) FROM stock_valuation_layer l WHERE l.product_id=p.id AND l.warehouse_id=14
    AND COALESCE(l.accounting_date,l.create_date)>='2026-03-30 17:00' AND COALESCE(l.accounting_date,l.create_date)<='2026-10-29 17:00') q_at,
 (SELECT round(coalesce(sum(value),0),2) FROM stock_valuation_layer l WHERE l.product_id=p.id AND l.warehouse_id=14
    AND COALESCE(l.accounting_date,l.create_date)>='2026-03-30 17:00' AND COALESCE(l.accounting_date,l.create_date)<='2026-10-29 17:00') v_at,
 (SELECT round(coalesce(sum(value),0),2) FROM stock_valuation_layer l WHERE l.product_id=p.id AND l.warehouse_id=14
    AND COALESCE(l.accounting_date,l.create_date)<'2026-03-30 17:00') v_pre,
 (SELECT round(sum(value),2) FROM stock_valuation_layer l WHERE l.product_id=p.id AND l.warehouse_id=14) rm02_v,
 (SELECT round(sum(value),2) FROM stock_valuation_layer l WHERE l.product_id=p.id) tot_v,
 (SELECT count(*) FROM stock_valuation_layer l WHERE l.product_id=p.id AND l.description LIKE 'Revaluation (409250054 RM02%') done
FROM product_product p WHERE p.default_code='409250054';
\echo '== preconditions'
SELECT * FROM st;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM st WHERE n_prod=1 AND q_at=0 AND v_at=27216.89 AND v_pre=0 AND done=0) THEN
    RAISE EXCEPTION 'precondition failed (qty at 2026-10-29 must be 0 with value 27216.89, no pre-cutoff value, not applied yet)';
  END IF;
END $$;
\echo '== month-end RM02 (qty, value) BEFORE'
CREATE TEMP TABLE me_before AS
SELECT date_trunc('month', (COALESCE(l.accounting_date,l.create_date)+interval '7 hours'))::date m,
       sum(l.quantity) q, sum(l.value) v
FROM stock_valuation_layer l WHERE l.product_id=(SELECT pid FROM st) AND l.warehouse_id=14
  AND COALESCE(l.accounting_date,l.create_date)>='2026-03-30 17:00' GROUP BY 1;
SELECT m, sum(q) OVER (ORDER BY m) cq, round(sum(v) OVER (ORDER BY m),2) cv FROM me_before ORDER BY m;
SQLEOF
)

WRITE=$(cat <<'SQLEOF'
INSERT INTO stock_valuation_layer
  (company_id, product_id, description, quantity, unit_cost, value, remaining_qty, remaining_value,
   warehouse_id, current_warehouse_id, location_id, create_uid, write_uid, create_date, write_date, accounting_date)
SELECT 1, pid, 'Revaluation (409250054 RM02 stranded value at qty 0; PD01/INT transfer cost asymmetry; -27,216.89)', 0, 0, -27216.89, 0, 0,
       wid, wid, 116, 2, 2, TIMESTAMP '2026-10-29 16:00:00', now() AT TIME ZONE 'UTC', TIMESTAMP '2026-10-29 16:00:00' FROM st;
\echo '== month-end RM02 (qty, value) AFTER'
CREATE TEMP TABLE me_after AS
SELECT date_trunc('month', (COALESCE(l.accounting_date,l.create_date)+interval '7 hours'))::date m,
       sum(l.quantity) q, sum(l.value) v
FROM stock_valuation_layer l WHERE l.product_id=(SELECT pid FROM st) AND l.warehouse_id=14
  AND COALESCE(l.accounting_date,l.create_date)>='2026-03-30 17:00' GROUP BY 1;
SELECT a.m, sum(a.q) OVER (ORDER BY a.m) cq, round(sum(a.v) OVER (ORDER BY a.m),2) cv FROM me_after a ORDER BY a.m;
\echo '== post-check'
DO $$
DECLARE v_at_after numeric; q_at_after numeric; tv_after numeric; nrows int;
BEGIN
  SELECT round(sum(value),2), sum(quantity) INTO v_at_after, q_at_after FROM stock_valuation_layer
   WHERE product_id=(SELECT pid FROM st) AND warehouse_id=14
     AND COALESCE(accounting_date,create_date)>='2026-03-30 17:00' AND COALESCE(accounting_date,create_date)<='2026-10-29 17:00';
  SELECT round(sum(value),2) INTO tv_after FROM stock_valuation_layer WHERE product_id=(SELECT pid FROM st);
  SELECT count(*) INTO nrows FROM stock_valuation_layer WHERE product_id=(SELECT pid FROM st) AND description LIKE 'Revaluation (409250054 RM02%';
  IF v_at_after<>0 OR q_at_after<>0 OR nrows<>1 OR tv_after <> (SELECT tot_v FROM st)-27216.89 THEN
    RAISE EXCEPTION 'post-check failed: v_at=% q_at=% rows=% total=%', v_at_after, q_at_after, nrows, tv_after;
  END IF;
  RAISE NOTICE 'post-check ok: RM02 0/0 at 2026-10-29, product total value % (was %)', tv_after, (SELECT tot_v FROM st);
END $$;
SQLEOF
)

if [ "$MODE" = check ]; then
  { printf 'BEGIN;\n%s\nROLLBACK;\n' "$BODY"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q"
  exit 0
fi
COMMIT_OR_ROLLBACK=$([ "$MODE" = apply ] && echo COMMIT || echo ROLLBACK)
STAMP=$(date +%Y%m%d_%H%M%S)
echo ">>> backup stock_valuation_layer (~/db_backups/svl_409250054_RM02_${STAMP}.dump)"
ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_valuation_layer MOG_LIVE -f ~/db_backups/svl_409250054_RM02_${STAMP}.dump && ls -l ~/db_backups/svl_409250054_RM02_${STAMP}.dump"
{ printf 'BEGIN;\n%s\n%s\n%s;\n' "$BODY" "$WRITE" "$COMMIT_OR_ROLLBACK"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q"
echo ">>> $MODE finished ($COMMIT_OR_ROLLBACK)"
