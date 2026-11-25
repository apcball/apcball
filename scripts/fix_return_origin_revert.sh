#!/usr/bin/env bash
# Revert return position layers that fix_return_origin_relink.sh attached to a lot they do not belong to
# and that fix_return_origin_rehome.sh could not re-home, MOG_LIVE.
#
# Set = layers written by the 3 relink rounds (audit tables return_origin_relink_20261125_142846 / _142910 /
# _150725) that are still attached to the root the relink chose, still in stock, and whose root exceeds its
# origin_remaining_qty ONLY because of the layers moved into it (no candidate lot, ambiguous, or colliding):
# 85 layers, remaining value 208,139 at the time of writing.
# Fix: origin_valuation_layer_id := the ORIGINAL origin (old_oid in the relink audit tables = the negative out
# layer of the original transfer). Nothing else is written.
#
# Known downside (accepted): with a negative layer as origin the engine falls back to the layer's own unit cost
# for sales (fine), but a later TRANSFER out of such a layer books its out leg at 0 (see PR #63 / the 3 legs
# repaired on RM01261100214). Prefer re-homing when the real lot becomes known.
#
# Modes (first arg):
#   check   read-only: counts and the full list. Writes nothing.
#   dry     backup + audit table + UPDATE + post-checks in a transaction, ROLLBACK.
#   apply   same, COMMIT only if every check passes. Needs EXPECT_N (and EXPECT_RV) from `check`:
#             EXPECT_N=<n> EXPECT_RV=<sum rv> bash scripts/fix_return_origin_revert.sh apply
# Audit table (kept): return_origin_revert_<stamp>. Rollback after apply (puts them back on the wrong lot):
#   UPDATE stock_valuation_layer s SET origin_valuation_layer_id = a.cur_root
#     FROM return_origin_revert_<stamp> a WHERE s.id = a.lid;
set -euo pipefail
MODE="${1:-check}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply" >&2; exit 2;; esac
STAMP=$(date +%Y%m%d_%H%M%S)
AUDIT="return_origin_revert_${STAMP}"
REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'

read -r -d '' CTE <<'SQLEOF' || true
WITH aud AS (
  SELECT lid, old_oid, new_oid FROM return_origin_relink_20261125_142846
  UNION ALL SELECT lid, old_oid, new_oid FROM return_origin_relink_20261125_142910
  UNION ALL SELECT lid, old_oid, new_oid FROM return_origin_relink_20261125_150725
),
rootstat AS (
  SELECT r.new_oid root, (SELECT product_id FROM stock_valuation_layer x WHERE x.id = r.new_oid) product_id,
    coalesce(sum(s.remaining_qty) FILTER (WHERE s.quantity > 0), 0)
      + (SELECT coalesce(remaining_qty, 0) FROM stock_valuation_layer x WHERE x.id = r.new_oid) live,
    (SELECT origin_remaining_qty FROM stock_valuation_layer x WHERE x.id = r.new_oid) orq,
    (SELECT coalesce(sum(l.remaining_qty), 0) FROM aud a JOIN stock_valuation_layer l ON l.id = a.lid WHERE a.new_oid = r.new_oid) applied_rq
  FROM (SELECT DISTINCT new_oid FROM aud) r LEFT JOIN stock_valuation_layer s ON s.origin_valuation_layer_id = r.new_oid
  GROUP BY r.new_oid
),
target AS (
  SELECT a.lid, a.new_oid cur_root, a.old_oid orig_oid, rs.product_id, l.warehouse_id wh, l.remaining_qty rq,
         round(l.remaining_value::numeric, 2) rv, l.quantity q, round(l.value::numeric, 2) v
  FROM aud a JOIN rootstat rs ON rs.root = a.new_oid JOIN stock_valuation_layer l ON l.id = a.lid
  WHERE rs.live > rs.orq + 0.0001 AND rs.live - rs.applied_rq <= rs.orq + 0.0001
    AND l.origin_valuation_layer_id = a.new_oid AND l.remaining_qty > 0
    AND (SELECT o.quantity FROM stock_valuation_layer o WHERE o.id = a.old_oid) < 0
)
SQLEOF

if [ "$MODE" = check ]; then
  ssh mog-prod "$REMOTE_ENV; PGOPTIONS='-c default_transaction_read_only=on' psql -h localhost -U odoo MOG_LIVE -q" <<SQL
