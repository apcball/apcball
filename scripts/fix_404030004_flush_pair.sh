#!/usr/bin/env bash
# Repair of the FIFO Reset Flush pair for 404030004 (product_id 10302) on MOG_LIVE.
#
#   flush layers (no stock_move): 127078 RM02(wh14) -35 / -2,975.00
#                                 127079 RM03(wh15) +35 / +2,905.00
#   physical stock sat in RM03 (quant RM03 328, RM02 0); the flush left the
#   SVL ledger RM02 -35 / RM03 363.
#
# Adds ONE plain SVL pair (no stock_move, remaining 0, same shape as the
# 301010008 / 404030004 fixes), priced value-neutral at 85.00/unit (option 3,
# RM03 avg 30,589/363 = 84.27 is NOT used; 85.00 = RM02 flush unit cost
# 2,975/35, so RM02 returns to exactly qty 0 / value 0). Both sides or neither.
#
#   RM02 (wh14)  +35 / +2,975.00   dated 2026-03-31 00:00 Bangkok (= 2026-03-30 17:00 UTC)
#   RM03 (wh15)  -35 / -2,975.00
#
# Modes (first arg): check (read-only) | dry (ROLLBACK) | apply (COMMIT after checks).
# Rollback after apply: DELETE FROM stock_valuation_layer WHERE description LIKE 'Reverse FIFO Reset Flush (404030004%';
# Does NOT touch FIFO remaining_* / queue drift, quants, moves or journal entries.
set -euo pipefail
MODE="${1:-check}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply" >&2; exit 2;; esac
UNIT_COST="85.0000"
VALUE="2975.00"
TS="2026-03-30 17:00:00"

REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'

read -r -d '' PRE <<'SQLEOF' || true
\echo '== preconditions (expect RM02 svl -35 / quant 0, RM03 svl 363 / quant 328)'
SELECT w.code wh, sum(l.quantity) svl_qty, round(sum(l.value),2) svl_val,
       (SELECT coalesce(sum(q.quantity),0) FROM stock_quant q JOIN stock_location sl ON sl.id=q.location_id
         WHERE q.product_id=10302 AND sl.warehouse_id=w.id AND sl.usage='internal') quant
FROM stock_valuation_layer l JOIN stock_warehouse w ON w.id=l.warehouse_id
WHERE l.product_id=10302 GROUP BY w.id, w.code ORDER BY 1;
\echo '== already applied? (expect 0)'
SELECT count(*) FROM stock_valuation_layer WHERE description LIKE 'Reverse FIFO Reset Flush (404030004%';
SQLEOF

if [ "$MODE" = check ]; then
  printf '%s\n' "$PRE" | ssh mog-prod "$REMOTE_ENV; PGOPTIONS='-c default_transaction_read_only=on' psql -h localhost -U odoo MOG_LIVE -q"
  echo "== proposed rows (not written): wh14 +35/+$VALUE and wh15 -35/-$VALUE at $TS UTC, remaining 0"
  exit 0
fi

COMMIT_OR_ROLLBACK=$([ "$MODE" = apply ] && echo COMMIT || echo ROLLBACK)
STAMP=$(date +%Y%m%d_%H%M%S)
echo ">>> backup stock_valuation_layer on mog-prod (~/db_backups/svl_404030004_${STAMP}.dump)"
ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_valuation_layer MOG_LIVE -f ~/db_backups/svl_404030004_${STAMP}.dump && ls -l ~/db_backups/svl_404030004_${STAMP}.dump"

ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q" <<SQL
BEGIN;
$PRE
DO \$\$
DECLARE pd numeric; rm numeric; done_ int;
BEGIN
  SELECT coalesce(sum(quantity),0) INTO pd FROM stock_valuation_layer WHERE product_id=10302 AND warehouse_id=14;
  SELECT coalesce(sum(quantity),0) INTO rm FROM stock_valuation_layer WHERE product_id=10302 AND warehouse_id=15;
  SELECT count(*) INTO done_ FROM stock_valuation_layer WHERE description LIKE 'Reverse FIFO Reset Flush (404030004%';
  IF pd <> -35 OR rm <> 363 OR done_ <> 0 THEN
    RAISE EXCEPTION 'precondition failed: RM02 %, RM03 %, already applied %', pd, rm, done_;
  END IF;
END \$\$;
INSERT INTO stock_valuation_layer
  (company_id, product_id, description, quantity, unit_cost, value, remaining_qty, remaining_value,
   warehouse_id, current_warehouse_id, create_uid, write_uid, create_date, write_date, accounting_date)
VALUES
  (1, 10302, 'Reverse FIFO Reset Flush (404030004 ledger fix) - WH RM02', 35, $UNIT_COST, $VALUE, 0, 0,
   14, 14, 2, 2, '$TS', now() AT TIME ZONE 'UTC', '$TS'),
  (1, 10302, 'Reverse FIFO Reset Flush (404030004 ledger fix) - WH RM03', -35, $UNIT_COST, -$VALUE, 0, 0,
   15, 15, 2, 2, '$TS', now() AT TIME ZONE 'UTC', '$TS');
DO \$\$
DECLARE pd numeric; rm numeric; tot numeric; totv numeric;
BEGIN
  SELECT coalesce(sum(quantity),0) INTO pd FROM stock_valuation_layer WHERE product_id=10302 AND warehouse_id=14;
  SELECT coalesce(sum(quantity),0) INTO rm FROM stock_valuation_layer WHERE product_id=10302 AND warehouse_id=15;
  SELECT sum(quantity), sum(value) INTO tot, totv FROM stock_valuation_layer WHERE product_id=10302;
  IF pd <> 0 OR rm <> 328 THEN RAISE EXCEPTION 'post-check failed: RM02 %, RM03 % (want 0 / 328)', pd, rm; END IF;
  IF totv <> 27614.00 THEN RAISE EXCEPTION 'post-check failed: total value % (want 27614.00 unchanged)', totv; END IF;
  RAISE NOTICE 'post-check ok: RM02 %, RM03 %, total qty %, total value %', pd, rm, tot, totv;
END \$\$;
$COMMIT_OR_ROLLBACK;
SQL
echo ">>> $MODE finished ($COMMIT_OR_ROLLBACK)"
