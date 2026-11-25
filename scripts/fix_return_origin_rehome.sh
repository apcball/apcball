#!/usr/bin/env bash
# Re-home return position layers that fix_return_origin_relink.sh attached to the WRONG lot, MOG_LIVE.
#
# Why: the relink script finds the real origin from the ORIGINAL transfer move's dest in-leg. When the
# returned units physically came from a DIFFERENT lot (the return-out consumed another lot at the same
# warehouse) that link is wrong, and the value check cannot see it (the return in-leg copies the value of
# the original out leg). Symptom: the root the layer was attached to now holds MORE live qty than its
# origin_remaining_qty, only because of the layer, while another root of the same product has a deficit of
# exactly the layer's qty. Pilot: MCV0000E0010000 layer 253083 belongs to root 248103 (RM01/2608068), not 239453.
#
# Classes (CLASSES env, default REHOME):
#   MCV      explicit pilot: layer 253083 (return in, wh25) -> root 248103; checked: same product, 248103 has
#            origin_remaining_qty 300, no live qty in its chain (deficit 300) and its own remaining_qty is 0.
#   REHOME   layers written by the 3 relink rounds (audit tables return_origin_relink_20261125_142846/_142910/
#            _150725) whose current root exceeds orq only because of them AND exactly ONE other root of the same
#            product has a deficit equal to the layer qty AND that candidate had a used-up layer at the return's
#            source warehouse before the return (it is the lot that was physically consumed) AND no other
#            layer points at the same candidate (a root short by N units can only take N units).
#   Not touched: layers with no candidate or several candidates (report-only in `check`).
# Writes only origin_valuation_layer_id. No values, qty, remaining_*, quants, moves or journal entries.
#
# Modes (first arg):
#   check   read-only: class counts and the full list. Writes nothing.
#   dry     backup + audit table + UPDATE + post-checks in a transaction, ROLLBACK.
#   apply   same, COMMIT only if every check passes. Needs EXPECT_N for the selected classes:
#             CLASSES=MCV,REHOME EXPECT_N=<n> bash scripts/fix_return_origin_rehome.sh apply
# Audit table (kept): return_origin_rehome_<stamp>. Rollback after apply:
#   UPDATE stock_valuation_layer s SET origin_valuation_layer_id = a.old_oid
#     FROM return_origin_rehome_<stamp> a WHERE s.id = a.lid;
set -euo pipefail
MODE="${1:-check}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply" >&2; exit 2;; esac
CLASSES="${CLASSES:-REHOME}"
for c in $(echo "$CLASSES" | tr "," " "); do
  case "$c" in MCV|REHOME) ;; *) echo "CLASSES must be a comma list of MCV,REHOME (got $c)" >&2; exit 2;; esac
