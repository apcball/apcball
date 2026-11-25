#!/usr/bin/env bash
# Relink position layers created by inter-warehouse RETURNS to their real cost origin, MOG_LIVE.
#
# Bug (fixed in stock_fifo_by_location PR #63): the return branch of
#   _ensure_inter_warehouse_valuation_layers set the new position layer's
#   origin_valuation_layer_id to the original transfer's NEGATIVE out layer (orq 0, value 0)
#   instead of the cost origin (the receipt). The next transfer of that stock is then costed at 0
#   on the out leg (one-sided legs): RM01261100214 out 0 / in 64,177.98, RM01261100217 ...
#
# Scope (safe subset only): position layers L with
#   - quantity > 0, origin = a negative layer N, remaining_qty > 0 (still in stock), date >= 2026-03-30;
#   - the real origin R is found from the ORIGINAL transfer move of N: its other positive (dest in-leg)
#     layers all point to ONE root R (positive, no origin of its own), same product and company;
#   - L.value matches L.quantity x R unit cost within max(0.5, 0.5%) (so the stock is valued right);
#   - the root's orv/orq unit cost is within 1% of L's own unit cost (or the root has orq <= 0, where the
#     engine already falls back to L's own cost), so relinking does not change the next-issue cost.
#   Fix: origin_valuation_layer_id := R. Nothing else is written (no values, no qty, no remaining_*,
#   no quants, no moves, no journal entries).
# NOT in scope (reported by `check`): layers already consumed (history), several/ambiguous real origins,
#   a real origin that is itself a negative layer, L.value not matching the origin cost, a root whose
#   orv/orq unit differs from L's cost, roots with their own origin. Values already mis-booked by past zero out-legs (24 in Oct/Nov) are NOT corrected.
# Side effect to know: R.origin_remaining_qty/value are NOT touched. Past external sales from these
#   layers reduced N (a no-op) instead of R, so R's orq/orv may stay higher than its chain; that existing
#   gap is unchanged (later sales from the relinked layers do reduce R correctly).
#
# Modes (first arg):
#   check   read-only: counts by class, list of the fix set (largest 40), excluded classes.
#   dry     backup + audit table + UPDATE + post-checks in a transaction, ROLLBACK.
#   apply   same, COMMIT only if all checks pass. Needs EXPECT_N and EXPECT_RV from `check`:
#             EXPECT_N=<n> EXPECT_RV=<sum of remaining_value> bash scripts/fix_return_origin_relink.sh apply
# Run dry/apply yourself (prefix with `!`) or with the user's explicit go; backup is taken first.
# Audit table (kept): return_origin_relink_<stamp>. Rollback after apply:
#   UPDATE stock_valuation_layer s SET origin_valuation_layer_id = a.old_oid
#     FROM return_origin_relink_<stamp> a WHERE s.id = a.lid;
set -euo pipefail
MODE="${1:-check}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply" >&2; exit 2;; esac
STAMP=$(date +%Y%m%d_%H%M%S)
AUDIT="return_origin_relink_${STAMP}"
REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'

read -r -d '' CTE <<'SQLEOF' || true
WITH p AS (
  SELECT l.id lid, l.product_id, l.company_id, l.warehouse_id wh, l.quantity q, l.value v, l.remaining_qty rq,
         round(l.remaining_value::numeric, 2) rv, l.origin_valuation_layer_id old_oid, l.stock_move_id mv,
         coalesce(l.accounting_date, l.create_date)::date d, o.stock_move_id neg_move
  FROM stock_valuation_layer l JOIN stock_valuation_layer o ON o.id = l.origin_valuation_layer_id
  WHERE o.quantity < 0 AND l.quantity > 0 AND coalesce(l.accounting_date, l.create_date) >= '2026-03-30'
),
cand AS (
  SELECT p.lid, array_agg(DISTINCT coalesce(t.origin_valuation_layer_id, t.id))
                  FILTER (WHERE t.quantity > 0) reals
  FROM p LEFT JOIN stock_valuation_layer t ON t.stock_move_id = p.neg_move AND t.id <> p.lid
  GROUP BY p.lid
),
j AS (
  SELECT p.*, c.reals, r.id real_oid, r.quantity r_q, r.value r_v, r.origin_valuation_layer_id r_own_origin,
         r.product_id r_product, r.company_id r_company, r.origin_remaining_qty r_orq,
         r.origin_remaining_value r_orv
  FROM p JOIN cand c USING (lid)
  LEFT JOIN stock_valuation_layer r ON r.id = c.reals[1] AND array_length(c.reals, 1) = 1
),
cls AS (
  SELECT j.*,
    CASE
      WHEN j.rq <= 0 THEN 'consumed (history, not touched)'
      WHEN j.reals IS NULL OR array_length(j.reals, 1) IS NULL THEN 'no dest in-leg found'
      WHEN array_length(j.reals, 1) > 1 THEN 'several real origins'
      WHEN j.r_q IS NULL OR j.r_q <= 0 THEN 'real origin is a negative layer'
      WHEN j.r_own_origin IS NOT NULL THEN 'real origin has its own origin'
      WHEN j.r_product <> j.product_id OR j.r_company <> j.company_id THEN 'product/company differs'
      WHEN abs(j.v - j.q * (j.r_v / j.r_q)) > greatest(0.5, 0.005 * abs(j.v)) THEN 'value differs from origin cost'
      WHEN j.r_orq > 0 AND abs(j.r_orv / j.r_orq - j.v / j.q) > greatest(0.01, 0.01 * abs(j.v / j.q))
        THEN 'root orv/orq unit differs (relink would change next-issue cost)'
      ELSE 'FIX'
    END k
  FROM j
),
fixset AS (SELECT lid, old_oid, real_oid new_oid, product_id, wh, q, v, rq, rv, d, r_orq FROM cls WHERE k = 'FIX')
SQLEOF

