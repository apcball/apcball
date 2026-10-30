#!/usr/bin/env bash
# Read-only scan of MOG_LIVE for two reservation defects:
#   1. stock.quant.reserved_quantity above the sum of open move lines (phantom reservation)
#   2. open pickings with a move stuck confirmed + picked=true and no move lines
#      (core _pre_action_done_hook sets picked, then an abandoned backorder wizard leaves it)
# Runs on the prod host, reads credentials from /etc/instance1.conf. Never writes.
#
# Manual run from a workstation:
#   ssh mog-prod 'bash -s' < scripts/reservation_scan.sh
# Cron on the prod host (daily 08:00 Thai = 01:00 UTC), output kept in a log:
#   0 1 * * * /opt/instance1/scripts/reservation_scan.sh >> /var/log/reservation_scan.log 2>&1
#
# Exit code: 0 clean, 1 findings, 2 error.
# Env: DB (default MOG_LIVE), LOOKBACK_DAYS (default 3, picked-move check only).
set -uo pipefail

DB="${DB:-MOG_LIVE}"
LOOKBACK_DAYS="${LOOKBACK_DAYS:-3}"
CONF=/etc/instance1.conf

PW=$(grep -E '^db_password' "$CONF" | cut -d= -f2 | tr -d ' ')
[ -n "$PW" ] || { echo "cannot read db_password from $CONF" >&2; exit 2; }
export PGPASSWORD="$PW" PGOPTIONS='-c default_transaction_read_only=on'

run() { psql -h localhost -U odoo "$DB" -X -q -v ON_ERROR_STOP=1 -v days="$LOOKBACK_DAYS" "$@"; }

echo "=== reservation scan $DB $(date -u '+%Y-%m-%d %H:%M:%S UTC') ==="

# 1. over-reserved quants (also lists under-reserved so a sign flip is visible)
OVER=$(run -At -F '|' <<'SQL'
WITH ml AS (
  SELECT product_id, location_id, lot_id, package_id, owner_id, SUM(quantity_product_uom) q
  FROM stock_move_line
  WHERE state NOT IN ('done','cancel','draft')
  GROUP BY 1,2,3,4,5
)
SELECT sq.id, pp.default_code, sl.complete_name, sq.quantity, sq.reserved_quantity,
       COALESCE(ml.q,0), sq.reserved_quantity - COALESCE(ml.q,0), sq.write_date::timestamp(0)
FROM stock_quant sq
JOIN product_product pp ON pp.id = sq.product_id
JOIN stock_location sl ON sl.id = sq.location_id AND sl.usage IN ('internal','transit')
LEFT JOIN ml ON ml.product_id = sq.product_id AND ml.location_id = sq.location_id
  AND ml.lot_id IS NOT DISTINCT FROM sq.lot_id
  AND ml.package_id IS NOT DISTINCT FROM sq.package_id
  AND ml.owner_id IS NOT DISTINCT FROM sq.owner_id
WHERE round(sq.reserved_quantity - COALESCE(ml.q,0), 3) <> 0
ORDER BY 7 DESC;
SQL
) || { echo "check 1 failed" >&2; exit 2; }

echo
echo "-- 1. quants where reserved_quantity != open move lines"
if [ -n "$OVER" ]; then
  echo "quant|product|location|onhand|reserved|real|excess|quant_write_date"
  echo "$OVER"
else
  echo "none"
fi

# 2. confirmed+picked moves without lines, only on open pickings touched recently
STUCK=$(run -At -F '|' <<'SQL'
SELECT sm.id, sp.name, pp.default_code, sm.state, sm.product_uom_qty, sm.write_date::timestamp(0),
       COALESCE(ru.login, sm.write_uid::text)
FROM stock_move sm
JOIN stock_picking sp ON sp.id = sm.picking_id AND sp.state NOT IN ('done','cancel','draft')
JOIN product_product pp ON pp.id = sm.product_id
LEFT JOIN res_users ru ON ru.id = sm.write_uid
WHERE sm.state IN ('confirmed','partially_available','waiting')
  AND sm.picked
  AND NOT EXISTS (SELECT 1 FROM stock_move_line l WHERE l.move_id = sm.id)
  AND sp.write_date > (now() at time zone 'utc') - (:days || ' days')::interval
ORDER BY sm.id;
SQL
) || { echo "check 2 failed" >&2; exit 2; }

echo
echo "-- 2. open-picking moves confirmed+picked with no move line (last ${LOOKBACK_DAYS}d)"
if [ -n "$STUCK" ]; then
  echo "move|picking|product|state|demand|write_date|last_writer"
  echo "$STUCK"
else
  echo "none"
fi

echo
if [ -n "$OVER" ] || [ -n "$STUCK" ]; then
  echo "RESULT: FINDINGS"
  exit 1
fi
echo "RESULT: CLEAN"
