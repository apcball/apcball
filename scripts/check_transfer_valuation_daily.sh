#!/usr/bin/env bash
# Daily read-only check of the valuation problems found in Nov 2026, MOG_LIVE (prod-native via ssh mog-prod).
#
# Usage:  bash scripts/check_transfer_valuation_daily.sh [DAYS]      (default DAYS=2: today and yesterday)
# Exit code: 0 = nothing to report, 1 = at least one alert (use it in cron / a notifier).
# Nothing is written (PGOPTIONS default_transaction_read_only=on).
#
# Checks over the moves/layers of the last DAYS days (accounting date, Bangkok day):
#   1. ONE-SIDED TRANSFER LEGS   inter-warehouse transfer where one leg is 0 and the other is not
#                                (re-transfer after a return consumed a layer whose origin is a negative layer;
#                                 PR #63 fixed the code, ~85 old layers still point at a negative layer).
#   2. UNEQUAL TRANSFER LEGS     in leg value != out leg value beyond max(0.05, 0.1%) (Sep-Oct 2026 problem:
#                                 in leg booked at the source's cost history / standard price).
#   3. RETURN LAYER, NEG ORIGIN  position layer created in the window AFTER PR #63 went live (FIX63_LIVE_AT) whose
#                                 origin_valuation_layer_id is a NEGATIVE layer (regression of PR #63).
#   4. STUCK VALUE (NEW)         warehouse/product with qty 0 and |value| >= 1 after the window whose value was
#                                 0 before the window (value left behind by something booked in the window, e.g. a
#                                 leg booked at 0). Older residues are not repeated every day.
# Legit zero-cost lots (both legs 0) are not reported. Thresholds: ALERT_MIN_ABS (default 1.00) is the smallest
# leg gap worth reporting in checks 1 and 2.
set -uo pipefail
DAYS="${1:-2}"
ALERT_MIN_ABS="${ALERT_MIN_ABS:-1.00}"
# PR #63 (return layers keep their real origin) went live on prod at this time; check 3 only counts later layers
FIX63_LIVE_AT="${FIX63_LIVE_AT:-2026-11-25 14:25:00+07}"
case "$DAYS" in ''|*[!0-9]*) echo "DAYS must be a number" >&2; exit 2;; esac
REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'

read -r -d '' TL <<'SQLEOF' || true
WITH win AS (
  SELECT ((date_trunc('day', now() AT TIME ZONE 'Asia/Bangkok') - (__DAYS__ - 1) * interval '1 day') AT TIME ZONE 'Asia/Bangkok') AS from_utc
),
tl AS (
  SELECT m.id mid, m.reference, m.picking_type_id pt, m.product_id, m.origin_returned_move_id IS NOT NULL is_return,
         ls.warehouse_id swh, ld.warehouse_id dwh, m.date::timestamp(0) d,
         max(l.id) FILTER (WHERE l.quantity > 0) in_id, max(l.id) FILTER (WHERE l.quantity < 0) out_id,
         coalesce(sum(l.value) FILTER (WHERE l.quantity > 0), 0) in_v, coalesce(-sum(l.value) FILTER (WHERE l.quantity < 0), 0) out_v,
         coalesce(sum(l.quantity) FILTER (WHERE l.quantity > 0), 0) in_q
  FROM stock_move m
  JOIN stock_location ls ON ls.id = m.location_id JOIN stock_location ld ON ld.id = m.location_dest_id
  JOIN stock_valuation_layer l ON l.stock_move_id = m.id AND l.quantity <> 0
  WHERE m.state = 'done' AND ls.usage IN ('internal', 'transit') AND ld.usage IN ('internal', 'transit')
    AND ls.warehouse_id IS DISTINCT FROM ld.warehouse_id
    AND m.date >= (SELECT from_utc FROM win)
  GROUP BY m.id, ls.warehouse_id, ld.warehouse_id
  HAVING count(*) FILTER (WHERE l.quantity > 0) > 0 AND count(*) FILTER (WHERE l.quantity < 0) > 0
)
SQLEOF
TL="${TL//__DAYS__/$DAYS}"
WIN="WITH win AS (SELECT ((date_trunc('day', now() AT TIME ZONE 'Asia/Bangkok') - ($DAYS - 1) * interval '1 day') AT TIME ZONE 'Asia/Bangkok') AS from_utc)"

