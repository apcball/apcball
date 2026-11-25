#!/usr/bin/env bash
# Repair of origin_remaining_value (orv) inflated/deflated by the old landed-cost code, MOG_LIVE.
#
# Bug (fixed in stock_fifo_by_location, PR #59): stock_landed_cost.button_validate booked only
#   ratio = in-stock qty / move qty of a landed cost (LC) in the SVL, but added the FULL LC to
#   origin_remaining_value. fifo_service.calculate_fifo_cost prices later issues at
#   orv / origin_remaining_qty, so the next issue of that lot is costed wrong.
#   e.g. MAC0045BPL10000 origin layer 290864: orv 3,111.82 vs ledger 2,913.24 (+198.58).
#
# Scope = "class A" only: origin layers (origin_valuation_layer_id IS NULL, orq > 0) where
#   1. the chain's remaining qty == origin_remaining_qty (stock matches), and
#   2. orv - chain remaining_value is explained by LC: |diff - sum(LC additional cost - LC value
#      booked in SVL for that move)| <= 0.05.
#   Fix: origin_remaining_value := sum(remaining_value) of the chain's positive layers (= ledger).
#   Nothing else is written: no SVL rows, no remaining_*, no quants, no moves, no journal entries.
# Class B1 (CLASSES=B1): diff is explained by vendor-bill price-difference / revaluation value-only
#   layers (no stock_landed_cost_id, e.g. `BR... (IV.../PO...)`). Standard purchase_stock adds them
#   to the layer's remaining_value only, nothing updates orv. The ledger side is right; same fix.
#   |diff + in-stock share of those layers| <= 0.05, |share| >= 0.01, not already class A.
# NOT in scope (class B3, ~270 roots, |diff| ~126k: transfer-leg cost asymmetry, mis-linked origin,
#   mixed): reported by `check` only, needs per-case review with accounting.
#
# CLASSES env (default A): which classes to fix, comma list of A,B1 (e.g. CLASSES=B1, CLASSES=A,B1).
# Modes (first arg):
#   check   read-only: class A/B counts, sums, class A list, class B top 15. Writes nothing.
#   dry     backup + audit table + UPDATE + post-checks in a transaction, ROLLBACK.
#   apply   same, COMMIT only if all checks pass. Requires EXPECT_N and EXPECT_SUM (from `check`)
#           so it aborts if the data moved since you looked:
#             CLASSES=B1 EXPECT_N=<n> EXPECT_SUM=<sum> bash scripts/fix_orv_landed_cost_class_a.sh apply
#   (class A was applied 2026-11-25: 87 layers, net +708.92, audit orv_fix_class_a_20261125_130052)
# Run dry/apply yourself (prefix with `!`); assistant sessions are blocked from prod writes.
# Audit table (kept): orv_fix_class_a_<date>. Rollback after apply:
#   UPDATE stock_valuation_layer s SET origin_remaining_value = a.old_orv
#     FROM orv_fix_class_a_<date> a WHERE s.id = a.id;
# Re-running apply is a no-op (the fixed classes are empty after a fix).
set -euo pipefail
MODE="${1:-check}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply" >&2; exit 2;; esac
STAMP=$(date +%Y%m%d_%H%M%S)
CLASSES="${CLASSES:-A}"
case "$CLASSES" in A|B1|A,B1|B1,A) ;; *) echo "CLASSES must be A, B1 or A,B1" >&2; exit 2;; esac
TAG=$(echo "$CLASSES" | tr "A-Z," "a-z_")
AUDIT="orv_fix_${TAG}_${STAMP}"

REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'

