#!/usr/bin/env bash
# Repair of 3 out legs booked at 0 on picking RM01261100214 (RM-NI wh25 -> RM01 wh13), MOG_LIVE, 2026-11-24.
#
# Sequence for each product: receipt RM-NI/IN2611005 (+X at wh25) -> RM01261100209 transfer (wh25 -X, wh13 +X)
#   -> RM01261100212 return (wh13 -X, wh25 +X) -> RM01261100214 transfer again (wh25 ???, wh13 +X).
# The return's position layer pointed at the original transfer's NEGATIVE out layer (bug fixed in
# stock_fifo_by_location PR #63), so the re-transfer consumed it at origin value 0: out leg booked 0 while
# the in leg carries the full X. wh25 keeps X of value with 0 qty and the same value is also at wh13
# (stock value counted twice).
#
#   out layer 318005 WB0004A100  300 u  in-leg 318004 30,449.67
#   out layer 318007 SP0024100   600 u  in-leg 318006 64,177.98
#   out layer 318011 FCF0004100  200 u  in-leg 318010 22,160.80      total 116,788.45
#
# Fix: out-leg value := -in-leg value (unit_cost := value/qty) and the matching consumed_origin_splits value.
# Nothing else is written (no qty, remaining_*, origin links, quants, moves, journal entries).
#
# Modes (first arg):
#   check   read-only: print the 3 layers, the in-legs and the stuck value at wh25. Writes nothing.
#   dry     backup + audit table + UPDATE + post-checks in a transaction, ROLLBACK.
#   apply   same, COMMIT only if every check passes.
# Audit table (kept): zero_out_legs_fix_<stamp>. Rollback after apply:
#   UPDATE stock_valuation_layer s SET value = a.old_value, unit_cost = a.old_unit_cost,
#          consumed_origin_splits = a.old_splits
#     FROM zero_out_legs_fix_<stamp> a WHERE s.id = a.id;
set -euo pipefail
MODE="${1:-check}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply" >&2; exit 2;; esac
STAMP=$(date +%Y%m%d_%H%M%S)
AUDIT="zero_out_legs_fix_${STAMP}"
REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'

read -r -d '' CTE <<'SQLEOF' || true
WITH t(out_id, in_id, exp_in) AS (VALUES (318005, 318004, 30449.67), (318007, 318006, 64177.98), (318011, 318010, 22160.80)),
x AS (
  SELECT t.out_id id, t.in_id, t.exp_in, o.stock_move_id mid, o.product_id, o.warehouse_id wh, o.quantity q, o.value old_value, o.unit_cost old_unit_cost,
         o.consumed_origin_splits old_splits, i.value in_value, i.quantity in_q, i.warehouse_id in_wh, m.reference
  FROM t JOIN stock_valuation_layer o ON o.id = t.out_id
  JOIN stock_valuation_layer i ON i.id = t.in_id
  JOIN stock_move m ON m.id = o.stock_move_id
),
good AS (
  SELECT * FROM x
  WHERE reference = 'RM01261100214' AND wh = 25 AND in_wh = 13 AND q < 0 AND old_value = 0
    AND in_q = -q AND round(in_value::numeric, 2) = exp_in
    AND old_splits IS NOT NULL AND old_splits <> '' AND jsonb_array_length(old_splits::jsonb) = 1
    AND (old_splits::jsonb->0->>2)::numeric = 0
)
SQLEOF

if [ "$MODE" = check ]; then
  ssh mog-prod "$REMOTE_ENV; PGOPTIONS='-c default_transaction_read_only=on' psql -h localhost -U odoo MOG_LIVE -q" <<SQL
\echo '== the 3 out legs and their in legs (all conditions met = listed in good)'
$CTE
SELECT x.id out_id, x.in_id, x.reference, x.wh, x.q, x.old_value, round(x.in_value::numeric,2) in_value, x.old_splits,
       (x.id IN (SELECT id FROM good)) AS conditions_ok FROM x ORDER BY x.id;
