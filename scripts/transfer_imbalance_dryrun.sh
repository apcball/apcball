#!/usr/bin/env bash
# DRY RUN ONLY. Read-only report of inter-warehouse transfers whose valuation
# layers do not net to zero (value in != value out), with the correction a repair
# would book. Writes nothing to the database.
#
# Why: stock_by_locations books the destination layer of a transfer at the source
# location's cost history / standard price while the out layer carries the FIFO
# cost. Fixed going forward in stock_fifo_by_location 2071a593; this measures the
# damage already in MOG_LIVE.
#
# Usage: scripts/transfer_imbalance_dryrun.sh <since> <until> <outdir> [ssh-host]
#   since/until  'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS' (UTC, layer create_date)
#   outdir       where the CSV files are written (contains business data: keep it
#                out of git)
#   ssh-host     default mog-prod
#
# Output (outdir):
#   detail.csv                one row per destination position layer to correct
#   by_product_warehouse.csv  the same, summed per product x destination warehouse
#   summary.csv               headline numbers and sanity checks
#
# Method: for every transfer (move with a position layer created in the window) where
# quantity in == quantity out but value in != value out, the out value is spread over
# the destination layers by quantity (target_value). delta = target_value - value.
# delta_on_hand is the share sitting in stock still on hand (remaining_qty/qty), the
# rest left the destination layer already (sold, consumed or moved on).
set -euo pipefail

SINCE="${1:?usage: $0 <since> <until> <outdir> [ssh-host]}"
UNTIL="${2:?usage: $0 <since> <until> <outdir> [ssh-host]}"
OUTDIR="${3:?usage: $0 <since> <until> <outdir> [ssh-host]}"
HOST="${4:-mog-prod}"

TS_RE='^[0-9]{4}-[0-9]{2}-[0-9]{2}( [0-9]{2}:[0-9]{2}:[0-9]{2})?$'
[[ "$SINCE" =~ $TS_RE && "$UNTIL" =~ $TS_RE ]] || { echo "ERROR: since/until must look like 'YYYY-MM-DD[ HH:MM:SS]'" >&2; exit 1; }
mkdir -p "$OUTDIR"

read -r -d '' BASE <<'SQL' || true
WITH win AS (
  SELECT DISTINCT stock_move_id FROM stock_valuation_layer
  WHERE is_position_layer AND create_date >= '@SINCE@' AND create_date < '@UNTIL@'),
lay AS (
  SELECT l.* FROM stock_valuation_layer l JOIN win ON win.stock_move_id = l.stock_move_id
  WHERE l.stock_landed_cost_id IS NULL AND l.quantity <> 0),
tot AS (
  SELECT stock_move_id,
         sum(quantity) FILTER (WHERE quantity > 0)  AS in_q,
         sum(value)    FILTER (WHERE quantity > 0)  AS in_v,
         -sum(quantity) FILTER (WHERE quantity < 0) AS out_q,
         -sum(value)    FILTER (WHERE quantity < 0) AS out_v
  FROM lay GROUP BY 1),
imb AS (
  SELECT * FROM tot
  WHERE in_q > 0 AND out_q > 0 AND abs(in_q - out_q) < 0.0001 AND abs(in_v - out_v) > 0.01),
rws AS (
  SELECT l.id AS layer_id, l.stock_move_id, l.product_id, l.warehouse_id AS dest_wh,
         l.quantity AS qty, l.remaining_qty AS rem_qty, l.value, l.remaining_value,
         i.out_v * l.quantity / i.in_q AS target_value,
         i.out_v * l.quantity / i.in_q - l.value AS delta,
         LEAST(1, GREATEST(0, l.remaining_qty / l.quantity)) AS on_hand_frac,
         (SELECT n.warehouse_id FROM lay n WHERE n.stock_move_id = l.stock_move_id AND n.quantity < 0 LIMIT 1) AS src_wh
  FROM lay l JOIN imb i ON i.stock_move_id = l.stock_move_id
  WHERE l.quantity > 0),