# CTE chain ending in class_a / class_b1 / class_b3 (id, default_code, wh, orq, old_orv, new_orv, diff, expected_over, n_layers, pd)
read -r -d '' CTE <<'SQLEOF' || true
WITH RECURSIVE ch AS (
  SELECT id AS root, id AS lid FROM stock_valuation_layer
   WHERE origin_valuation_layer_id IS NULL AND origin_remaining_qty > 0
  UNION
  SELECT ch.root, s.id FROM ch JOIN stock_valuation_layer s ON s.origin_valuation_layer_id = ch.lid
),
agg AS (
  SELECT ch.root,
         sum(s.remaining_qty)   FILTER (WHERE s.quantity > 0) AS chain_rq,
         sum(s.remaining_value) FILTER (WHERE s.quantity > 0) AS chain_rv,
         count(*) AS n_layers
  FROM ch JOIN stock_valuation_layer s ON s.id = ch.lid GROUP BY ch.root
),
lc AS (
  SELECT r.id root, sum(a.add_sum - coalesce(b.booked, 0)) expected_over
  FROM stock_valuation_layer r
  JOIN (SELECT cost_id, move_id, sum(additional_landed_cost) add_sum
          FROM stock_valuation_adjustment_lines GROUP BY cost_id, move_id) a ON a.move_id = r.stock_move_id
  JOIN stock_landed_cost c ON c.id = a.cost_id AND c.state = 'done'
  LEFT JOIN (SELECT stock_landed_cost_id cid, stock_move_id mid, sum(value) booked
               FROM stock_valuation_layer WHERE stock_landed_cost_id IS NOT NULL GROUP BY 1, 2) b
         ON b.cid = a.cost_id AND b.mid = a.move_id
  WHERE r.origin_valuation_layer_id IS NULL AND r.origin_remaining_qty > 0
  GROUP BY r.id
),
pd AS (   -- value-only children WITHOUT landed cost: vendor-bill price difference / revaluation
  SELECT stock_valuation_layer_id pid, sum(value) v FROM stock_valuation_layer
   WHERE quantity = 0 AND value <> 0 AND stock_landed_cost_id IS NULL AND stock_valuation_layer_id IS NOT NULL
   GROUP BY 1
),
pdagg AS (
  SELECT ch.root, sum(CASE WHEN s.quantity > 0 THEN s.remaining_qty / s.quantity * coalesce(p.v, 0) END) pd_in_stock
  FROM ch JOIN stock_valuation_layer s ON s.id = ch.lid LEFT JOIN pd p ON p.pid = s.id GROUP BY ch.root
),
cand AS (
  SELECT r.id, pp.default_code, r.warehouse_id wh, r.origin_remaining_qty orq,
         r.origin_remaining_value old_orv, round(a.chain_rv::numeric, 2) new_orv,
         round((r.origin_remaining_value - a.chain_rv)::numeric, 2) diff,
         round(coalesce(l.expected_over, 0)::numeric, 2) expected_over, a.n_layers,
         round(coalesce(pa.pd_in_stock, 0)::numeric, 2) pd
  FROM stock_valuation_layer r
  JOIN agg a ON a.root = r.id
  LEFT JOIN lc l ON l.root = r.id
  LEFT JOIN pdagg pa ON pa.root = r.id
  JOIN product_product pp ON pp.id = r.product_id
  WHERE abs(a.chain_rq - r.origin_remaining_qty) <= 0.0001
    AND abs(r.origin_remaining_value - a.chain_rv) >= 0.01
),
class_a AS (SELECT * FROM cand WHERE abs(diff - expected_over) <= 0.05),
class_b1 AS (SELECT * FROM cand WHERE abs(diff - expected_over) > 0.05
                AND abs(pd) >= 0.01 AND abs(diff + pd) <= 0.05),
class_b3 AS (SELECT * FROM cand WHERE abs(diff - expected_over) > 0.05
                AND NOT (abs(pd) >= 0.01 AND abs(diff + pd) <= 0.05))
SQLEOF

case "$CLASSES" in
  A)            TARGET_SQL="SELECT * FROM class_a" ;;
  B1)           TARGET_SQL="SELECT * FROM class_b1" ;;
  *)            TARGET_SQL="SELECT * FROM class_a UNION ALL SELECT * FROM class_b1" ;;
esac
CTE_T="$CTE
, target AS ($TARGET_SQL)"
COLS="id, default_code, wh, orq, old_orv, new_orv, diff, expected_over, pd, n_layers"

if [ "$MODE" = check ]; then
  ssh mog-prod "$REMOTE_ENV; PGOPTIONS='-c default_transaction_read_only=on' psql -h localhost -U odoo MOG_LIVE -q" <<SQL