\echo '== stuck value at wh25 before (value with 0 qty) for the 3 products'
$CTE
SELECT pp.default_code, sum(l.quantity) qty, round(sum(l.value)::numeric,2) value
FROM stock_valuation_layer l JOIN product_product pp ON pp.id = l.product_id
WHERE l.warehouse_id = 25 AND l.product_id IN (SELECT DISTINCT product_id FROM x) GROUP BY 1 ORDER BY 1;
\echo '== same products at wh13'
$CTE
SELECT pp.default_code, sum(l.quantity) qty, round(sum(l.value)::numeric,2) value
FROM stock_valuation_layer l JOIN product_product pp ON pp.id = l.product_id
WHERE l.warehouse_id = 13 AND l.product_id IN (SELECT DISTINCT product_id FROM x) GROUP BY 1 ORDER BY 1;
SQL
  echo "== apply needs: EXPECT_N=3 EXPECT_VALUE=116788.45 bash $0 apply"
  exit 0
fi

if [ "$MODE" = apply ]; then
  : "${EXPECT_N:?set EXPECT_N=3}"; : "${EXPECT_VALUE:?set EXPECT_VALUE=116788.45}"
else
  EXPECT_N="${EXPECT_N:-3}"; EXPECT_VALUE="${EXPECT_VALUE:-116788.45}"
fi
COMMIT_OR_ROLLBACK=$([ "$MODE" = apply ] && echo COMMIT || echo ROLLBACK)

echo ">>> backup stock_valuation_layer on mog-prod (~/db_backups/svl_zeroout_${STAMP}.dump)"
ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_valuation_layer MOG_LIVE -f ~/db_backups/svl_zeroout_${STAMP}.dump && ls -l ~/db_backups/svl_zeroout_${STAMP}.dump"

ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q" <<SQL
BEGIN;
CREATE TABLE $AUDIT AS
$CTE
SELECT id, in_id, mid, product_id, wh, q, old_value, old_unit_cost, old_splits,
       -round(in_value::numeric, 2) AS new_value, round((in_value / -q)::numeric, 6) AS new_unit_cost, now() AS fixed_at FROM good;
DO \$\$
DECLARE n int; s numeric;
BEGIN
  SELECT count(*), -sum(new_value) INTO n, s FROM $AUDIT;
  IF n <> $EXPECT_N OR s IS DISTINCT FROM round($EXPECT_VALUE::numeric, 2) THEN
    RAISE EXCEPTION 'abort: % layers / % but expected % / % - conditions not met or data moved', n, s, $EXPECT_N, $EXPECT_VALUE;
  END IF;
  UPDATE stock_valuation_layer s
     SET value = a.new_value, unit_cost = a.new_unit_cost,
         consumed_origin_splits = jsonb_build_array(jsonb_build_array(
             (a.old_splits::jsonb->0->>0)::int, (a.old_splits::jsonb->0->>1)::numeric, -a.new_value))::text
    FROM $AUDIT a WHERE s.id = a.id AND s.value = 0;
  GET DIAGNOSTICS n = ROW_COUNT;
  IF n <> $EXPECT_N THEN RAISE EXCEPTION 'abort: updated % rows, expected %', n, $EXPECT_N; END IF;
  RAISE NOTICE 'fixed % out legs', n;
END \$\$;
\echo '== post-check: stuck value at wh25 (expect value 0 where qty 0) for the 3 products'
SELECT pp.default_code, sum(l.quantity) qty, round(sum(l.value)::numeric,2) value
FROM stock_valuation_layer l JOIN product_product pp ON pp.id = l.product_id
WHERE l.warehouse_id = 25 AND l.product_id IN (SELECT DISTINCT product_id FROM $AUDIT) GROUP BY 1 ORDER BY 1;
\echo '== post-check: only value/unit_cost/splits changed on the audited ids (expect 0)'
SELECT count(*) AS other_changed FROM stock_valuation_layer s JOIN $AUDIT a ON a.id = s.id WHERE s.quantity <> a.q OR s.warehouse_id <> a.wh OR s.remaining_qty <> 0;
\echo '== post-check: move-level legs now equal (out = in)'
SELECT m.reference, pp.default_code, round(sum(l.value) FILTER (WHERE l.quantity > 0)::numeric, 2) in_v, round(-sum(l.value) FILTER (WHERE l.quantity < 0)::numeric, 2) out_v
FROM stock_valuation_layer l JOIN stock_move m ON m.id = l.stock_move_id JOIN product_product pp ON pp.id = l.product_id
WHERE l.stock_move_id IN (SELECT mid FROM $AUDIT) GROUP BY 1, 2 ORDER BY 2;
$COMMIT_OR_ROLLBACK;
SQL
echo ">>> $MODE finished ($COMMIT_OR_ROLLBACK); audit table $AUDIT $( [ "$MODE" = apply ] && echo kept || echo rolled back )"
