#!/usr/bin/env bash
# Repair of the PD01/RM02 ledger split for 409250055 (product_id 10711) on MOG_LIVE.
#
#   Not a clean flush pair: flush layers 127129 PD01 -50 / +2,070.60 and
#   127130 RM02 +50 / -2,070.59 (no stock_move) push the SAME way as one
#   pre-cut-off move whose SVL sits on PD01 while the move line leaves RM02:
#     BLOJ003194/BOJ0003080 (2025-12-17, 110)
#   => ledger PD01 short 160 (110 + 50) / RM02 over 160 vs quant
#      (PD01 1902, RM02 20468).
#
# Adds ONE plain SVL pair (no stock_move, remaining 0, same shape as the
# earlier flush-pair fixes), value-neutral at 0.87/unit (the cost PD01 books
# its consumption at in this period; PD01 avg 0.27 is skewed by the flush value):
#   PD01 (wh11)  +160 / +139.20   dated 2026-03-31 00:00 Bangkok (= 2026-03-30 17:00 UTC)
#   RM02 (wh14)  -160 / -139.20
# Both sides or neither. Total qty 22370 and total value 2424.60 unchanged.
# NOT touched: 7 zero-qty, no-warehouse invoice price-diff layers totalling
# -20,146.09 (accounting to review) and the flush layers 127129/127130.
#
# Modes (first arg): check (read-only) | dry (ROLLBACK) | apply (COMMIT after checks).
# Rollback after apply: DELETE FROM stock_valuation_layer WHERE description LIKE 'Reverse FIFO Reset Flush (409250055%';
# Does NOT touch FIFO remaining_* / queue drift, quants, moves or journal entries.
set -euo pipefail
MODE="${1:-check}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply" >&2; exit 2;; esac
UNIT_COST="0.8700"
VALUE="139.20"
TS="2026-03-30 17:00:00"

REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'

read -r -d '' PRE <<'SQLEOF' || true
\echo '== preconditions (expect PD01 svl 1742 / quant 1902, RM02 svl 20628 / quant 20468)'
SELECT w.code wh, sum(l.quantity) svl_qty, round(sum(l.value),2) svl_val,
       (SELECT coalesce(sum(q.quantity),0) FROM stock_quant q JOIN stock_location sl ON sl.id=q.location_id
         WHERE q.product_id=10711 AND sl.warehouse_id=w.id AND sl.usage='internal') quant
FROM stock_valuation_layer l JOIN stock_warehouse w ON w.id=l.warehouse_id
WHERE l.product_id=10711 GROUP BY w.id, w.code ORDER BY 1;
\echo '== already applied? (expect 0)'
SELECT count(*) FROM stock_valuation_layer WHERE description LIKE 'Reverse FIFO Reset Flush (409250055%';
SQLEOF

if [ "$MODE" = check ]; then
  printf '%s\n' "$PRE" | ssh mog-prod "$REMOTE_ENV; PGOPTIONS='-c default_transaction_read_only=on' psql -h localhost -U odoo MOG_LIVE -q"
  echo "== proposed rows (not written): wh11 +160/+$VALUE and wh14 -160/-$VALUE at $TS UTC, remaining 0"
  exit 0
fi

COMMIT_OR_ROLLBACK=$([ "$MODE" = apply ] && echo COMMIT || echo ROLLBACK)
STAMP=$(date +%Y%m%d_%H%M%S)
echo ">>> backup stock_valuation_layer on mog-prod (~/db_backups/svl_409250055_${STAMP}.dump)"
ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_valuation_layer MOG_LIVE -f ~/db_backups/svl_409250055_${STAMP}.dump && ls -l ~/db_backups/svl_409250055_${STAMP}.dump"

ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q" <<SQL
BEGIN;
$PRE
DO \$\$
DECLARE pd numeric; rm numeric; done_ int;
BEGIN
  SELECT coalesce(sum(quantity),0) INTO pd FROM stock_valuation_layer WHERE product_id=10711 AND warehouse_id=11;
  SELECT coalesce(sum(quantity),0) INTO rm FROM stock_valuation_layer WHERE product_id=10711 AND warehouse_id=14;
  SELECT count(*) INTO done_ FROM stock_valuation_layer WHERE description LIKE 'Reverse FIFO Reset Flush (409250055%';
  IF pd <> 1742 OR rm <> 20628 OR done_ <> 0 THEN
    RAISE EXCEPTION 'precondition failed: PD01 %, RM02 %, already applied %', pd, rm, done_;
  END IF;
END \$\$;
INSERT INTO stock_valuation_layer
  (company_id, product_id, description, quantity, unit_cost, value, remaining_qty, remaining_value,
   warehouse_id, current_warehouse_id, create_uid, write_uid, create_date, write_date, accounting_date)
VALUES
  (1, 10711, 'Reverse FIFO Reset Flush (409250055 ledger fix) - WH PD01', 160, $UNIT_COST, $VALUE, 0, 0,
   11, 11, 2, 2, '$TS', now() AT TIME ZONE 'UTC', '$TS'),
  (1, 10711, 'Reverse FIFO Reset Flush (409250055 ledger fix) - WH RM02', -160, $UNIT_COST, -$VALUE, 0, 0,
   14, 14, 2, 2, '$TS', now() AT TIME ZONE 'UTC', '$TS');
DO \$\$
DECLARE pd numeric; rm numeric; tot numeric; totv numeric;
BEGIN
  SELECT coalesce(sum(quantity),0) INTO pd FROM stock_valuation_layer WHERE product_id=10711 AND warehouse_id=11;
  SELECT coalesce(sum(quantity),0) INTO rm FROM stock_valuation_layer WHERE product_id=10711 AND warehouse_id=14;
  SELECT sum(quantity), sum(value) INTO tot, totv FROM stock_valuation_layer WHERE product_id=10711;
  IF pd <> 1902 OR rm <> 20468 THEN RAISE EXCEPTION 'post-check failed: PD01 %, RM02 % (want 1902 / 20468)', pd, rm; END IF;
  IF totv <> 2424.60 THEN RAISE EXCEPTION 'post-check failed: total value % (want 2424.60 unchanged)', totv; END IF;
  RAISE NOTICE 'post-check ok: PD01 %, RM02 %, total qty %, total value %', pd, rm, tot, totv;
END \$\$;
$COMMIT_OR_ROLLBACK;
SQL
echo ">>> $MODE finished ($COMMIT_OR_ROLLBACK)"