done
STAMP=$(date +%Y%m%d_%H%M%S)
AUDIT="return_origin_rehome_${STAMP}"
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
bad AS (
  SELECT a.lid, a.new_oid cur_root, rs.product_id, l.remaining_qty lq, round(l.remaining_value::numeric, 2) lrv,
         coalesce(l.accounting_date, l.create_date) ld, l.warehouse_id lwh,
         (SELECT o.warehouse_id FROM stock_valuation_layer o WHERE o.stock_move_id = l.stock_move_id AND o.quantity < 0 LIMIT 1) src_wh
  FROM aud a JOIN rootstat rs ON rs.root = a.new_oid JOIN stock_valuation_layer l ON l.id = a.lid
  WHERE rs.live > rs.orq + 0.0001 AND rs.live - rs.applied_rq <= rs.orq + 0.0001
    AND l.origin_valuation_layer_id = a.new_oid AND l.remaining_qty > 0
),
defs AS (
  SELECT r.id root, r.product_id,
         r.origin_remaining_qty - coalesce((SELECT sum(s.remaining_qty) FROM stock_valuation_layer s WHERE s.origin_valuation_layer_id = r.id AND s.quantity > 0), 0)
           - coalesce(r.remaining_qty, 0) deficit
  FROM stock_valuation_layer r
  WHERE r.origin_valuation_layer_id IS NULL AND r.origin_remaining_qty > 0 AND r.quantity > 0
    AND coalesce(r.accounting_date, r.create_date) >= '2026-03-30'
),
cand AS (
  SELECT b.lid, d.root cand_root,
    EXISTS (SELECT 1 FROM stock_valuation_layer s
             WHERE (s.id = d.root OR s.origin_valuation_layer_id = d.root) AND s.quantity > 0
               AND s.warehouse_id = b.src_wh AND s.remaining_qty < 0.0001
               AND coalesce(s.accounting_date, s.create_date) <= b.ld) used_at_src
  FROM bad b JOIN defs d ON d.product_id = b.product_id AND d.root <> b.cur_root AND abs(d.deficit - b.lq) < 0.0001
),
uniq AS (
  SELECT b.lid, (SELECT c.cand_root FROM cand c WHERE c.lid = b.lid AND c.used_at_src) cand_root
  FROM bad b WHERE (SELECT count(*) FROM cand c WHERE c.lid = b.lid AND c.used_at_src) = 1
),
rehome AS (
  -- one candidate root per layer AND one layer per candidate root (a root short by N can only take N units)
  SELECT b.lid, b.cur_root old_oid, u.cand_root new_oid, b.product_id, b.lwh wh, b.lq rq, b.lrv rv, 'REHOME'::text cls
  FROM bad b JOIN uniq u ON u.lid = b.lid
  WHERE (SELECT count(*) FROM uniq u2 WHERE u2.cand_root = u.cand_root) = 1
),
mcv AS (
  SELECT l.id lid, l.origin_valuation_layer_id old_oid, 248103 new_oid, l.product_id, l.warehouse_id wh, l.remaining_qty rq,
         round(l.remaining_value::numeric, 2) rv, 'MCV'::text cls
  FROM stock_valuation_layer l, stock_valuation_layer r
  WHERE l.id = 253083 AND r.id = 248103 AND l.product_id = r.product_id AND l.warehouse_id = 25 AND l.remaining_qty = 300
    AND l.origin_valuation_layer_id = 239454 AND r.origin_remaining_qty = 300 AND r.remaining_qty = 0
    AND NOT EXISTS (SELECT 1 FROM stock_valuation_layer s WHERE s.origin_valuation_layer_id = 248103 AND s.quantity > 0 AND s.remaining_qty > 0)
),
allset AS (SELECT * FROM rehome UNION ALL SELECT * FROM mcv),
target AS (SELECT * FROM allset WHERE cls = ANY (string_to_array('__CLASSES__', ',')))
SQLEOF
CTE="${CTE//__CLASSES__/$CLASSES}"

if [ "$MODE" = check ]; then
  ssh mog-prod "$REMOTE_ENV; PGOPTIONS='-c default_transaction_read_only=on' psql -h localhost -U odoo MOG_LIVE -q" <<SQL
\echo '== layers attached to a root that exceeds its orq only because of them (from the 3 relink rounds)'
$CTE
SELECT (SELECT count(*) FROM bad) bad_layers, (SELECT round(sum(lrv), 0) FROM bad) rv,
       (SELECT count(*) FROM uniq) unique_candidate_refined, (SELECT count(*) FROM rehome) rehome_after_one_layer_per_root,
       (SELECT count(*) FROM bad b WHERE (SELECT count(*) FROM cand c WHERE c.lid = b.lid AND c.used_at_src) = 0) no_candidate,
       (SELECT count(*) FROM bad b WHERE (SELECT count(*) FROM cand c WHERE c.lid = b.lid AND c.used_at_src) > 1) ambiguous;
\echo '== MCV pilot conditions met?'
$CTE
SELECT count(*) mcv_ok FROM mcv;
\echo '== target set for CLASSES=$CLASSES'
$CTE
SELECT t.cls, t.lid, pp.default_code, t.wh, t.rq, t.rv, t.old_oid, t.new_oid FROM target t JOIN product_product pp ON pp.id = t.product_id ORDER BY t.rv DESC;
\echo '== totals for apply'
$CTE
SELECT count(*) AS expect_n, round(sum(rv), 2) AS rv FROM target;
SQL
  echo "== apply needs: CLASSES=$CLASSES EXPECT_N=<expect_n> bash $0 apply"
  exit 0
