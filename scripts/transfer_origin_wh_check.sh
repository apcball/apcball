#!/usr/bin/env bash
# READ-ONLY. Cross-warehouse FIFO consumption check from real data (no replay).
# A transfer's destination position layers point (origin_valuation_layer_id) at the layers
# the transfer consumed. If that origin layer sits in another warehouse than the transfer-out
# layer, the transfer was costed from a foreign queue.
# 'foreign' = origin layer is in another warehouse AND the transfer-out warehouse never received
# stock from that origin earlier (chained transfers into the source warehouse are legitimate).
# Moves that are returns (origin_returned_move_id set) are excluded: they are costed at the
# original transfer's price by design.
# Usage: scripts/transfer_origin_wh_check.sh <since> <until> [ssh-host]   (UTC, 'YYYY-MM-DD')
set -euo pipefail
SINCE="${1:?since}"; UNTIL="${2:?until}"; HOST="${3:-mog-prod}"
[[ "$SINCE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ && "$UNTIL" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || { echo "bad date"; exit 1; }
ssh "$HOST" "PGPASSWORD=\$(grep -E '^db_password' /etc/instance1.conf | cut -d= -f2 | tr -d ' ') PGOPTIONS='-c default_transaction_read_only=on' psql -h localhost -U odoo MOG_LIVE -P pager=off -v since='$SINCE' -v until='$UNTIL'" <<'SQL'
\set q 'WITH t AS (SELECT out.stock_move_id, out.warehouse_id AS out_wh, out.create_date AS ts, sm0.origin_returned_move_id AS ret, to_char(out.create_date,\'YYYY-MM\') AS month, pos.quantity AS qty, pos.value AS val, o.warehouse_id AS origin_wh, o.id AS origin_id FROM stock_valuation_layer out JOIN stock_move sm0 ON sm0.id = out.stock_move_id JOIN stock_valuation_layer pos ON pos.stock_move_id = out.stock_move_id AND pos.is_position_layer JOIN stock_valuation_layer o ON o.id = pos.origin_valuation_layer_id WHERE out.quantity < 0 AND NOT out.is_position_layer AND out.company_id = 1 AND out.create_date >= \'' :since '\' AND out.create_date < \'' :until '\')'
\echo == by month (cross = origin layer warehouse differs from transfer-out warehouse)
:q SELECT month, count(DISTINCT stock_move_id) moves, count(DISTINCT stock_move_id) FILTER (WHERE (ret IS NULL AND origin_wh IS DISTINCT FROM out_wh AND NOT EXISTS (SELECT 1 FROM stock_valuation_layer h WHERE h.warehouse_id = t.out_wh AND h.origin_valuation_layer_id = t.origin_id AND h.quantity > 0 AND h.create_date < t.ts))) cross_moves, round(sum(qty) FILTER (WHERE (ret IS NULL AND origin_wh IS DISTINCT FROM out_wh AND NOT EXISTS (SELECT 1 FROM stock_valuation_layer h WHERE h.warehouse_id = t.out_wh AND h.origin_valuation_layer_id = t.origin_id AND h.quantity > 0 AND h.create_date < t.ts)))) cross_qty, round(sum(val) FILTER (WHERE (ret IS NULL AND origin_wh IS DISTINCT FROM out_wh AND NOT EXISTS (SELECT 1 FROM stock_valuation_layer h WHERE h.warehouse_id = t.out_wh AND h.origin_valuation_layer_id = t.origin_id AND h.quantity > 0 AND h.create_date < t.ts)))) cross_val FROM t GROUP BY 1 ORDER BY 1;
\echo == cross moves (largest value first)
:q SELECT t.stock_move_id, sm.reference, t.ts::date d, t.out_wh, t.origin_wh, round(sum(t.qty),2) qty, round(sum(t.val)) val FROM t JOIN stock_move sm ON sm.id=t.stock_move_id WHERE (ret IS NULL AND origin_wh IS DISTINCT FROM out_wh AND NOT EXISTS (SELECT 1 FROM stock_valuation_layer h WHERE h.warehouse_id = t.out_wh AND h.origin_valuation_layer_id = t.origin_id AND h.quantity > 0 AND h.create_date < t.ts)) GROUP BY 1,2,3,4,5 ORDER BY abs(sum(t.val)) DESC LIMIT 25;
SQL
