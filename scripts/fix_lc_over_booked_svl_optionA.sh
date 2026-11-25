#!/usr/bin/env bash
# Option A for the 11 over-booked landed costs on MOG_LIVE (ids 8,171,177,232,262,298,305,312,319,320,326).
#
# Cause: before commit fdcdbf60 (2026-10-16) button_validate used an uncapped ratio, so for stock in
# several warehouses each position layer got the FULL landed cost -> SVL sum > adjustment-line sum.
# See memory landed-cost-over-booked-svl-11-lcs-2026-11-24 and the accounting Excel on the Desktop.
#
# Option A = scale every layer of an over-booked (LC, move, product) so the group sums to the adjustment
# line amount:   new_value = round(value * adj_amt / svl_amt, 2)   (rounding remainder on the largest layer).
# SCOPE (decision 1): only layers whose parent layer still holds stock (remaining_qty > 0) are changed; the
# parent's remaining_value is reduced by the same amount (button_validate had added it there). Layers on
# consumed parents (remaining_qty = 0, ~35.5k) are LEFT AS THEY ARE until it is checked whether the issue
# layers already absorbed that value. A group with both kinds of layers is only partly fixed (no rounding fix-up).
#
# Only products where SVL > adjustment line are changed. Under-booked products of the same LCs are NOT
# topped up. No stock_move, quants, remaining_qty, origin_remaining_* or journal entries are touched.
#
# Modes (first arg):
#   check   read-only: counts, totals, per-LC / per-warehouse impact. Writes nothing.
#   dry     backup, run the UPDATEs + post-checks in a transaction, ROLLBACK.
#   apply   backup, run the UPDATEs + post-checks, COMMIT only if all checks pass.
# Run dry/apply yourself (prefix with `!`) unless the user told the assistant to run it.
# Rollback after apply: restore the two columns from the backup dump (stock_valuation_layer table),
#   or from the audit table written by this script: lc_overbook_fix_20261124 (id, old_value, new_value,
#   parent_id, parent_old_rv, parent_new_rv).
set -euo pipefail
MODE="${1:-check}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply" >&2; exit 2;; esac
LCS="8,171,177,232,262,298,305,312,319,320,326"
EXPECT_ROWS=149
EXPECT_REDUCTION="22631.90"   # per-layer rounding; group totals are forced to the adjustment amount

REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'

# plan = one CTE chain ending in `plan`; used inline (check, read-only) or as a temp table (dry/apply)
PLAN_CTE="WITH adj AS (
  SELECT cost_id, move_id, product_id, sum(additional_landed_cost) adj_amt
  FROM stock_valuation_adjustment_lines GROUP BY 1,2,3),
sv AS (
  SELECT stock_landed_cost_id cost_id, stock_move_id move_id, product_id, sum(value) svl_amt
  FROM stock_valuation_layer WHERE stock_landed_cost_id IS NOT NULL GROUP BY 1,2,3),
bad AS (
  SELECT adj.*, sv.svl_amt FROM adj JOIN sv USING (cost_id, move_id, product_id)
  WHERE sv.svl_amt > adj.adj_amt + 0.05 AND adj.cost_id IN ($LCS)),
lay AS (
  SELECT s.id, s.stock_landed_cost_id cost_id, s.stock_move_id move_id, s.product_id, s.warehouse_id,
         s.value old_value, s.stock_valuation_layer_id parent_id, b.adj_amt, b.svl_amt,
         (par.remaining_qty > 0) holds,
         round((s.value * b.adj_amt / b.svl_amt)::numeric, 2) prop_value,
         row_number() OVER (PARTITION BY s.stock_landed_cost_id, s.stock_move_id, s.product_id ORDER BY s.value DESC, s.id) rn,
         count(*) OVER (PARTITION BY s.stock_landed_cost_id, s.stock_move_id, s.product_id) grp_n,
         count(*) FILTER (WHERE par.remaining_qty > 0) OVER (PARTITION BY s.stock_landed_cost_id, s.stock_move_id, s.product_id) grp_hold_n
  FROM stock_valuation_layer s
  JOIN bad b ON b.cost_id = s.stock_landed_cost_id AND b.move_id = s.stock_move_id AND b.product_id = s.product_id
  JOIN stock_valuation_layer par ON par.id = s.stock_valuation_layer_id),