\echo '== layers to revert (attached by relink, root over orq only because of them, original origin is a negative layer)'
$CTE
SELECT count(*) AS expect_n, round(sum(rv), 2) AS expect_rv, count(DISTINCT cur_root) roots FROM target;
\echo '== by month of the layer... top 25 by remaining value'
$CTE
SELECT t.lid, pp.default_code, t.wh, t.rq, t.rv, t.cur_root, t.orig_oid FROM target t JOIN product_product pp ON pp.id = t.product_id ORDER BY t.rv DESC LIMIT 25;
SQL
  echo "== apply needs: EXPECT_N=<expect_n> EXPECT_RV=<expect_rv> bash $0 apply"
  exit 0
fi

if [ "$MODE" = apply ]; then : "${EXPECT_N:?set EXPECT_N from check}"; : "${EXPECT_RV:?set EXPECT_RV from check}"
else EXPECT_N="${EXPECT_N:--1}"; EXPECT_RV="${EXPECT_RV:-0}"; fi
COMMIT_OR_ROLLBACK=$([ "$MODE" = apply ] && echo COMMIT || echo ROLLBACK)

echo ">>> backup stock_valuation_layer on mog-prod (~/db_backups/svl_revert_${STAMP}.dump)"
ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_valuation_layer MOG_LIVE -f ~/db_backups/svl_revert_${STAMP}.dump && ls -l ~/db_backups/svl_revert_${STAMP}.dump"

ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q" <<SQL
BEGIN;
CREATE TABLE $AUDIT AS
$CTE
SELECT lid, cur_root, orig_oid, product_id, wh, rq, rv, q, v, now() AS fixed_at FROM target;
DO \$\$
DECLARE n int; s numeric;
BEGIN
  SELECT count(*), round(sum(rv), 2) INTO n, s FROM $AUDIT;
  IF n = 0 THEN RAISE EXCEPTION 'abort: nothing to revert'; END IF;
  IF $EXPECT_N >= 0 AND (n <> $EXPECT_N OR s IS DISTINCT FROM round($EXPECT_RV::numeric, 2)) THEN
    RAISE EXCEPTION 'abort: % rows / % but expected % / % - data moved since check', n, s, $EXPECT_N, $EXPECT_RV;
  END IF;
  UPDATE stock_valuation_layer s SET origin_valuation_layer_id = a.orig_oid
    FROM $AUDIT a WHERE s.id = a.lid AND s.origin_valuation_layer_id = a.cur_root;
  GET DIAGNOSTICS n = ROW_COUNT;
  IF n <> (SELECT count(*) FROM $AUDIT) THEN RAISE EXCEPTION 'abort: updated % rows, audit has %', n, (SELECT count(*) FROM $AUDIT); END IF;
  RAISE NOTICE 'reverted % layers', n;
END \$\$;
\echo '== post-check: nothing but the origin link changed (expect 0)'
SELECT count(*) AS other_changed FROM stock_valuation_layer s JOIN $AUDIT a ON a.lid = s.id
 WHERE round(s.remaining_value::numeric, 2) <> a.rv OR round(s.remaining_qty::numeric, 4) <> round(a.rq::numeric, 4)
    OR round(s.value::numeric, 2) <> a.v OR s.quantity <> a.q;
\echo '== post-check: touched roots over orq because of reverted layers (expect 0 roots)'
SELECT count(*) AS roots_still_over_due_to_reverted FROM (
  SELECT a.cur_root, coalesce(sum(s.remaining_qty) FILTER (WHERE s.quantity > 0), 0)
           + (SELECT coalesce(remaining_qty, 0) FROM stock_valuation_layer x WHERE x.id = a.cur_root) live,
         (SELECT origin_remaining_qty FROM stock_valuation_layer x WHERE x.id = a.cur_root) orq
  FROM (SELECT DISTINCT cur_root FROM $AUDIT) a LEFT JOIN stock_valuation_layer s ON s.origin_valuation_layer_id = a.cur_root
  GROUP BY a.cur_root) z
WHERE z.live > z.orq + 0.0001;
\echo '== post-check: reverted layers all point at a negative layer again'
SELECT count(*) FILTER (WHERE o.quantity < 0) neg_origin, count(*) total FROM stock_valuation_layer s JOIN $AUDIT a ON a.lid = s.id JOIN stock_valuation_layer o ON o.id = s.origin_valuation_layer_id;
$COMMIT_OR_ROLLBACK;
SQL
echo ">>> $MODE finished ($COMMIT_OR_ROLLBACK); audit table $AUDIT $( [ "$MODE" = apply ] && echo kept || echo rolled back )"
