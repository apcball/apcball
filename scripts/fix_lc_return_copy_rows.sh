#!/usr/bin/env bash
# Zero the landed-cost allocation rows that returns copied, MOG_LIVE (table
# stock_valuation_layer_landed_cost only).
#
# Bug: stock_fifo_by_location._copy_landed_cost_to_return gave every return
#   (all rows of the product at the original warehouse) x returned qty / queued qty
# so the values compounded (MO00790111: 1,419M THB). A later return of the returned lot adds
# those rows on top of the lot's cost. The landed cost of a returned lot is already inside its
# valuation layer value, so such a row is never owed.
#
# Rows selected: no landed_cost_id and no adjustment line, layer's move is a return, value <> 0.
#   SCOPE=all       every such row
#   SCOPE=inflated  only rows whose per-unit amount exceeds the layer's own unit value
# Writes landed_cost_value := 0 (rows are kept). Nothing else: no SVL, moves, quants or journals.
# Values already booked into valuation layers are NOT changed here.
#
# Modes (first arg):
#   check   read-only: counts and sums of both scopes, largest rows, whether the code fix is live
#   dry     SCOPE=... : table dump + audit table + UPDATE + post-checks in a transaction, ROLLBACK
#           (EXPECT_N / EXPECT_SUM optional, checked when given)
#   apply   same, COMMIT. Needs SCOPE, EXPECT_N and EXPECT_SUM (from `check`), and refuses unless
#           the fixed code is on the server and instance1 was restarted after it, otherwise the
#           old code would add new rows again:
#             SCOPE=all EXPECT_N=<n> EXPECT_SUM=<sum> bash scripts/fix_lc_return_copy_rows.sh apply
# Run apply yourself (prefix with `!`).
# Backup: ~/db_backups/lc_side_<stamp>.dump on mog-prod, audit table lc_return_copy_fix_<stamp>.
# Rollback after apply:
#   UPDATE stock_valuation_layer_landed_cost t SET landed_cost_value = a.old_value
#     FROM lc_return_copy_fix_<stamp> a WHERE t.id = a.id;
set -euo pipefail
MODE="${1:-check}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply" >&2; exit 2;; esac
STAMP=$(date +%Y%m%d_%H%M%S)
AUDIT="lc_return_copy_fix_${STAMP}"
REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW##*= }"'
PSQL='psql -h localhost -U odoo MOG_LIVE -X -P footer=off -v ON_ERROR_STOP=1'
CODE=/opt/instance1/odoo17/custom-addons/stock_fifo_by_location/models/stock_move.py

# ctime, not mtime: rsync keeps the local edit time, the arrival time is what counts
code_live() {
  ssh mog-prod "grep -q 'Deliberately does nothing' $CODE || { echo 'no: old code on the server'; exit 0; }
    started=\$(date -d \"\$(systemctl show instance1 -p ActiveEnterTimestamp --value)\" +%s)
    changed=\$(stat -c %Z $CODE)
    if [ \"\$started\" -gt \"\$changed\" ]; then echo yes; else echo 'no: instance1 not restarted since the file changed'; fi"
}

SELECTION="
  SELECT t.id, p.default_code, t.valuation_layer_id, t.warehouse_id, t.quantity,
         t.landed_cost_value AS old_value,
         (t.quantity > 0 AND l.quantity <> 0
          AND t.landed_cost_value / t.quantity > abs(l.value / l.quantity)) AS inflated
    FROM stock_valuation_layer_landed_cost t
    JOIN stock_valuation_layer l ON l.id = t.valuation_layer_id
    JOIN stock_move m ON m.id = l.stock_move_id
    JOIN product_product p ON p.id = t.product_id
   WHERE t.landed_cost_id IS NULL AND t.valuation_adjustment_line_id IS NULL
     AND m.origin_returned_move_id IS NOT NULL
     AND t.landed_cost_value <> 0"

if [ "$MODE" = check ]; then
  echo "code fix live: $(code_live)"
  ssh mog-prod "$REMOTE_ENV; PGOPTIONS='-c default_transaction_read_only=on' $PSQL" <<SQL
\echo == by scope
WITH s AS ($SELECTION)
SELECT 'all' AS scope, count(*) AS n, round(sum(old_value)::numeric, 2) AS sum, count(DISTINCT default_code) AS products FROM s
UNION ALL
SELECT 'inflated', count(*), round(sum(old_value)::numeric, 2), count(DISTINCT default_code) FROM s WHERE inflated;
\echo == largest rows
WITH s AS ($SELECTION)
SELECT id, default_code, valuation_layer_id AS layer, warehouse_id AS wh, quantity, round(old_value::numeric, 2) AS value, inflated
  FROM s ORDER BY old_value DESC LIMIT 12;
SQL
  exit 0
fi

case "${SCOPE:-}" in
  all) FILTER="true" ;;
  inflated) FILTER="inflated" ;;
  *) echo "set SCOPE=all or SCOPE=inflated" >&2; exit 2 ;;