plan AS (
  SELECT l.id, l.cost_id, l.move_id, l.product_id, l.warehouse_id, l.old_value, l.parent_id,
         l.prop_value + CASE WHEN l.rn = 1 AND l.grp_n = l.grp_hold_n
                             THEN round((l.adj_amt - sum(l.prop_value) OVER (PARTITION BY l.cost_id, l.move_id, l.product_id))::numeric, 2)
                             ELSE 0 END AS new_value,
         (l.grp_n = l.grp_hold_n) AS full_group
  FROM lay l WHERE l.holds)"

Q_SIZE="SELECT count(*) AS rows, round(sum(old_value - new_value), 2) AS reduction, count(DISTINCT cost_id) AS lcs FROM plan;"
Q_LC="SELECT p.cost_id, round(sum(p.old_value), 2) old_sum, round(sum(p.new_value), 2) new_sum, round(sum(p.old_value - p.new_value), 2) reduction FROM plan p GROUP BY 1 ORDER BY 1;"
Q_WH="SELECT w.code, count(*) layers, round(-sum(p.old_value - p.new_value), 2) delta FROM plan p LEFT JOIN stock_warehouse w ON w.id = p.warehouse_id GROUP BY 1 ORDER BY 3;"
Q_PAR="SELECT (par.remaining_qty > 0) parent_holds_stock, count(*) rows, round(sum(p.old_value - p.new_value), 2) reduction, count(*) FILTER (WHERE par.remaining_value < (p.old_value - p.new_value) - 0.005) would_go_negative FROM plan p JOIN stock_valuation_layer par ON par.id = p.parent_id GROUP BY 1 ORDER BY 1;"
Q_262="SELECT id, cost_id, product_id, warehouse_id, old_value, new_value, parent_id FROM plan WHERE cost_id = 262 ORDER BY id;"

report_check() {
  echo "\\echo '== plan size (see EXPECT_ROWS / EXPECT_REDUCTION)'";            echo "$PLAN_CTE $Q_SIZE"
  echo "\\echo '== per LC: SVL sum now -> after'";                                      echo "$PLAN_CTE $Q_LC"
  echo "\\echo '== per warehouse impact on SVL value'";                                 echo "$PLAN_CTE $Q_WH"
  echo "\\echo '== parent layers: still holding stock (remaining_value reduced) vs consumed (untouched)'"; echo "$PLAN_CTE $Q_PAR"
  echo "\\echo '== sample: LC 262 rows'";                                               echo "$PLAN_CTE $Q_262"
}

if [ "$MODE" = check ]; then
  report_check | ssh mog-prod "$REMOTE_ENV; PGOPTIONS='-c default_transaction_read_only=on' psql -h localhost -U odoo MOG_LIVE -q"
  echo "== nothing written"
  exit 0
fi

REPORT="\\echo '== plan size'
$Q_SIZE
\\echo '== per LC'
$Q_LC
\\echo '== per warehouse'
$Q_WH
\\echo '== parents'
$Q_PAR"
PLAN="CREATE TEMP TABLE plan ON COMMIT DROP AS $PLAN_CTE SELECT * FROM plan;"

