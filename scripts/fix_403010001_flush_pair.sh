#!/usr/bin/env bash
# Repair of the PD01/RM02 ledger split for 403010001 (product_id 10224) on MOG_LIVE.
#
#   flush layers (no stock_move): 127069 PD01(wh11) +0.4 / +88.00
#                                 127070 RM02(wh14) -0.4 / -88.00
#   The flush CREATED the gap: before it SVL already equalled quant
#   (PD01 1.00, RM02 25.61). Now SVL PD01 1.40 / RM02 25.21 vs quant 1.00 / 25.61.
#
# Option 1 (undo the flush exactly; symmetric, so value-neutral): plain SVL pair
# (no stock_move, remaining 0), 220.00/unit:
#   PD01 (wh11)  -0.4 / -88.00    dated 2026-03-31 00:00 Bangkok (= 2026-03-30 17:00 UTC)
#   RM02 (wh14)  +0.4 / +88.00
# After: PD01 1.00 / 220.00, RM02 25.61 / 5,634.20. Total qty 26.61 and total
# value 5854.20 unchanged. Both sides or neither.
#
# Modes (first arg): check (read-only) | dry (ROLLBACK) | apply (COMMIT after checks).
# Rollback after apply: DELETE FROM stock_valuation_layer WHERE description LIKE 'Reverse FIFO Reset Flush (403010001%';
# Does NOT touch FIFO remaining_* / queue drift, quants, moves or journal entries.
set -euo pipefail
MODE="${1:-check}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply" >&2; exit 2;; esac
UNIT_COST="220.0000"
VALUE="88.00"
TS="2026-03-30 17:00:00"

REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'

read -r -d '' PRE <<'SQLEOF' || true
\echo '== preconditions (expect PD01 svl 1.4 / quant 1, RM02 svl 25.21 / quant 25.61)'
SELECT w.code wh, sum(l.quantity) svl_qty, round(sum(l.value),2) svl_val,
       (SELECT coalesce(sum(q.quantity),0) FROM stock_quant q JOIN stock_location sl ON sl.id=q.location_id
         WHERE q.product_id=10224 AND sl.warehouse_id=w.id AND sl.usage='internal') quant
FROM stock_valuation_layer l JOIN stock_warehouse w ON w.id=l.warehouse_id
WHERE l.product_id=10224 GROUP BY w.id, w.code ORDER BY 1;
\echo '== already applied? (expect 0)'
SELECT count(*) FROM stock_valuation_layer WHERE description LIKE 'Reverse FIFO Reset Flush (403010001%';
SQLEOF

if [ "$MODE" = check ]; then
  printf '%s\n' "$PRE" | ssh mog-prod "$REMOTE_ENV; PGOPTIONS='-c default_transaction_read_only=on' psql -h localhost -U odoo MOG_LIVE -q"
  echo "== proposed rows (not written): wh11 -0.4/-$VALUE and wh14 +0.4/+$VALUE at $TS UTC, remaining 0"
  exit 0
fi

COMMIT_OR_ROLLBACK=$([ "$MODE" = apply ] && echo COMMIT || echo ROLLBACK)
STAMP=$(date +%Y%m%d_%H%M%S)
echo ">>> backup stock_valuation_layer on mog-prod (~/db_backups/svl_403010001_${STAMP}.dump)"
ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_valuation_layer MOG_LIVE -f ~/db_backups/svl_403010001_${STAMP}.dump && ls -l ~/db_backups/svl_403010001_${STAMP}.dump"

ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q" <<SQL
BEGIN;
$PRE
DO \$\$
DECLARE pd numeric; rm numeric; done_ int;
BEGIN
  SELECT coalesce(sum(quantity),0) INTO pd FROM stock_valuation_layer WHERE product_id=10224 AND warehouse_id=11;
  SELECT coalesce(sum(quantity),0) INTO rm FROM stock_valuation_layer WHERE product_id=10224 AND warehouse_id=14;
  SELECT count(*) INTO done_ FROM stock_valuation_layer WHERE description LIKE 'Reverse FIFO Reset Flush (403010001%';
  IF pd <> 1.4 OR rm <> 25.21 OR done_ <> 0 THEN
    RAISE EXCEPTION 'precondition failed: PD01 %, RM02 %, already applied %', pd, rm, done_;
  END IF;
END \$\$;
INSERT INTO stock_valuation_layer
  (company_id, product_id, description, quantity, unit_cost, value, remaining_qty, remaining_value,
   warehouse_id, current_warehouse_id, create_uid, write_uid, create_date, write_date, accounting_date)
VALUES
  (1, 10224, 'Reverse FIFO Reset Flush (403010001 ledger fix) - WH PD01', -0.4, $UNIT_COST, -$VALUE, 0, 0,
   11, 11, 2, 2, '$TS', now() AT TIME ZONE 'UTC', '$TS'),
  (1, 10224, 'Reverse FIFO Reset Flush (403010001 ledger fix) - WH RM02', 0.4, $UNIT_COST, $VALUE, 0, 0,
   14, 14, 2, 2, '$TS', now() AT TIME ZONE 'UTC', '$TS');
DO \$\$
DECLARE pd numeric; rm numeric; tot numeric; totv numeric;
BEGIN
  SELECT coalesce(sum(quantity),0) INTO pd FROM stock_valuation_layer WHERE product_id=10224 AND warehouse_id=11;
  SELECT coalesce(sum(quantity),0) INTO rm FROM stock_valuation_layer WHERE product_id=10224 AND warehouse_id=14;
  SELECT sum(quantity), sum(value) INTO tot, totv FROM stock_valuation_layer WHERE product_id=10224;
  IF pd <> 1.0 OR rm <> 25.61 THEN RAISE EXCEPTION 'post-check failed: PD01 %, RM02 % (want 1 / 25.61)', pd, rm; END IF;
  IF round(totv,2) <> 5854.20 THEN RAISE EXCEPTION 'post-check failed: total value % (want 5854.20 unchanged)', totv; END IF;
  RAISE NOTICE 'post-check ok: PD01 %, RM02 %, total qty %, total value %', pd, rm, tot, totv;
END \$\$;
$COMMIT_OR_ROLLBACK;
SQL
echo ">>> $MODE finished ($COMMIT_OR_ROLLBACK)"