fi

if [ "$MODE" = apply ]; then : "${EXPECT_N:?set EXPECT_N from check}"; else EXPECT_N="${EXPECT_N:--1}"; fi
COMMIT_OR_ROLLBACK=$([ "$MODE" = apply ] && echo COMMIT || echo ROLLBACK)

echo ">>> backup stock_valuation_layer on mog-prod (~/db_backups/svl_rehome_${STAMP}.dump)"
ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_valuation_layer MOG_LIVE -f ~/db_backups/svl_rehome_${STAMP}.dump && ls -l ~/db_backups/svl_rehome_${STAMP}.dump"

ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q" <<SQL
BEGIN;
CREATE TABLE $AUDIT AS
$CTE
SELECT lid, old_oid, new_oid, product_id, wh, rq, rv, cls, now() AS fixed_at FROM target;
DO \$\$
DECLARE n int;
BEGIN
  SELECT count(*) INTO n FROM $AUDIT;
  IF n = 0 THEN RAISE EXCEPTION 'abort: nothing to fix'; END IF;
  IF $EXPECT_N >= 0 AND n <> $EXPECT_N THEN RAISE EXCEPTION 'abort: % rows but expected % - data moved since check', n, $EXPECT_N; END IF;
  UPDATE stock_valuation_layer s SET origin_valuation_layer_id = a.new_oid
    FROM $AUDIT a WHERE s.id = a.lid AND s.origin_valuation_layer_id = a.old_oid;
  GET DIAGNOSTICS n = ROW_COUNT;
  IF n <> (SELECT count(*) FROM $AUDIT) THEN RAISE EXCEPTION 'abort: updated % rows, audit has %', n, (SELECT count(*) FROM $AUDIT); END IF;
  RAISE NOTICE 'rehomed % layers', n;
END \$\$;
\echo '== post-check: nothing but the origin link changed (expect 0)'
SELECT count(*) AS other_changed FROM stock_valuation_layer s JOIN $AUDIT a ON a.lid = s.id
 WHERE round(s.remaining_value::numeric, 2) <> a.rv OR round(s.remaining_qty::numeric, 4) <> round(a.rq::numeric, 4);
\echo '== post-check: new roots no longer short, old roots no longer over (live qty vs orq)'
SELECT a.cls, count(*) layers,
  count(*) FILTER (WHERE abs(nr.live - nr.orq) < 0.0001) new_root_ties,
  count(*) FILTER (WHERE orr.live <= orr.orq + 0.0001) old_root_not_over
FROM $AUDIT a
JOIN LATERAL (SELECT coalesce(sum(s.remaining_qty) FILTER (WHERE s.quantity > 0), 0) + (SELECT coalesce(remaining_qty, 0) FROM stock_valuation_layer x WHERE x.id = a.new_oid) live,
                     (SELECT origin_remaining_qty FROM stock_valuation_layer x WHERE x.id = a.new_oid) orq
              FROM stock_valuation_layer s WHERE s.origin_valuation_layer_id = a.new_oid) nr ON true
JOIN LATERAL (SELECT coalesce(sum(s.remaining_qty) FILTER (WHERE s.quantity > 0), 0) + (SELECT coalesce(remaining_qty, 0) FROM stock_valuation_layer x WHERE x.id = a.old_oid) live,
                     (SELECT origin_remaining_qty FROM stock_valuation_layer x WHERE x.id = a.old_oid) orq
              FROM stock_valuation_layer s WHERE s.origin_valuation_layer_id = a.old_oid) orr ON true
GROUP BY a.cls;
\echo '== sample'
SELECT a.lid, pp.default_code, a.old_oid, a.new_oid, a.rq, a.rv, a.cls FROM $AUDIT a JOIN product_product pp ON pp.id = a.product_id ORDER BY a.rv DESC LIMIT 8;
$COMMIT_OR_ROLLBACK;
SQL
echo ">>> $MODE finished ($COMMIT_OR_ROLLBACK); audit table $AUDIT $( [ "$MODE" = apply ] && echo kept || echo rolled back )"