esac
END="ROLLBACK"
EXPECT=""
if [ "$MODE" = apply ]; then
  : "${EXPECT_N:?set EXPECT_N from check}" "${EXPECT_SUM:?set EXPECT_SUM from check}"
  LIVE=$(code_live)
  [ "$LIVE" = yes ] || { echo "refused: code fix live: $LIVE" >&2; exit 1; }
  END="COMMIT"
fi
if [ -n "${EXPECT_N:-}${EXPECT_SUM:-}" ]; then
  [[ "${EXPECT_N:-}" =~ ^[0-9]+$ && "${EXPECT_SUM:-}" =~ ^-?[0-9]+(\.[0-9]+)?$ ]] || { echo "EXPECT_N / EXPECT_SUM must be numbers" >&2; exit 2; }
  EXPECT="DO \$\$ BEGIN
    IF (SELECT count(*) FROM $AUDIT) <> $EXPECT_N
       OR abs((SELECT COALESCE(sum(old_value), 0) FROM $AUDIT) - $EXPECT_SUM) > 0.05 THEN
      RAISE EXCEPTION 'rows moved since check: now % rows, sum %',
        (SELECT count(*) FROM $AUDIT), (SELECT round(sum(old_value)::numeric, 2) FROM $AUDIT);
    END IF; END \$\$;"
fi

DUMP="db_backups/lc_side_${STAMP}.dump"
ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_valuation_layer_landed_cost MOG_LIVE > ~/$DUMP && test -s ~/$DUMP && pg_restore -l ~/$DUMP | grep -c 'TABLE DATA' >/dev/null && echo \"backup ok: ~/$DUMP\""

ssh mog-prod "$REMOTE_ENV; $PSQL" <<SQL
BEGIN;
SET LOCAL lock_timeout = '15s';
LOCK TABLE stock_valuation_layer_landed_cost IN SHARE ROW EXCLUSIVE MODE;
CREATE TABLE $AUDIT AS WITH s AS ($SELECTION) SELECT * FROM s WHERE $FILTER;
$EXPECT
CREATE TEMP TABLE untouched ON COMMIT DROP AS
  SELECT count(*) AS n, COALESCE(sum(landed_cost_value), 0) AS total
    FROM stock_valuation_layer_landed_cost WHERE id NOT IN (SELECT id FROM $AUDIT);
DO \$\$ DECLARE changed bigint; BEGIN
  UPDATE stock_valuation_layer_landed_cost t
     SET landed_cost_value = 0, write_date = now() AT TIME ZONE 'utc'
    FROM $AUDIT a WHERE t.id = a.id;
  GET DIAGNOSTICS changed = ROW_COUNT;
  IF changed <> (SELECT count(*) FROM $AUDIT) THEN
    RAISE EXCEPTION 'updated % rows, selected another number', changed;
  END IF;
  IF EXISTS (SELECT 1 FROM stock_valuation_layer_landed_cost t JOIN $AUDIT a ON a.id = t.id
             WHERE t.landed_cost_value <> 0) THEN
    RAISE EXCEPTION 'selected rows still hold a value';
  END IF;
  IF (SELECT (u.n, u.total) IS DISTINCT FROM (count(*), COALESCE(sum(t.landed_cost_value), 0))
        FROM stock_valuation_layer_landed_cost t, untouched u
       WHERE t.id NOT IN (SELECT id FROM $AUDIT) GROUP BY u.n, u.total) THEN
    RAISE EXCEPTION 'rows outside the selection changed';
  END IF;
END \$\$;
\echo == result
SELECT count(*) AS rows_zeroed, round(sum(old_value)::numeric, 2) AS value_removed,
       count(DISTINCT default_code) AS products FROM $AUDIT;
SELECT round(sum(landed_cost_value)::numeric, 2) AS table_total_after,
       round(max(landed_cost_value)::numeric, 2) AS largest_after
  FROM stock_valuation_layer_landed_cost;
$END;
SQL
echo "$MODE done ($END). audit table: $AUDIT"