enr AS (
  SELECT r.*, sm.reference, sm.date AS move_date, pp.default_code,
         ipc.value_text AS cost_method, ipv.value_text AS valuation,
         r.delta * r.on_hand_frac AS delta_on_hand,
         r.delta * (1 - r.on_hand_frac) AS delta_left,
         r.remaining_value + r.delta * r.on_hand_frac AS remaining_value_after,
         CASE WHEN r.value = 0 THEN NULL ELSE r.target_value / r.value END AS ratio,
         CASE WHEN r.value = 0 OR r.target_value / r.value > 3 OR r.target_value / r.value < 0.3333
                   OR abs(r.delta) > 20000 THEN 'REVIEW' ELSE '' END AS review_flag
  FROM rws r
  JOIN stock_move sm ON sm.id = r.stock_move_id
  JOIN product_product pp ON pp.id = r.product_id
  JOIN product_template pt ON pt.id = pp.product_tmpl_id
  LEFT JOIN ir_property ipc ON ipc.name = 'property_cost_method' AND ipc.res_id = 'product.category,' || pt.categ_id
  LEFT JOIN ir_property ipv ON ipv.name = 'property_valuation'   AND ipv.res_id = 'product.category,' || pt.categ_id)
SQL
BASE="${BASE//@SINCE@/$SINCE}"
BASE="${BASE//@UNTIL@/$UNTIL}"

Q_DETAIL="$BASE
SELECT e.reference, to_char(e.move_date, 'YYYY-MM-DD HH24:MI') AS move_date, e.layer_id, e.stock_move_id,
       e.product_id, e.default_code, e.src_wh AS source_wh_id, e.dest_wh AS dest_wh_id,
       (SELECT w.name FROM stock_warehouse w WHERE w.id = e.src_wh)  AS source_wh,
       (SELECT w.name FROM stock_warehouse w WHERE w.id = e.dest_wh) AS dest_wh,
       e.cost_method, e.valuation,
       round(e.qty::numeric, 4) AS qty, round(e.rem_qty::numeric, 4) AS rem_qty,
       round(e.value::numeric, 2) AS value, round(e.remaining_value::numeric, 2) AS remaining_value,
       round(e.target_value::numeric, 2) AS target_value, round(e.delta::numeric, 2) AS delta,
       round(e.delta_on_hand::numeric, 2) AS delta_on_hand, round(e.delta_left::numeric, 2) AS delta_left,
       round(e.remaining_value_after::numeric, 2) AS remaining_value_after,
       round(e.ratio::numeric, 3) AS target_over_value, e.review_flag
FROM enr e ORDER BY e.move_date, e.reference, e.layer_id"

Q_AGG="$BASE
SELECT e.product_id, e.default_code,
       (SELECT w.name FROM stock_warehouse w WHERE w.id = e.dest_wh) AS dest_wh, e.cost_method,
       count(DISTINCT e.stock_move_id) AS transfers, count(*) AS layers,
       round(sum(e.delta)::numeric, 2) AS delta, round(sum(e.delta_on_hand)::numeric, 2) AS delta_on_hand,
       round(sum(e.delta_left)::numeric, 2) AS delta_left,
       round(sum(e.rem_qty)::numeric, 4) AS rem_qty_total,
       count(*) FILTER (WHERE e.review_flag = 'REVIEW') AS layers_to_review
FROM enr e GROUP BY e.product_id, e.default_code, e.dest_wh, e.cost_method
ORDER BY abs(sum(e.delta)) DESC"