OUT=$(ssh mog-prod "$REMOTE_ENV; PGOPTIONS='-c default_transaction_read_only=on' psql -h localhost -U odoo MOG_LIVE -q -v ON_ERROR_STOP=1" <<SQL
\\pset footer off
\\echo '##CHECK1 one-sided transfer legs'
$TL
SELECT t.d, t.reference, pp.default_code, t.in_q, round(t.out_v::numeric, 2) out_v, round(t.in_v::numeric, 2) in_v, round((t.in_v - t.out_v)::numeric, 2) gap
FROM tl t JOIN product_product pp ON pp.id = t.product_id
WHERE ((t.out_v = 0 AND t.in_v <> 0) OR (t.in_v = 0 AND t.out_v <> 0)) AND abs(t.in_v - t.out_v) >= $ALERT_MIN_ABS
ORDER BY abs(t.in_v - t.out_v) DESC LIMIT 30;
\\echo '##CHECK2 unequal transfer legs'
$TL
SELECT t.d, t.reference, pp.default_code, t.in_q, round(t.out_v::numeric, 2) out_v, round(t.in_v::numeric, 2) in_v, round((t.in_v - t.out_v)::numeric, 2) gap
FROM tl t JOIN product_product pp ON pp.id = t.product_id
WHERE t.out_v <> 0 AND t.in_v <> 0 AND abs(t.in_v - t.out_v) > greatest(0.05, 0.001 * t.out_v) AND abs(t.in_v - t.out_v) >= $ALERT_MIN_ABS
ORDER BY abs(t.in_v - t.out_v) DESC LIMIT 30;
\\echo '##CHECK3 return layer with a negative origin (created after PR #63 went live)'
$WIN
SELECT l.id, l.create_date::timestamp(0) created, pp.default_code, l.warehouse_id wh, l.quantity, round(l.value::numeric, 2) value, l.origin_valuation_layer_id origin_id
FROM stock_valuation_layer l JOIN stock_valuation_layer o ON o.id = l.origin_valuation_layer_id JOIN product_product pp ON pp.id = l.product_id
WHERE l.quantity > 0 AND o.quantity < 0 AND l.create_date >= (SELECT from_utc FROM win) AND l.create_date >= '$FIX63_LIVE_AT'::timestamptz
ORDER BY l.id DESC LIMIT 30;
\\echo '##CHECK4 NEW stuck value (qty 0, value left) from the window'
$WIN
, pairs AS (SELECT DISTINCT product_id, warehouse_id FROM stock_valuation_layer WHERE create_date >= (SELECT from_utc FROM win) AND warehouse_id IS NOT NULL),
sums AS (
  SELECT s.product_id, s.warehouse_id, sum(s.quantity) qty, sum(s.value) value,
         sum(s.value) FILTER (WHERE s.create_date >= (SELECT from_utc FROM win)) win_value
  FROM stock_valuation_layer s JOIN pairs p ON p.product_id = s.product_id AND p.warehouse_id = s.warehouse_id GROUP BY s.product_id, s.warehouse_id
)
SELECT pp.default_code, x.warehouse_id wh, round(x.qty::numeric, 4) qty, round(x.value::numeric, 2) value, round(coalesce(x.win_value, 0)::numeric, 2) from_window
FROM sums x JOIN product_product pp ON pp.id = x.product_id
WHERE abs(x.qty) < 0.0001 AND abs(x.value) >= 1 AND abs(x.value - coalesce(x.win_value, 0)) < 1
ORDER BY abs(x.value) DESC LIMIT 30;
\\echo '##END'
SQL
)
RC=$?
if [ $RC -ne 0 ]; then echo "check failed to run (ssh/psql exit $RC)" >&2; printf '%s\n' "$OUT" >&2; exit 2; fi

ALERTS=0
section() {  # name marker next-marker
  printf '%s\n' "$OUT" | awk -v a="##$1" -v b="##$2" 'index($0,a)==1{f=1;next} index($0,b)==1{f=0} f'
}
echo "== transfer valuation check, last $DAYS day(s) ($(date '+%Y-%m-%d %H:%M'))"
for pair in "CHECK1:CHECK2:1 one-sided transfer legs" "CHECK2:CHECK3:2 unequal transfer legs" "CHECK3:CHECK4:3 return layer with a negative origin" "CHECK4:END:4 stuck value (qty 0, value left)"; do
  cur=${pair%%:*}; rest=${pair#*:}; nxt=${rest%%:*}; title=${rest#*:}
  body=$(section "$cur" "$nxt")
  rows=$(printf '%s\n' "$body" | grep -cE '^ *[0-9A-Za-z(]' || true)
  # psql prints a header + separator, so data rows = lines - 2 when there is output
  n=$(printf '%s\n' "$body" | grep -c '|' || true)
  n=$(( n > 0 ? n - 1 : 0 ))
  if [ "$n" -gt 0 ]; then
    ALERTS=$((ALERTS + 1))
    echo; echo "!! [$title]: $n row(s)"; printf '%s\n' "$body" | sed '/^$/d'
  else
    echo "ok [$title]"
  fi
done
echo
if [ "$ALERTS" -gt 0 ]; then echo "RESULT: $ALERTS check(s) need attention"; exit 1; fi
echo "RESULT: all clear"
exit 0
