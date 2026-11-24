#!/usr/bin/env bash
# Repair of the PD01/RM02 ledger split for 409110001 (product_id 10604) on MOG_LIVE.
#
#   Not a clean flush pair: flush layers 127108 PD01 +236 / +354.00 and
#   127109 RM02 -236 / -354.00 (no stock_move) cancel only part of two
#   pre-cut-off moves whose SVL sits on PD01 while the move lines leave RM02:
#     BLOJ003192/BOJ0003050 (2025-12-12, 120) and BLOJ003193/BOJ0003051 (120)
#   => ledger PD01 short 4 / RM02 over 4 vs quant (PD01 2440, RM02 2442).
#
# Adds ONE plain SVL pair (no stock_move, remaining 0, same shape as the
# 301010008 / 409110001 / 404030004 fixes), value-neutral at 1.50/unit:
#   PD01 (wh11)  +4 / +6.00      dated 2026-03-31 00:00 Bangkok (= 2026-03-30 17:00 UTC)
#   RM02 (wh14)  -4 / -6.00
# Both sides or neither. Total qty 4889 and total value 7332.67 unchanged.
#
# Modes (first arg): check (read-only) | dry (ROLLBACK) | apply (COMMIT after checks).
# Rollback after apply: DELETE FROM stock_valuation_layer WHERE description LIKE 'Reverse FIFO Reset Flush (409110001%';
# Does NOT touch FIFO remaining_* / queue drift, quants, moves or journal entries.
set -euo pipefail
MODE="${1:-check}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply" >&2; exit 2;; esac
UNIT_COST="1.5000"
VALUE="6.00"
TS="2026-03-30 17:00:00"

REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'

read -r -d '' PRE <<'SQLEOF' || true
\echo '== preconditions (expect PD01 svl 2436 / quant 2440, RM02 svl 2446 / quant 2442)'
SELECT w.code wh, sum(l.quantity) svl_qty, round(sum(l.value),2) svl_val,
       (SELECT coalesce(sum(q.quantity),0) FROM stock_quant q JOIN stock_location sl ON sl.id=q.location_id
         WHERE q.product_id=10604 AND sl.warehouse_id=w.id AND sl.usage='internal') quant
FROM stock_valuation_layer l JOIN stock_warehouse w ON w.id=l.warehouse_id
WHERE l.product_id=10604 GROUP BY w.id, w.code ORDER BY 1;
\echo '== already applied? (expect 0)'
SELECT count(*) FROM stock_valuation_layer WHERE description LIKE 'Reverse FIFO Reset Flush (409110001%';
SQLEOF

if [ "$MODE" = check ]; then
  printf '%s\n' "$PRE" | ssh mog-prod "$REMOTE_ENV; PGOPTIONS='-c default_transaction_read_only=on' psql -h localhost -U odoo MOG_LIVE -q"
  echo "== proposed rows (not written): wh11 +4/+$VALUE and wh14 -4/-$VALUE at $TS UTC, remaining 0"
  exit 0
fi

COMMIT_OR_ROLLBACK=$([ "$MODE" = apply ] && echo COMMIT || echo ROLLBACK)
STAMP=$(date +%Y%m%d_%H%M%S)
echo ">>> backup stock_valuation_layer on mog-prod (~/db_backups/svl_409110001_${STAMP}.dump)"
ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_valuation_layer MOG_LIVE -f ~/db_backups/svl_409110001_${STAMP}.dump && ls -l ~/db_backups/svl_409110001_${STAMP}.dump"

ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q" <<SQL
BEGIN;
$PRE
DO \$\$
DECLARE pd numeric; rm numeric; done_ int;
BEGIN
  SELECT coalesce(sum(quantity),0) INTO pd FROM stock_valuation_layer WHERE product_id=10604 AND warehouse_id=11;
  SELECT coalesce(sum(quantity),0) INTO rm FROM stock_valuation_layer WHERE product_id=10604 AND warehouse_id=14;
  SELECT count(*) INTO done_ FROM stock_valuation_layer WHERE description LIKE 'Reverse FIFO Reset Flush (409110001%';
  IF pd <> 2436 OR rm <> 2446 OR done_ <> 0 THEN
    RAISE EXCEPTION 'precondition failed: PD01 %, RM02 %, already applied %', pd, rm, done_;
  END IF;
END \$\$;
INSERT INTO stock_valuation_layer
  (company_id, product_id, description, quantity, unit_cost, value, remaining_qty, remaining_value,
   warehouse_id, current_warehouse_id, create_uid, write_uid, create_date, write_date, accounting_date)
VALUES
  (1, 10604, 'Reverse FIFO Reset Flush (409110001 ledger fix) - WH PD01', 4, $UNIT_COST, $VALUE, 0, 0,
   11, 11, 2, 2, '$TS', now() AT TIME ZONE 'UTC', '$TS'),
  (1, 10604, 'Reverse FIFO Reset Flush (409110001 ledger fix) - WH RM02', -4, $UNIT_COST, -$VALUE, 0, 0,
   14, 14, 2, 2, '$TS', now() AT TIME ZONE 'UTC', '$TS');
DO \$\$
DECLARE pd numeric; rm numeric; tot numeric; totv numeric;
BEGIN
  SELECT coalesce(sum(quantity),0) INTO pd FROM stock_valuation_layer WHERE product_id=10604 AND warehouse_id=11;
  SELECT coalesce(sum(quantity),0) INTO rm FROM stock_valuation_layer WHERE product_id=10604 AND warehouse_id=14;
  SELECT sum(quantity), sum(value) INTO tot, totv FROM stock_valuation_layer WHERE product_id=10604;
  IF pd <> 2440 OR rm <> 2442 THEN RAISE EXCEPTION 'post-check failed: PD01 %, RM02 % (want 2440 / 2442)', pd, rm; END IF;
  IF totv <> 7332.67 THEN RAISE EXCEPTION 'post-check failed: total value % (want 7332.67 unchanged)', totv; END IF;
  RAISE NOTICE 'post-check ok: PD01 %, RM02 %, total qty %, total value %', pd, rm, tot, totv;
END \$\$;
$COMMIT_OR_ROLLBACK;
SQL
echo ">>> $MODE finished ($COMMIT_OR_ROLLBACK)"