Q_SUM="$BASE
SELECT metric, value FROM (
  SELECT 1 AS ord, 'window_since_utc' AS metric, '$SINCE' AS value
  UNION ALL SELECT 2, 'window_until_utc', '$UNTIL'
  UNION ALL SELECT 3, 'transfers_in_window', count(*)::text FROM tot
  UNION ALL SELECT 4, 'transfers_value_imbalanced', count(*)::text FROM imb
  UNION ALL SELECT 5, 'transfers_qty_imbalanced_skipped', count(*)::text FROM tot WHERE in_q > 0 AND out_q > 0 AND abs(in_q - out_q) >= 0.0001
  UNION ALL SELECT 6, 'layers_to_correct', count(*)::text FROM enr
  UNION ALL SELECT 7, 'gap_total_thb (out - in)', round(coalesce(sum(out_v - in_v), 0)::numeric, 2)::text FROM imb
  UNION ALL SELECT 8, 'sum_delta_layers_thb', round(coalesce(sum(delta), 0)::numeric, 2)::text FROM enr
  UNION ALL SELECT 9, 'delta_on_hand_thb', round(coalesce(sum(delta_on_hand), 0)::numeric, 2)::text FROM enr
  UNION ALL SELECT 10, 'delta_already_left_thb', round(coalesce(sum(delta_left), 0)::numeric, 2)::text FROM enr
  UNION ALL SELECT 11, 'abs_gap_thb', round(coalesce(sum(abs(out_v - in_v)), 0)::numeric, 2)::text FROM imb
  UNION ALL SELECT 12, 'gap_in_gt_out_thb (in overvalued)', round(coalesce(sum(in_v - out_v) FILTER (WHERE in_v > out_v), 0)::numeric, 2)::text FROM imb
  UNION ALL SELECT 13, 'gap_out_gt_in_thb (in undervalued)', round(coalesce(sum(out_v - in_v) FILTER (WHERE out_v > in_v), 0)::numeric, 2)::text FROM imb
  UNION ALL SELECT 14, 'layers_non_fifo_category', count(*)::text FROM enr WHERE coalesce(cost_method, '') <> 'fifo'
  UNION ALL SELECT 15, 'delta_non_fifo_thb', round(coalesce(sum(delta) FILTER (WHERE coalesce(cost_method, '') <> 'fifo'), 0)::numeric, 2)::text FROM enr
  UNION ALL SELECT 16, 'layers_fully_on_hand', count(*)::text FROM enr WHERE on_hand_frac >= 0.999
  UNION ALL SELECT 17, 'layers_fully_gone', count(*)::text FROM enr WHERE on_hand_frac <= 0.001
  UNION ALL SELECT 18, 'layers_with_account_move', count(*)::text FROM stock_valuation_layer WHERE id IN (SELECT layer_id FROM enr) AND account_move_id IS NOT NULL
  UNION ALL SELECT 19, 'products', count(DISTINCT product_id)::text FROM enr
  UNION ALL SELECT 20, 'layers_flagged_review (ratio>3 or <0.33 or |delta|>20000)', count(*)::text FROM enr WHERE review_flag = 'REVIEW'
  UNION ALL SELECT 21, 'delta_flagged_review_thb', round(coalesce(sum(delta) FILTER (WHERE review_flag = 'REVIEW'), 0)::numeric, 2)::text FROM enr
  UNION ALL SELECT 22, 'delta_not_flagged_thb', round(coalesce(sum(delta) FILTER (WHERE review_flag = ''), 0)::numeric, 2)::text FROM enr
  UNION ALL SELECT 23, 'layers_remaining_value_inconsistent (|rem_val - rem_qty*value/qty|>0.5)', count(*)::text FROM enr WHERE abs(remaining_value - rem_qty * value / qty) > 0.5
) s ORDER BY ord"

run_remote() {  # $1 = output file, $2 = query
  ssh "$HOST" 'bash -s' > "$1" <<EOF
set -euo pipefail
PGPASS=\$(grep -E '^db_password' /etc/instance1.conf | cut -d= -f2 | tr -d ' ')
export PGPASSWORD="\$PGPASS"
export PGOPTIONS='-c default_transaction_read_only=on'   # belt and braces: nothing can write
psql -X -h localhost -U odoo MOG_LIVE --csv -v ON_ERROR_STOP=1 <<'SQLEOF'
$2
SQLEOF
EOF
}

echo ">>> DRY RUN (read-only) on $HOST, window [$SINCE, $UNTIL) UTC"
run_remote "$OUTDIR/summary.csv" "$Q_SUM"
run_remote "$OUTDIR/by_product_warehouse.csv" "$Q_AGG"
run_remote "$OUTDIR/detail.csv" "$Q_DETAIL"
echo ">>> summary:"
column -s, -t "$OUTDIR/summary.csv"
echo ">>> wrote $(($(wc -l < "$OUTDIR/detail.csv") - 1)) layer rows to $OUTDIR/detail.csv, $(($(wc -l < "$OUTDIR/by_product_warehouse.csv") - 1)) product x warehouse rows to $OUTDIR/by_product_warehouse.csv"
