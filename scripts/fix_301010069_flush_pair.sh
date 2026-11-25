#!/usr/bin/env bash
# Repair of the FIFO Reset Flush pair for 301010069 (product_id 9632) on MOG_LIVE.
#
#   flush layers (no stock_move): 127039 PD01(wh11) -4 /   -537.07
#                                 127040 RM02(wh14) +4 / +1,539.28   (asymmetric!)
#   physical stock: quant PD01 89, RM02 52; SVL ledger PD01 85 / RM02 56.
#
# Adds ONE plain SVL pair (no stock_move, remaining 0). Pick the value policy
# with OPT (required for dry/apply):
#   OPT=opt1  undo the flush exactly: PD01 +4/+537.07, RM02 -4/-1,539.28
#             PD01 ends 2,218.05 @89, RM02 ends 5,499.80 @52; total value
#             8,720.06 -> 7,717.85 (-1,002.21: removes the value the flush injected).
#   OPT=opt3  value-neutral at PD01 avg 19.78/unit: +/-79.10; total unchanged.
# Dated 2026-03-31 00:00 Bangkok (= 2026-03-30 17:00 UTC). Both sides or neither.
# NOTE opt1 changes total inventory value of the product: accounting must acknowledge.
#
# Modes (first arg): check (read-only) | dry (ROLLBACK) | apply (COMMIT after checks).
#   OPT=opt1 scripts/fix_301010069_flush_pair.sh dry
# Rollback after apply: DELETE FROM stock_valuation_layer WHERE description LIKE 'Reverse FIFO Reset Flush (301010069%';
# Does NOT touch FIFO remaining_* / queue drift, quants, moves or journal entries.
set -euo pipefail
MODE="${1:-check}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply" >&2; exit 2;; esac
QTY=4
OPT="${OPT:-}"
case "$OPT" in
  opt3) FG_VALUE="79.10"; RM_VALUE="79.10"; TOT_VALUE="8720.06";;
  opt1) FG_VALUE="537.07"; RM_VALUE="1539.28"; TOT_VALUE="7717.85";;
  *) if [ "$MODE" != check ]; then echo "set OPT=opt1|opt3" >&2; exit 2; fi; FG_VALUE="?"; RM_VALUE="?"; TOT_VALUE="0";;
esac
TS="2026-03-30 17:00:00"

REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'

read -r -d '' PRE <<'SQLEOF' || true
\echo '== preconditions (expect PD01 svl 85 / quant 89, RM02 svl 56 / quant 52)'
SELECT w.code wh, sum(l.quantity) svl_qty, round(sum(l.value),2) svl_val,
       (SELECT coalesce(sum(q.quantity),0) FROM stock_quant q JOIN stock_location sl ON sl.id=q.location_id
         WHERE q.product_id=9632 AND sl.warehouse_id=w.id AND sl.usage='internal') quant
FROM stock_valuation_layer l JOIN stock_warehouse w ON w.id=l.warehouse_id
WHERE l.product_id=9632 GROUP BY w.id, w.code ORDER BY 1;
\echo '== already applied? (expect 0)'
SELECT count(*) FROM stock_valuation_layer WHERE description LIKE 'Reverse FIFO Reset Flush (301010069%';
SQLEOF

if [ "$MODE" = check ]; then
  printf '%s\n' "$PRE" | ssh mog-prod "$REMOTE_ENV; PGOPTIONS='-c default_transaction_read_only=on' psql -h localhost -U odoo MOG_LIVE -q"
  echo "== proposed rows (not written): wh11 +4/+$FG_VALUE and wh14 -4/-$RM_VALUE ($OPT) at $TS UTC, remaining 0"
  exit 0
fi

COMMIT_OR_ROLLBACK=$([ "$MODE" = apply ] && echo COMMIT || echo ROLLBACK)
STAMP=$(date +%Y%m%d_%H%M%S)
echo ">>> backup stock_valuation_layer on mog-prod (~/db_backups/svl_301010069_${STAMP}.dump)"
ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_valuation_layer MOG_LIVE -f ~/db_backups/svl_301010069_${STAMP}.dump && ls -l ~/db_backups/svl_301010069_${STAMP}.dump"

ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q" <<SQL
BEGIN;
$PRE
DO \$\$
DECLARE pd numeric; rm numeric; done_ int;
BEGIN
  SELECT coalesce(sum(quantity),0) INTO pd FROM stock_valuation_layer WHERE product_id=9632 AND warehouse_id=11;
  SELECT coalesce(sum(quantity),0) INTO rm FROM stock_valuation_layer WHERE product_id=9632 AND warehouse_id=14;
  SELECT count(*) INTO done_ FROM stock_valuation_layer WHERE description LIKE 'Reverse FIFO Reset Flush (301010069%';
  IF pd <> 85 OR rm <> 56 OR done_ <> 0 THEN
    RAISE EXCEPTION 'precondition failed: PD01 %, RM02 %, already applied %', pd, rm, done_;
  END IF;
END \$\$;
INSERT INTO stock_valuation_layer
  (company_id, product_id, description, quantity, unit_cost, value, remaining_qty, remaining_value,
   warehouse_id, current_warehouse_id, create_uid, write_uid, create_date, write_date, accounting_date)
VALUES
  (1, 9632, 'Reverse FIFO Reset Flush (301010069 ledger fix) - WH PD01', 4, $FG_VALUE / 4, $FG_VALUE, 0, 0,
   11, 11, 2, 2, '$TS', now() AT TIME ZONE 'UTC', '$TS'),
  (1, 9632, 'Reverse FIFO Reset Flush (301010069 ledger fix) - WH RM02', -4, $RM_VALUE / 4, -$RM_VALUE, 0, 0,
   14, 14, 2, 2, '$TS', now() AT TIME ZONE 'UTC', '$TS');
DO \$\$
DECLARE pd numeric; rm numeric; tot numeric; totv numeric;
BEGIN
  SELECT coalesce(sum(quantity),0) INTO pd FROM stock_valuation_layer WHERE product_id=9632 AND warehouse_id=11;
  SELECT coalesce(sum(quantity),0) INTO rm FROM stock_valuation_layer WHERE product_id=9632 AND warehouse_id=14;
  SELECT sum(quantity), sum(value) INTO tot, totv FROM stock_valuation_layer WHERE product_id=9632;
  IF pd <> 89 OR rm <> 52 THEN RAISE EXCEPTION 'post-check failed: PD01 %, RM02 % (want 89 / 52)', pd, rm; END IF;
  IF round(totv,2) <> $TOT_VALUE THEN RAISE EXCEPTION 'post-check failed: total value % (want $TOT_VALUE)', totv; END IF;
  RAISE NOTICE 'post-check ok: PD01 %, RM02 %, total qty %, total value %', pd, rm, tot, totv;
END \$\$;
$COMMIT_OR_ROLLBACK;
SQL
echo ">>> $MODE finished ($COMMIT_OR_ROLLBACK)"
