#!/usr/bin/env bash
# Repair of the FIFO Reset Flush pair for 406010069 (product_id 10355) on MOG_LIVE.
#
#   flush layers (no stock_move): 127083 PD01(wh11) -200 / -1,000.00
#                                 127084 RM02(wh14) +200 /   +840.00
#   physical stock moved RM02 -> PD01 before the cut-off, SVL ledger did not.
#
# Adds ONE plain SVL pair (no stock_move, remaining 0, same shape as the
# 301010008 fix 302655/302656), priced value-neutral at 4.20/unit (option 3,
# RM02 avg cost 2520/600 = 4.20; PD01 has qty 0 so no own basis => +/-840.00).
# Both sides or neither.
#
#   PD01 (wh11)  +200 / +840.00
#   RM02 (wh14)  -200 / -840.00   dated 2026-03-31 00:00 Bangkok (= 2026-03-30 17:00 UTC)
#
# Modes (first arg):
#   check   read-only: print preconditions + proposed rows. Writes nothing.
#   dry     backup, run the INSERTs + post-checks in a transaction, ROLLBACK.
#   apply   backup, run the INSERTs + post-checks, COMMIT only if all checks pass.
# Run dry/apply yourself (prefix with `!`); assistant sessions may be blocked from prod writes.
# Rollback after apply: DELETE FROM stock_valuation_layer WHERE description LIKE 'Reverse FIFO Reset Flush (406010069%';
# Does NOT touch FIFO remaining_* / queue drift, quants, moves or journal entries.
# Does NOT clear PD01's pre-existing -270.00 value at qty 0 (accounting decision).
set -euo pipefail
MODE="${1:-check}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply" >&2; exit 2;; esac
UNIT_COST="4.2000"
VALUE="840.00"
TS="2026-03-30 17:00:00"

REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'

read -r -d '' PRE <<'SQLEOF' || true
\echo '== preconditions (expect PD01 svl 0 / quant 200, RM02 svl 600 / quant 400)'
SELECT w.code wh, sum(l.quantity) svl_qty, round(sum(l.value),2) svl_val,
       (SELECT coalesce(sum(q.quantity),0) FROM stock_quant q JOIN stock_location sl ON sl.id=q.location_id
         WHERE q.product_id=10355 AND sl.warehouse_id=w.id AND sl.usage='internal') quant
FROM stock_valuation_layer l JOIN stock_warehouse w ON w.id=l.warehouse_id
WHERE l.product_id=10355 GROUP BY w.id, w.code ORDER BY 1;
\echo '== already applied? (expect 0)'
SELECT count(*) FROM stock_valuation_layer WHERE description LIKE 'Reverse FIFO Reset Flush (406010069%';
SQLEOF

if [ "$MODE" = check ]; then
  printf '%s\n' "$PRE" | ssh mog-prod "$REMOTE_ENV; PGOPTIONS='-c default_transaction_read_only=on' psql -h localhost -U odoo MOG_LIVE -q"
  echo "== proposed rows (not written): wh11 +200/+$VALUE and wh14 -200/-$VALUE at $TS UTC, remaining 0"
  exit 0
fi

COMMIT_OR_ROLLBACK=$([ "$MODE" = apply ] && echo COMMIT || echo ROLLBACK)
STAMP=$(date +%Y%m%d_%H%M%S)
echo ">>> backup stock_valuation_layer on mog-prod (~/db_backups/svl_406010069_${STAMP}.dump)"
ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_valuation_layer MOG_LIVE -f ~/db_backups/svl_406010069_${STAMP}.dump && ls -l ~/db_backups/svl_406010069_${STAMP}.dump"

ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q" <<SQL
BEGIN;
$PRE
DO \$\$
DECLARE pd numeric; rm numeric; done_ int;
BEGIN
  SELECT coalesce(sum(quantity),0) INTO pd FROM stock_valuation_layer WHERE product_id=10355 AND warehouse_id=11;
  SELECT coalesce(sum(quantity),0) INTO rm FROM stock_valuation_layer WHERE product_id=10355 AND warehouse_id=14;
  SELECT count(*) INTO done_ FROM stock_valuation_layer WHERE description LIKE 'Reverse FIFO Reset Flush (406010069%';
  IF pd <> 0 OR rm <> 600 OR done_ <> 0 THEN
    RAISE EXCEPTION 'precondition failed: PD01 %, RM02 %, already applied %', pd, rm, done_;
  END IF;
END \$\$;
INSERT INTO stock_valuation_layer
  (company_id, product_id, description, quantity, unit_cost, value, remaining_qty, remaining_value,
   warehouse_id, current_warehouse_id, create_uid, write_uid, create_date, write_date, accounting_date)
VALUES
  (1, 10355, 'Reverse FIFO Reset Flush (406010069 ledger fix) - WH PD01', 200, $UNIT_COST, $VALUE, 0, 0,
   11, 11, 2, 2, '$TS', now() AT TIME ZONE 'UTC', '$TS'),
  (1, 10355, 'Reverse FIFO Reset Flush (406010069 ledger fix) - WH RM02', -200, $UNIT_COST, -$VALUE, 0, 0,
   14, 14, 2, 2, '$TS', now() AT TIME ZONE 'UTC', '$TS');
DO \$\$
DECLARE pd numeric; rm numeric; tot numeric; totv numeric;
BEGIN
  SELECT coalesce(sum(quantity),0) INTO pd FROM stock_valuation_layer WHERE product_id=10355 AND warehouse_id=11;
  SELECT coalesce(sum(quantity),0) INTO rm FROM stock_valuation_layer WHERE product_id=10355 AND warehouse_id=14;
  SELECT sum(quantity), sum(value) INTO tot, totv FROM stock_valuation_layer WHERE product_id=10355;
  IF pd <> 200 OR rm <> 400 THEN RAISE EXCEPTION 'post-check failed: PD01 %, RM02 % (want 200 / 400)', pd, rm; END IF;
  IF totv <> 2250.00 THEN RAISE EXCEPTION 'post-check failed: total value % (want 2250.00 unchanged)', totv; END IF;
  RAISE NOTICE 'post-check ok: PD01 %, RM02 %, total qty %, total value %', pd, rm, tot, totv;
END \$\$;
$COMMIT_OR_ROLLBACK;
SQL
echo ">>> $MODE finished ($COMMIT_OR_ROLLBACK)"
