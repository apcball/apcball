#!/usr/bin/env bash
# MT0014101 (product 3812) @ FG10 (wh 1) on MOG_LIVE: missing SVL for the claim-cycle receipt move.
#
#   move 265679 'FG40/EMCP/2606001 ยกเลิก' (Customers -> FG10/Stock/Claim Return, +1, done 2026-06-23 10:25:21) has NO SVL
#   move 282901 'FG40/EMCP/2606001 Return' (Claim Return -> Customers, -1) booked SVL 224625 FG10 -1 / -2,060.89
#   => quant 0 but SVL -1 (all-time and report window), FG10 value -2,060.89.
#
# Adds ONE SVL FG10 +1 / +2,060.89 (mirror of 224625), linked to move 265679, remaining 0, accounting_date = the move's
# date (2026-06-23 10:25:21, inside the report window). Result: FG10 qty 0 / value 0.00 everywhere. No quant/queue/journal change.
#
# Modes: check (read-only) | dry (backup, insert + post-checks, ROLLBACK) | apply (COMMIT)
# Rollback after apply: DELETE FROM stock_valuation_layer WHERE description LIKE 'Missing receipt SVL (MT0014101 claim cycle%';
set -euo pipefail
MODE="${1:-check}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply" >&2; exit 2;; esac
REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'

read -r -d '' PRE <<'SQLEOF' || true
\echo '== FG10 MT0014101 (expect all-time -1 / -2060.89, window -1, quant 0, move 265679 done with 0 layers, not applied)'
SELECT sum(l.quantity) all_q, round(sum(l.value)::numeric,2) all_v,
  sum(l.quantity) FILTER (WHERE COALESCE(l.accounting_date,l.create_date)>='2026-03-30 17:00') win_q,
  (SELECT coalesce(sum(q.quantity),0) FROM stock_quant q JOIN stock_location sl ON sl.id=q.location_id WHERE q.product_id=3812 AND sl.warehouse_id=1 AND sl.usage IN ('internal','transit')) quant,
  (SELECT state FROM stock_move WHERE id=265679) mv_state,
  (SELECT count(*) FROM stock_valuation_layer WHERE stock_move_id=265679) mv_layers,
  (SELECT count(*) FROM stock_valuation_layer WHERE description LIKE 'Missing receipt SVL (MT0014101 claim cycle%') done
FROM stock_valuation_layer l WHERE l.product_id=3812 AND l.warehouse_id=1;
SQLEOF

if [ "$MODE" = check ]; then
  printf '%s\n' "$PRE" | ssh mog-prod "$REMOTE_ENV; PGOPTIONS='-c default_transaction_read_only=on' psql -h localhost -U odoo MOG_LIVE -q"
  echo "== proposed (not written): SVL FG10 +1 / +2060.89 linked to move 265679, remaining 0, accounting_date 2026-06-23 10:25:21"
  exit 0
fi
COMMIT_OR_ROLLBACK=$([ "$MODE" = apply ] && echo COMMIT || echo ROLLBACK)
STAMP=$(date +%Y%m%d_%H%M%S)
echo ">>> backup stock_valuation_layer on mog-prod (~/db_backups/svl_MT14_${STAMP}.dump)"
ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_valuation_layer MOG_LIVE -f ~/db_backups/svl_MT14_${STAMP}.dump && ls -l ~/db_backups/svl_MT14_${STAMP}.dump"
ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q" <<SQL
BEGIN;
$PRE
DO \$\$
DECLARE aq numeric; av numeric; wq numeric; qq numeric; st text; ml int; dn int;
BEGIN
  SELECT sum(quantity), round(sum(value)::numeric,2), sum(quantity) FILTER (WHERE COALESCE(accounting_date,create_date)>='2026-03-30 17:00')
    INTO aq, av, wq FROM stock_valuation_layer WHERE product_id=3812 AND warehouse_id=1;
  SELECT coalesce(sum(q.quantity),0) INTO qq FROM stock_quant q JOIN stock_location sl ON sl.id=q.location_id WHERE q.product_id=3812 AND sl.warehouse_id=1 AND sl.usage IN ('internal','transit');
  SELECT state INTO st FROM stock_move WHERE id=265679;
  SELECT count(*) INTO ml FROM stock_valuation_layer WHERE stock_move_id=265679;
  SELECT count(*) INTO dn FROM stock_valuation_layer WHERE description LIKE 'Missing receipt SVL (MT0014101 claim cycle%';
  IF aq<>-1 OR av<>-2060.89 OR wq<>-1 OR qq<>0 OR st<>'done' OR ml<>0 OR dn<>0 THEN
    RAISE EXCEPTION 'precondition failed: all %/% window % quant % move % layers % done %', aq, av, wq, qq, st, ml, dn;
  END IF;
END \$\$;
INSERT INTO stock_valuation_layer
  (company_id, product_id, description, quantity, unit_cost, value, remaining_qty, remaining_value,
   warehouse_id, current_warehouse_id, stock_move_id, create_uid, write_uid, create_date, write_date, accounting_date)
VALUES
  (1, 3812, 'Missing receipt SVL (MT0014101 claim cycle FG40/EMCP/2606001 ยกเลิก) - WH FG10', 1, 2060.89, 2060.89, 0, 0,
   1, 1, 265679, 2, 2, now() AT TIME ZONE 'UTC', now() AT TIME ZONE 'UTC', TIMESTAMP '2026-06-23 10:25:21');
DO \$\$
DECLARE aq numeric; av numeric; wq numeric; wv numeric; qq numeric; gq numeric;
BEGIN
  SELECT sum(quantity), round(sum(value)::numeric,2), sum(quantity) FILTER (WHERE COALESCE(accounting_date,create_date)>='2026-03-30 17:00'),
         round(sum(value) FILTER (WHERE COALESCE(accounting_date,create_date)>='2026-03-30 17:00')::numeric,2)
    INTO aq, av, wq, wv FROM stock_valuation_layer WHERE product_id=3812 AND warehouse_id=1;
  SELECT coalesce(sum(q.quantity),0) INTO qq FROM stock_quant q JOIN stock_location sl ON sl.id=q.location_id WHERE q.product_id=3812 AND sl.warehouse_id=1 AND sl.usage IN ('internal','transit');
  SELECT coalesce(sum(l.quantity),0) INTO gq FROM stock_valuation_layer l LEFT JOIN stock_move sm ON sm.id=l.stock_move_id
    WHERE l.product_id=3812 AND l.warehouse_id=1 AND COALESCE(sm.reference,'') NOT LIKE 'IMEX-REBASELINE%';
  IF aq<>0 OR wq<>0 OR qq<>0 OR gq<>0 OR abs(av)>0.011 OR abs(wv)>0.011 THEN
    RAISE EXCEPTION 'post-check failed: all %/% window %/% quant % guard %', aq, av, wq, wv, qq, gq;
  END IF;
  RAISE NOTICE 'post-check ok: FG10 all-time %/%, window %/%, quant %, guard sum %', aq, av, wq, wv, qq, gq;
END \$\$;
$COMMIT_OR_ROLLBACK;
SQL
echo ">>> $MODE finished ($COMMIT_OR_ROLLBACK)"
