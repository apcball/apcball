#!/usr/bin/env bash
# Repair of inflated origin_remaining_value on the MCV0000E0010000 lot (product MCV07C valve) on MOG_LIVE.
#
#   origin layer 239453 (RM-NI/IN2608001, 2026-08-04, wh25): 300 units, value 65,538.00 (218.46/unit)
#     origin_remaining_qty 300, origin_remaining_value 375,312.35  (1,251.04/unit)   <-- inflated
#   position layers 239455 (wh13) / 239991 (wh1, still holds the 300 units, remaining_value 68,814.53)
#     carry origin_remaining_value 372,035.82 as well (not read by the engine, left untouched)
#
# fifo_service.calculate_fifo_cost / stock_move external-out cost the position layers at
#   origin.origin_remaining_value / origin.origin_remaining_qty  -> next issue of the 300 units
# would be booked at ~1,251/unit instead of ~229/unit (about 306,498 of COGS too high).
# SVL ledger values are correct; only origin_remaining_value is wrong.
#
# Fix: set 239453.origin_remaining_value = sum(remaining_value) of the chain's positive layers
#      that still hold stock (= 68,814.53 = 65,538.00 receipt + 3,276.53 landed cost LC 262),
#      i.e. the same value the ledger already carries. Nothing else is written: no SVL rows,
#      no remaining_*, no quants, no moves, no journal entries.
# NOT in scope (reported separately): landed cost 262 also booked 3,276.53 on origin layer 262869 (wh25)
#      besides 262868 (wh1) for the same line; the origin that still holds the 300 units sits at wh1.
#
# Modes (first arg):
#   check   read-only: print the chain, preconditions and the proposed value. Writes nothing.
#   dry     backup, run the UPDATE + post-checks in a transaction, ROLLBACK.
#   apply   backup, run the UPDATE + post-checks, COMMIT only if all checks pass.
# Run dry/apply yourself (prefix with `!`); assistant sessions are blocked from prod writes.
# Rollback after apply:
#   UPDATE stock_valuation_layer SET origin_remaining_value = 375312.35 WHERE id = 239453;
set -euo pipefail
MODE="${1:-check}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply" >&2; exit 2;; esac
ORIGIN_ID=239453
OLD_VALUE="375312.35"

REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'

read -r -d '' PRE <<'SQLEOF' || true
\echo '== chain of origin 239453 (expect origin orv 375312.35, orq 300; wh1 layer 239991 rq 300 / rv 68814.53)'
SELECT id, accounting_date::date ad, warehouse_id wh, quantity q, round(value,2) v, remaining_qty rq,
       round(remaining_value,2) rv, origin_valuation_layer_id ovid, origin_remaining_qty orq,
       round(origin_remaining_value,2) orv, stock_landed_cost_id lc
FROM stock_valuation_layer WHERE id = 239453 OR origin_valuation_layer_id = 239453 ORDER BY id;
\echo '== proposed origin_remaining_value (sum of remaining_value of positive chain layers) and unit cost'
SELECT round(sum(remaining_value) FILTER (WHERE quantity > 0), 2) proposed_orv,
       sum(remaining_qty) FILTER (WHERE quantity > 0) chain_rq,
       round(sum(remaining_value) FILTER (WHERE quantity > 0) / nullif(sum(remaining_qty) FILTER (WHERE quantity > 0), 0), 4) proposed_unit
FROM stock_valuation_layer WHERE id = 239453 OR origin_valuation_layer_id = 239453;
\echo '== already applied? (expect orv still 375312.35)'
SELECT round(origin_remaining_value, 2) FROM stock_valuation_layer WHERE id = 239453;
SQLEOF

if [ "$MODE" = check ]; then
  printf '%s\n' "$PRE" | ssh mog-prod "$REMOTE_ENV; PGOPTIONS='-c default_transaction_read_only=on' psql -h localhost -U odoo MOG_LIVE -q"
  echo "== proposed (not written): UPDATE stock_valuation_layer SET origin_remaining_value = <proposed_orv> WHERE id = $ORIGIN_ID"
  exit 0
fi

COMMIT_OR_ROLLBACK=$([ "$MODE" = apply ] && echo COMMIT || echo ROLLBACK)
STAMP=$(date +%Y%m%d_%H%M%S)
echo ">>> backup stock_valuation_layer on mog-prod (~/db_backups/svl_MCV0000E0010000_${STAMP}.dump)"
ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_valuation_layer MOG_LIVE -f ~/db_backups/svl_MCV0000E0010000_${STAMP}.dump && ls -l ~/db_backups/svl_MCV0000E0010000_${STAMP}.dump"

ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q" <<SQL
BEGIN;
$PRE
DO \$\$
DECLARE cur numeric; new_v numeric; chain_rq numeric; orq numeric;
BEGIN
  SELECT origin_remaining_value, origin_remaining_qty INTO cur, orq FROM stock_valuation_layer WHERE id = $ORIGIN_ID;
  IF round(cur, 2) <> $OLD_VALUE THEN
    RAISE EXCEPTION 'abort: origin_remaining_value is % (expected $OLD_VALUE) - changed or already fixed', cur;
  END IF;
  SELECT round(sum(remaining_value) FILTER (WHERE quantity > 0), 2), sum(remaining_qty) FILTER (WHERE quantity > 0)
    INTO new_v, chain_rq
  FROM stock_valuation_layer WHERE id = $ORIGIN_ID OR origin_valuation_layer_id = $ORIGIN_ID;
  IF chain_rq IS DISTINCT FROM orq THEN
    RAISE EXCEPTION 'abort: chain remaining_qty % <> origin_remaining_qty % - stock moved since the check', chain_rq, orq;
  END IF;
  IF new_v IS NULL OR new_v <= 0 THEN
    RAISE EXCEPTION 'abort: proposed value % invalid', new_v;
  END IF;
  UPDATE stock_valuation_layer SET origin_remaining_value = new_v WHERE id = $ORIGIN_ID;
  RAISE NOTICE 'origin_remaining_value % -> % (unit % -> %)', cur, new_v, round(cur/orq, 2), round(new_v/orq, 2);
END \$\$;
\echo '== after (expect origin orv 68814.53, unit ~229.38; position layers untouched)'
SELECT id, warehouse_id wh, remaining_qty rq, round(remaining_value,2) rv, origin_remaining_qty orq, round(origin_remaining_value,2) orv
FROM stock_valuation_layer WHERE id = $ORIGIN_ID OR origin_valuation_layer_id = $ORIGIN_ID ORDER BY id;
\echo '== rows changed in table since start of transaction is 1: verify no other layer was touched'
SELECT count(*) FILTER (WHERE origin_remaining_value <> 375312.35 AND id = $ORIGIN_ID) changed_origin FROM stock_valuation_layer WHERE id = $ORIGIN_ID;
$COMMIT_OR_ROLLBACK;
SQL
echo ">>> $MODE finished ($COMMIT_OR_ROLLBACK)"
