#!/usr/bin/env bash
# Repair of the FIFO Reset Flush pair for MO042S101 (product_id 5532) on MOG_LIVE.
#
#   flush layers (no stock_move): 127569 FG50(wh10) -2 / -1,576.26
#                                 127570 RM01(wh13) +2 / +1,576.26
#   physical stock sits in FG50 (quant FG50 21, RM01 0); SVL ledger FG50 19 / RM01 2.
#
# Adds ONE plain SVL pair (no stock_move, remaining 0). Pick the value policy
# with OPT (required for dry/apply):
#   OPT=opt1  undo the flush exactly: FG50 +2/+1,576.26, RM01 -2/-1,576.26
#             (flush sides are symmetric, so this is also value-neutral):
#             FG50 ends 17,754.70 @21 (845.46/unit), RM01 ends 0 / 0.00.
#   OPT=opt3  value-neutral at FG50 avg 851.50/unit: +/-1,702.99; RM01 ends -126.73 at qty 0.
# Dated 2026-03-31 00:00 Bangkok (= 2026-03-30 17:00 UTC). Both sides or neither.
# Total value 31922.44 unchanged either way. Tiny flush residues at FG10/FG40 are not touched.
#
# Modes (first arg): check (read-only) | dry (ROLLBACK) | apply (COMMIT after checks).
#   OPT=opt1 scripts/fix_MO042S101_flush_pair.sh dry
# Rollback after apply: DELETE FROM stock_valuation_layer WHERE description LIKE 'Reverse FIFO Reset Flush (MO042S101%';
# Does NOT touch FIFO remaining_* / queue drift, quants, moves or journal entries.
set -euo pipefail
MODE="${1:-check}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply" >&2; exit 2;; esac
QTY=2
OPT="${OPT:-}"
case "$OPT" in
  opt3) FG_VALUE="1702.99"; RM_VALUE="1702.99"; TOT_VALUE="31922.44";;
  opt1) FG_VALUE="1576.26"; RM_VALUE="1576.26"; TOT_VALUE="31922.44";;
  *) if [ "$MODE" != check ]; then echo "set OPT=opt1|opt3" >&2; exit 2; fi; FG_VALUE="?"; RM_VALUE="?"; TOT_VALUE="0";;
esac
TS="2026-03-30 17:00:00"

REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'

read -r -d '' PRE <<'SQLEOF' || true
\echo '== preconditions (expect FG50 svl 19 / quant 21, RM01 svl 2 / quant 0)'
SELECT w.code wh, sum(l.quantity) svl_qty, round(sum(l.value),2) svl_val,
       (SELECT coalesce(sum(q.quantity),0) FROM stock_quant q JOIN stock_location sl ON sl.id=q.location_id
         WHERE q.product_id=5532 AND sl.warehouse_id=w.id AND sl.usage='internal') quant
FROM stock_valuation_layer l JOIN stock_warehouse w ON w.id=l.warehouse_id
WHERE l.product_id=5532 GROUP BY w.id, w.code ORDER BY 1;
\echo '== already applied? (expect 0)'
SELECT count(*) FROM stock_valuation_layer WHERE description LIKE 'Reverse FIFO Reset Flush (MO042S101%';
SQLEOF

if [ "$MODE" = check ]; then
  printf '%s\n' "$PRE" | ssh mog-prod "$REMOTE_ENV; PGOPTIONS='-c default_transaction_read_only=on' psql -h localhost -U odoo MOG_LIVE -q"
  echo "== proposed rows (not written): wh10 +2/+$FG_VALUE and wh13 -2/-$RM_VALUE ($OPT) at $TS UTC, remaining 0"
  exit 0
fi

COMMIT_OR_ROLLBACK=$([ "$MODE" = apply ] && echo COMMIT || echo ROLLBACK)
STAMP=$(date +%Y%m%d_%H%M%S)
echo ">>> backup stock_valuation_layer on mog-prod (~/db_backups/svl_MO042S101_${STAMP}.dump)"
ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_valuation_layer MOG_LIVE -f ~/db_backups/svl_MO042S101_${STAMP}.dump && ls -l ~/db_backups/svl_MO042S101_${STAMP}.dump"

ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q" <<SQL
BEGIN;
$PRE
DO \$\$
DECLARE pd numeric; rm numeric; done_ int;
BEGIN
  SELECT coalesce(sum(quantity),0) INTO pd FROM stock_valuation_layer WHERE product_id=5532 AND warehouse_id=10;
  SELECT coalesce(sum(quantity),0) INTO rm FROM stock_valuation_layer WHERE product_id=5532 AND warehouse_id=13;
  SELECT count(*) INTO done_ FROM stock_valuation_layer WHERE description LIKE 'Reverse FIFO Reset Flush (MO042S101%';
  IF pd <> 19 OR rm <> 2 OR done_ <> 0 THEN
    RAISE EXCEPTION 'precondition failed: FG50 %, RM01 %, already applied %', pd, rm, done_;
  END IF;
END \$\$;
INSERT INTO stock_valuation_layer
  (company_id, product_id, description, quantity, unit_cost, value, remaining_qty, remaining_value,
   warehouse_id, current_warehouse_id, create_uid, write_uid, create_date, write_date, accounting_date)
VALUES
  (1, 5532, 'Reverse FIFO Reset Flush (MO042S101 ledger fix) - WH FG50', 2, $FG_VALUE / 2, $FG_VALUE, 0, 0,
   10, 10, 2, 2, '$TS', now() AT TIME ZONE 'UTC', '$TS'),
  (1, 5532, 'Reverse FIFO Reset Flush (MO042S101 ledger fix) - WH RM01', -2, $RM_VALUE / 2, -$RM_VALUE, 0, 0,
   13, 13, 2, 2, '$TS', now() AT TIME ZONE 'UTC', '$TS');
DO \$\$
DECLARE pd numeric; rm numeric; tot numeric; totv numeric;
BEGIN
  SELECT coalesce(sum(quantity),0) INTO pd FROM stock_valuation_layer WHERE product_id=5532 AND warehouse_id=10;
  SELECT coalesce(sum(quantity),0) INTO rm FROM stock_valuation_layer WHERE product_id=5532 AND warehouse_id=13;
  SELECT sum(quantity), sum(value) INTO tot, totv FROM stock_valuation_layer WHERE product_id=5532;
  IF pd <> 21 OR rm <> 0 THEN RAISE EXCEPTION 'post-check failed: FG50 %, RM01 % (want 21 / 0)', pd, rm; END IF;
  IF round(totv,2) <> $TOT_VALUE THEN RAISE EXCEPTION 'post-check failed: total value % (want $TOT_VALUE)', totv; END IF;
  RAISE NOTICE 'post-check ok: FG50 %, RM01 %, total qty %, total value %', pd, rm, tot, totv;
END \$\$;
$COMMIT_OR_ROLLBACK;
SQL
echo ">>> $MODE finished ($COMMIT_OR_ROLLBACK)"