\echo '== A = landed cost full-vs-booked / B1 = vendor-bill price-diff layers (both fixable) / B3 = other (NOT touched)'
$CTE
SELECT 'A' cls, count(*) n, round(sum(diff),2) sum_diff, round(sum(abs(diff)),2) sum_abs FROM class_a
UNION ALL SELECT 'B1', count(*), round(sum(diff),2), round(sum(abs(diff)),2) FROM class_b1
UNION ALL SELECT 'B3', count(*), round(sum(diff),2), round(sum(abs(diff)),2) FROM class_b3;
\echo '== class A list (largest 40 by |diff|)'
$CTE
SELECT $COLS FROM class_a ORDER BY abs(diff) DESC LIMIT 40;
\echo '== class B1 list (largest 40 by |diff|)'
$CTE
SELECT $COLS FROM class_b1 ORDER BY abs(diff) DESC LIMIT 40;
\echo '== class B3 top 15 by |diff| (report only)'
$CTE
SELECT $COLS FROM class_b3 ORDER BY abs(diff) DESC LIMIT 15;
SQL
  echo "== apply needs: CLASSES=<A|B1|A,B1> EXPECT_N=<count> EXPECT_SUM=<sum_diff> bash $0 apply"
  exit 0
fi

if [ "$MODE" = apply ]; then
  : "${EXPECT_N:?set EXPECT_N from check (count of the selected classes)}"
  : "${EXPECT_SUM:?set EXPECT_SUM from check (sum_diff of the selected classes)}"
else
  EXPECT_N="${EXPECT_N:--1}"; EXPECT_SUM="${EXPECT_SUM:-0}"
fi
COMMIT_OR_ROLLBACK=$([ "$MODE" = apply ] && echo COMMIT || echo ROLLBACK)

echo ">>> backup stock_valuation_layer on mog-prod (~/db_backups/svl_orv_${TAG}_${STAMP}.dump)"
ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_valuation_layer MOG_LIVE -f ~/db_backups/svl_orv_${TAG}_${STAMP}.dump && ls -l ~/db_backups/svl_orv_${TAG}_${STAMP}.dump"

ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q" <<SQL
BEGIN;
CREATE TABLE $AUDIT AS
$CTE_T
SELECT $COLS, now() AS fixed_at FROM target;
DO \$\$
DECLARE n int; s numeric;
BEGIN
  SELECT count(*), round(sum(diff), 2) INTO n, s FROM $AUDIT;
  IF n = 0 THEN RAISE EXCEPTION 'abort: nothing to fix for CLASSES=$CLASSES (already fixed?)'; END IF;
  IF $EXPECT_N >= 0 AND (n <> $EXPECT_N OR s IS DISTINCT FROM round($EXPECT_SUM::numeric, 2)) THEN
    RAISE EXCEPTION 'abort: CLASSES=$CLASSES is % rows / % but expected % / % - data moved since check', n, s, $EXPECT_N, $EXPECT_SUM;
  END IF;
  UPDATE stock_valuation_layer s SET origin_remaining_value = a.new_orv
    FROM $AUDIT a WHERE s.id = a.id AND round(s.origin_remaining_value, 2) = round(a.old_orv, 2);
  GET DIAGNOSTICS n = ROW_COUNT;
  IF n <> (SELECT count(*) FROM $AUDIT) THEN
    RAISE EXCEPTION 'abort: updated % rows, audit has %', n, (SELECT count(*) FROM $AUDIT);
  END IF;
  RAISE NOTICE 'updated % origin layers', n;
END \$\$;
\echo '== post-check: the selected classes must now be empty'
$CTE_T
SELECT (SELECT count(*) FROM class_a) class_a_left, (SELECT count(*) FROM class_b1) class_b1_left, (SELECT count(*) FROM class_b3) class_b3_unchanged;
\echo '== post-check: audited ids carry the audited value (mismatch, expect 0)'
SELECT count(*) AS mismatch FROM stock_valuation_layer s JOIN $AUDIT a ON a.id = s.id
 WHERE round(s.origin_remaining_value, 2) <> a.new_orv;
\echo '== sample'
SELECT id, default_code, old_orv, new_orv, diff, pd FROM $AUDIT ORDER BY abs(diff) DESC LIMIT 8;
$COMMIT_OR_ROLLBACK;
SQL
echo ">>> $MODE finished ($COMMIT_OR_ROLLBACK); audit table $AUDIT $( [ "$MODE" = apply ] && echo kept || echo rolled back )"