if [ "$MODE" = check ]; then
  ssh mog-prod "$REMOTE_ENV; PGOPTIONS='-c default_transaction_read_only=on' psql -h localhost -U odoo MOG_LIVE -q" <<SQL
\echo '== position layers whose origin is a NEGATIVE layer (since 2026-03-30), by class'
$CTE
SELECT k, count(*) n, round(sum(rv)::numeric, 0) remaining_value FROM cls GROUP BY k ORDER BY (k = 'FIX') DESC, n DESC;
\echo '== fix set by month (and how many roots still have origin_remaining_qty > 0)'
$CTE
SELECT to_char(d, 'YYYY-MM') mth, count(*) n, round(sum(rv)::numeric, 0) rv, count(*) FILTER (WHERE r_orq > 0) root_orq_pos FROM fixset GROUP BY 1 ORDER BY 1;
\echo '== fix set totals (use for apply)'
$CTE
SELECT count(*) AS expect_n, round(sum(rv)::numeric, 2) AS expect_rv FROM fixset;
\echo '== largest 40 of the fix set'
$CTE
SELECT f.lid, pp.default_code, f.wh, f.q, f.rv, f.old_oid, f.new_oid, f.d FROM fixset f JOIN product_product pp ON pp.id = f.product_id ORDER BY f.rv DESC LIMIT 40;
\echo '== not fixed but in stock: top 15 by remaining_value (report only)'
$CTE
SELECT c.k, c.lid, pp.default_code, c.wh, c.q, c.rv, c.old_oid, c.real_oid FROM cls c JOIN product_product pp ON pp.id = c.product_id WHERE c.k NOT IN ('FIX', 'consumed (history, not touched)') ORDER BY c.rv DESC NULLS LAST LIMIT 15;
SQL
  echo "== apply needs: EXPECT_N=<expect_n> EXPECT_RV=<expect_rv> bash $0 apply"
  exit 0
fi

if [ "$MODE" = apply ]; then
  : "${EXPECT_N:?set EXPECT_N from check}"
  : "${EXPECT_RV:?set EXPECT_RV from check}"
else
  EXPECT_N="${EXPECT_N:--1}"; EXPECT_RV="${EXPECT_RV:-0}"
fi
COMMIT_OR_ROLLBACK=$([ "$MODE" = apply ] && echo COMMIT || echo ROLLBACK)

echo ">>> backup stock_valuation_layer on mog-prod (~/db_backups/svl_returnorigin_${STAMP}.dump)"
ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_valuation_layer MOG_LIVE -f ~/db_backups/svl_returnorigin_${STAMP}.dump && ls -l ~/db_backups/svl_returnorigin_${STAMP}.dump"

ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q" <<SQL
BEGIN;
CREATE TABLE $AUDIT AS
$CTE
SELECT lid, old_oid, new_oid, product_id, wh, q, v, rq, rv, d, now() AS fixed_at FROM fixset;
DO \$\$
DECLARE n int; s numeric;
BEGIN
  SELECT count(*), round(sum(rv), 2) INTO n, s FROM $AUDIT;
  IF n = 0 THEN RAISE EXCEPTION 'abort: nothing to fix (already done?)'; END IF;
  IF $EXPECT_N >= 0 AND (n <> $EXPECT_N OR s IS DISTINCT FROM round($EXPECT_RV::numeric, 2)) THEN
    RAISE EXCEPTION 'abort: fix set is % rows / % but expected % / % - data moved since check', n, s, $EXPECT_N, $EXPECT_RV;
  END IF;
  UPDATE stock_valuation_layer s SET origin_valuation_layer_id = a.new_oid
    FROM $AUDIT a WHERE s.id = a.lid AND s.origin_valuation_layer_id = a.old_oid;
  GET DIAGNOSTICS n = ROW_COUNT;
  IF n <> (SELECT count(*) FROM $AUDIT) THEN
    RAISE EXCEPTION 'abort: updated % rows, audit has %', n, (SELECT count(*) FROM $AUDIT);
  END IF;
  RAISE NOTICE 'relinked % position layers', n;
END \$\$;
\echo '== post-check: fix set must now be empty'
$CTE
SELECT count(*) AS fix_left FROM fixset;
\echo '== post-check: no audited layer still points to a negative layer, and nothing but the origin link changed'
SELECT count(*) AS still_negative_origin FROM stock_valuation_layer s JOIN $AUDIT a ON a.lid = s.id JOIN stock_valuation_layer o ON o.id = s.origin_valuation_layer_id WHERE o.quantity < 0;
SELECT count(*) AS value_or_qty_changed FROM stock_valuation_layer s JOIN $AUDIT a ON a.lid = s.id
 WHERE round(s.value::numeric, 2) <> round(a.v::numeric, 2) OR s.quantity <> a.q OR round(s.remaining_qty::numeric, 4) <> round(a.rq::numeric, 4);
\echo '== sample'
SELECT a.lid, pp.default_code, a.old_oid, a.new_oid, a.rq, a.rv FROM $AUDIT a JOIN product_product pp ON pp.id = a.product_id ORDER BY a.rv DESC LIMIT 8;
$COMMIT_OR_ROLLBACK;
SQL
echo ">>> $MODE finished ($COMMIT_OR_ROLLBACK); audit table $AUDIT $( [ "$MODE" = apply ] && echo kept || echo rolled back )"
