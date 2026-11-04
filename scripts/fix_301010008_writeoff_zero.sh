#!/usr/bin/env bash
# Zero the residual value left at qty 0 for 301010008 (product_id 9622) on MOG_LIVE:
#   FG10 (wh1)  qty 0 / -82.02   (two-hop transfer priced at origin cost, see memory)
#   RM02 (wh14) qty 0 / +1,906.21 (leftover of the 844/unit reseed)
# Adds two qty=0 revaluation layers (no stock_move, remaining 0, unit_cost 0), the same
# shape as the FIFO single-product revaluation layer precedent:
#   FG10 +82.02, RM02 -1,906.21  => net -1,824.19; product total 5,572.96 -> 3,748.77
#   (= PD01 147 units, 25.50/unit). Dated now (current-period adjustment).
# Value change: accounting must approve. Both rows or neither.
#
# Modes (first arg): check (read-only) | dry (ROLLBACK) | apply (COMMIT after checks).
# Rollback after apply: DELETE FROM stock_valuation_layer WHERE description LIKE 'Write-off residual value to 0 (301010008%';
# Does NOT touch quants, moves, FIFO remaining_* or journal entries.
set -euo pipefail
MODE="${1:-check}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply" >&2; exit 2;; esac

REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'

read -r -d '' PRE <<'SQLEOF' || true
\echo '== preconditions (expect FG10 0 / -82.02, PD01 147 / 3748.77, RM02 0 / 1906.21)'
SELECT w.code wh, sum(l.quantity) svl_qty, round(sum(l.value),2) svl_val
FROM stock_valuation_layer l JOIN stock_warehouse w ON w.id=l.warehouse_id
WHERE l.product_id=9622 GROUP BY w.id, w.code ORDER BY 1;
\echo '== already applied? (expect 0)'
SELECT count(*) FROM stock_valuation_layer WHERE description LIKE 'Write-off residual value to 0 (301010008%';
SQLEOF

if [ "$MODE" = check ]; then
  printf '%s\n' "$PRE" | ssh mog-prod "$REMOTE_ENV; PGOPTIONS='-c default_transaction_read_only=on' psql -h localhost -U odoo MOG_LIVE -q"
  echo "== proposed rows (not written): wh1 qty 0 / +82.02 and wh14 qty 0 / -1906.21, dated now, remaining 0"
  exit 0
fi

COMMIT_OR_ROLLBACK=$([ "$MODE" = apply ] && echo COMMIT || echo ROLLBACK)
STAMP=$(date +%Y%m%d_%H%M%S)
echo ">>> backup stock_valuation_layer on mog-prod (~/db_backups/svl_301010008_wo_${STAMP}.dump)"
ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_valuation_layer MOG_LIVE -f ~/db_backups/svl_301010008_wo_${STAMP}.dump && ls -l ~/db_backups/svl_301010008_wo_${STAMP}.dump"

ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q" <<SQL
BEGIN;
$PRE
DO \$\$
DECLARE fq numeric; fv numeric; pq numeric; pv numeric; rq numeric; rv numeric; done_ int;
BEGIN
  SELECT sum(quantity), round(sum(value),2) INTO fq, fv FROM stock_valuation_layer WHERE product_id=9622 AND warehouse_id=1;
  SELECT sum(quantity), round(sum(value),2) INTO pq, pv FROM stock_valuation_layer WHERE product_id=9622 AND warehouse_id=11;
  SELECT sum(quantity), round(sum(value),2) INTO rq, rv FROM stock_valuation_layer WHERE product_id=9622 AND warehouse_id=14;
  SELECT count(*) INTO done_ FROM stock_valuation_layer WHERE description LIKE 'Write-off residual value to 0 (301010008%';
  IF fq <> 0 OR fv <> -82.02 OR pq <> 147 OR pv <> 3748.77 OR rq <> 0 OR rv <> 1906.21 OR done_ <> 0 THEN
    RAISE EXCEPTION 'precondition failed: FG10 %/%, PD01 %/%, RM02 %/%, already applied %', fq, fv, pq, pv, rq, rv, done_;
  END IF;
END \$\$;
INSERT INTO stock_valuation_layer
  (company_id, product_id, description, quantity, unit_cost, value, remaining_qty, remaining_value,
   warehouse_id, current_warehouse_id, create_uid, write_uid, create_date, write_date, accounting_date)
VALUES
  (1, 9622, 'Write-off residual value to 0 (301010008 qty 0) - WH FG10', 0, 0, 82.02, 0, 0,
   1, 1, 2, 2, now() AT TIME ZONE 'UTC', now() AT TIME ZONE 'UTC', now() AT TIME ZONE 'UTC'),
  (1, 9622, 'Write-off residual value to 0 (301010008 qty 0) - WH RM02', 0, 0, -1906.21, 0, 0,
   14, 14, 2, 2, now() AT TIME ZONE 'UTC', now() AT TIME ZONE 'UTC', now() AT TIME ZONE 'UTC');
DO \$\$
DECLARE fv numeric; rv numeric; pq numeric; pv numeric; totv numeric;
BEGIN
  SELECT round(sum(value),2) INTO fv FROM stock_valuation_layer WHERE product_id=9622 AND warehouse_id=1;
  SELECT round(sum(value),2) INTO rv FROM stock_valuation_layer WHERE product_id=9622 AND warehouse_id=14;
  SELECT sum(quantity), round(sum(value),2) INTO pq, pv FROM stock_valuation_layer WHERE product_id=9622 AND warehouse_id=11;
  SELECT round(sum(value),2) INTO totv FROM stock_valuation_layer WHERE product_id=9622;
  IF fv <> 0 OR rv <> 0 OR pq <> 147 OR pv <> 3748.77 OR totv <> 3748.77 THEN
    RAISE EXCEPTION 'post-check failed: FG10 %, RM02 %, PD01 %/%, total %', fv, rv, pq, pv, totv;
  END IF;
  RAISE NOTICE 'post-check ok: FG10 %, RM02 % value, PD01 %/%, total value %', fv, rv, pq, pv, totv;
END \$\$;
$COMMIT_OR_ROLLBACK;
SQL
echo ">>> $MODE finished ($COMMIT_OR_ROLLBACK)"