COMMIT_OR_ROLLBACK=$([ "$MODE" = apply ] && echo COMMIT || echo ROLLBACK)
STAMP=$(date +%Y%m%d_%H%M%S)
echo ">>> backup stock_valuation_layer on mog-prod (~/db_backups/svl_lc_overbook_${STAMP}.dump)"
ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_valuation_layer MOG_LIVE -f ~/db_backups/svl_lc_overbook_${STAMP}.dump && ls -l ~/db_backups/svl_lc_overbook_${STAMP}.dump"

ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q" <<SQL
BEGIN;
$PLAN
DO \$\$
DECLARE n int; red numeric; neg int;
BEGIN
  SELECT count(*), round(sum(old_value - new_value), 2) INTO n, red FROM plan;
  IF n <> $EXPECT_ROWS OR abs(red - $EXPECT_REDUCTION) > 0.10 THEN
    RAISE EXCEPTION 'abort: plan has % rows / reduction % (expected $EXPECT_ROWS / $EXPECT_REDUCTION) - data changed or already fixed', n, red;
  END IF;
  SELECT count(*) INTO neg FROM (
    SELECT par.id FROM plan p JOIN stock_valuation_layer par ON par.id = p.parent_id
    WHERE par.remaining_qty > 0 GROUP BY par.id, par.remaining_value
    HAVING par.remaining_value < sum(p.old_value - p.new_value) - 0.005) x;
  IF neg > 0 THEN RAISE EXCEPTION 'abort: % parent layer(s) would get negative remaining_value', neg; END IF;
END \$\$;
$REPORT
CREATE TABLE IF NOT EXISTS lc_overbook_fix_20261124 (id int, old_value numeric, new_value numeric, parent_id int, parent_old_rv numeric, parent_new_rv numeric);
INSERT INTO lc_overbook_fix_20261124
SELECT p.id, p.old_value, p.new_value, p.parent_id, par.remaining_value, NULL FROM plan p JOIN stock_valuation_layer par ON par.id = p.parent_id;
UPDATE stock_valuation_layer par SET remaining_value = par.remaining_value - x.red
FROM (SELECT p.parent_id, sum(p.old_value - p.new_value) red FROM plan p
      JOIN stock_valuation_layer q ON q.id = p.parent_id WHERE q.remaining_qty > 0 GROUP BY p.parent_id) x
WHERE par.id = x.parent_id;
UPDATE stock_valuation_layer s SET value = p.new_value FROM plan p WHERE s.id = p.id;
UPDATE lc_overbook_fix_20261124 a SET parent_new_rv = par.remaining_value FROM stock_valuation_layer par WHERE par.id = a.parent_id;
\echo '== post-check: groups fully in scope now equal their adjustment amount (expect 0 rows)'
SELECT b.cost_id, b.move_id, b.product_id, round(b.svl_amt::numeric, 2) svl_now, round(b.adj_amt::numeric, 2) adj
FROM (SELECT s.stock_landed_cost_id cost_id, s.stock_move_id move_id, s.product_id, sum(s.value) svl_amt,
             (SELECT sum(additional_landed_cost) FROM stock_valuation_adjustment_lines a
               WHERE a.cost_id = s.stock_landed_cost_id AND a.move_id = s.stock_move_id AND a.product_id = s.product_id) adj_amt
      FROM stock_valuation_layer s
      WHERE (s.stock_landed_cost_id, s.stock_move_id, s.product_id) IN (SELECT cost_id, move_id, product_id FROM plan WHERE full_group)
      GROUP BY 1,2,3) b
WHERE abs(b.svl_amt - b.adj_amt) > 0.011;
\echo '== post-check: layers changed (expect EXPECT_ROWS) / negative remaining_value among touched parents (expect 0)'
SELECT (SELECT count(*) FROM stock_valuation_layer s JOIN plan p ON p.id = s.id WHERE s.value = p.new_value) changed,
       (SELECT count(*) FROM stock_valuation_layer par WHERE par.id IN (SELECT parent_id FROM plan) AND par.remaining_value < -0.005) negative_rv;
$COMMIT_OR_ROLLBACK;
SQL
echo ">>> $MODE finished ($COMMIT_OR_ROLLBACK)"
