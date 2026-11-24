#!/usr/bin/env bash
# Residual of LC 262 (BR26080052) on MAC0039C (product_id 15850, move 297506) on MOG_LIVE.
#
# Facts (read-only, 2026-11-24):
#   * adjustment line = 2,206.86; the over-booking (pre fdcdbf60) put 2,206.86 on BOTH position layers
#     262866 (FG30, parent 236981 consumed) and 262867 (RM-NI, parent 253081 holds the returned unit).
#     scripts/fix_lc_over_booked_svl_optionA.sh already halved 262867 -> 1,103.43; 1,103.43 is still over.
#   * the unit that carried the landed cost left FG30 for FG40 on 2026-09-15 (pair 268832 -5,653.84 /
#     268833 +5,653.84, 268833 still on hand at FG40). 5,653.84 = 1,240.12 + 2 x 2,206.86, i.e. the
#     duplicate landed cost travelled with the unit. Correct cost = 1,240.12 + 2,206.86 = 3,446.98.
#   * corroboration: FG30 ledger value 10,924.19 vs FG30 queue remaining_value 13,131.05 -> gap 2,206.86.
#
# Step 1 (total): 262867 value 1,103.43 -> 0 and its parent 253081 remaining_value 2,343.55 -> 1,240.12.
#         LC layers of MAC0039C then sum to 2,206.86 = adjustment line.
# Step 2 (warehouse split): transfer pair 268832 -5,653.84 -> -3,446.98 and 268833 +5,653.84 -> +3,446.98,
#         268833.remaining_value 5,653.84 -> 3,446.98. Net 0 across warehouses: FG40 -2,206.86, FG30 +2,206.86.
# Not touched: quantities, quants, moves, journal entries, origin_remaining_* (the engine reads the origin
#         layer 236971, already 3,446.98), layer 262866.
#
# Modes (first arg):
#   check   read-only: preconditions, proposed changes, per-warehouse picture. Writes nothing.
#   dry     backup, run the UPDATEs + post-checks in a transaction, ROLLBACK.
#   apply   backup, run the UPDATEs + post-checks, COMMIT only if all checks pass.
# Rollback after apply: restore old values from lc262_mac0039c_fix_20261124 (id, col, old_value, new_value).
set -euo pipefail
MODE="${1:-check}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply" >&2; exit 2;; esac

REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'

read -r -d '' PRE <<'SQLEOF' || true
\echo '== layers (expect 262867 v 1103.43 | 253081 rv 2343.55 | 268832 v -5653.84 | 268833 v 5653.84 rq 1 rv 5653.84)'
SELECT id, warehouse_id wh, quantity q, round(value,2) v, remaining_qty rq, round(remaining_value,2) rv, stock_landed_cost_id lc
FROM stock_valuation_layer WHERE id IN (262866, 262867, 253081, 268832, 268833, 236971) ORDER BY id;
\echo '== LC 262 layers of MAC0039C now vs adjustment line 2206.86'
SELECT round(sum(value),2) booked, (SELECT round(sum(additional_landed_cost),2) FROM stock_valuation_adjustment_lines WHERE cost_id=262 AND product_id=15850) adj
FROM stock_valuation_layer WHERE stock_landed_cost_id = 262 AND product_id = 15850;
\echo '== per warehouse MAC0039C: ledger value vs queue remaining_value vs quant (FG30 gap expected 2206.86)'
SELECT w.code, sum(l.quantity) svl_qty, round(sum(l.value),2) svl_val, round(sum(l.remaining_value),2) rem_val,
       (SELECT coalesce(sum(q.quantity),0) FROM stock_quant q JOIN stock_location sl ON sl.id=q.location_id
         WHERE q.product_id=15850 AND sl.warehouse_id=w.id AND sl.usage='internal') quant
FROM stock_valuation_layer l JOIN stock_warehouse w ON w.id=l.warehouse_id
WHERE l.product_id=15850 AND w.id IN (8,9,25) GROUP BY w.id, w.code ORDER BY w.id;
SQLEOF

if [ "$MODE" = check ]; then
  printf '%s\n' "$PRE" | ssh mog-prod "$REMOTE_ENV; PGOPTIONS='-c default_transaction_read_only=on' psql -h localhost -U odoo MOG_LIVE -q"
  cat <<'TXT'
== proposed (not written)
  262867 value        1103.43 -> 0.00        253081 remaining_value 2343.55 -> 1240.12
  268832 value       -5653.84 -> -3446.98    268833 value 5653.84 -> 3446.98, remaining_value 5653.84 -> 3446.98
  expected after: LC262 layers 2206.86 | FG30 ledger 10924.19 -> 13131.05 (= queue) | FG40 7548.25 -> 5341.39 | RM-NI 2343.55 -> 1240.12
TXT
  exit 0
fi

COMMIT_OR_ROLLBACK=$([ "$MODE" = apply ] && echo COMMIT || echo ROLLBACK)
STAMP=$(date +%Y%m%d_%H%M%S)
echo ">>> backup stock_valuation_layer on mog-prod (~/db_backups/svl_lc262_mac0039c_${STAMP}.dump)"
ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_valuation_layer MOG_LIVE -f ~/db_backups/svl_lc262_mac0039c_${STAMP}.dump && ls -l ~/db_backups/svl_lc262_mac0039c_${STAMP}.dump"

ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q" <<SQL
BEGIN;
$PRE
DO \$\$
DECLARE a numeric; b numeric; c numeric; d numeric; e numeric; f numeric; g numeric; qty8 numeric;
BEGIN
  SELECT value INTO a FROM stock_valuation_layer WHERE id = 262867;
  SELECT remaining_value INTO b FROM stock_valuation_layer WHERE id = 253081;
  SELECT value INTO c FROM stock_valuation_layer WHERE id = 268832;
  SELECT value, remaining_value INTO d, e FROM stock_valuation_layer WHERE id = 268833;
  IF round(a,2) <> 1103.43 OR round(b,2) <> 2343.55 OR round(c,2) <> -5653.84 OR round(d,2) <> 5653.84 OR round(e,2) <> 5653.84 THEN
    RAISE EXCEPTION 'abort: layer values changed (262867 %, 253081 rv %, 268832 %, 268833 % / rv %) - already fixed or moved', a, b, c, d, e;
  END IF;
  IF (SELECT remaining_qty FROM stock_valuation_layer WHERE id = 268833) <> 1 THEN
    RAISE EXCEPTION 'abort: layer 268833 no longer holds 1 unit';
  END IF;
  IF (SELECT remaining_qty FROM stock_valuation_layer WHERE id = 253081) <> 1 THEN
    RAISE EXCEPTION 'abort: layer 253081 no longer holds 1 unit';
  END IF;
END \$\$;
CREATE TABLE IF NOT EXISTS lc262_mac0039c_fix_20261124 (id int, col text, old_value numeric, new_value numeric);
INSERT INTO lc262_mac0039c_fix_20261124 VALUES
  (262867, 'value', 1103.43, 0.00),
  (253081, 'remaining_value', 2343.55, 1240.12),
  (268832, 'value', -5653.84, -3446.98),
  (268833, 'value', 5653.84, 3446.98),
  (268833, 'remaining_value', 5653.84, 3446.98);
UPDATE stock_valuation_layer SET value = 0.00 WHERE id = 262867;
UPDATE stock_valuation_layer SET remaining_value = 1240.12 WHERE id = 253081;
UPDATE stock_valuation_layer SET value = -3446.98 WHERE id = 268832;
UPDATE stock_valuation_layer SET value = 3446.98, remaining_value = 3446.98 WHERE id = 268833;
\echo '== after'
SELECT id, warehouse_id wh, round(value,2) v, remaining_qty rq, round(remaining_value,2) rv FROM stock_valuation_layer WHERE id IN (262866, 262867, 253081, 268832, 268833) ORDER BY id;
\echo '== post-check: LC262 MAC0039C booked equals adjustment (expect 2206.86 / 2206.86)'
SELECT round(sum(value),2) booked, (SELECT round(sum(additional_landed_cost),2) FROM stock_valuation_adjustment_lines WHERE cost_id=262 AND product_id=15850) adj
FROM stock_valuation_layer WHERE stock_landed_cost_id = 262 AND product_id = 15850;
\echo '== post-check: FG30 ledger == queue (expect gap 0.00), FG40 and RM-NI value == remaining'
SELECT w.code, round(sum(l.value),2) svl_val, round(sum(l.remaining_value),2) rem_val, round(sum(l.remaining_value) - sum(l.value),2) gap
FROM stock_valuation_layer l JOIN stock_warehouse w ON w.id=l.warehouse_id WHERE l.product_id=15850 AND w.id IN (8,9,25) GROUP BY w.id, w.code ORDER BY w.id;
DO \$\$
BEGIN
  IF (SELECT round(sum(remaining_value) - sum(value), 2) FROM stock_valuation_layer WHERE product_id = 15850 AND warehouse_id = 8) <> 0 THEN
    RAISE EXCEPTION 'abort: FG30 ledger still differs from its queue';
  END IF;
  IF (SELECT round(sum(value),2) FROM stock_valuation_layer WHERE stock_landed_cost_id = 262 AND product_id = 15850) <> 2206.86 THEN
    RAISE EXCEPTION 'abort: LC 262 MAC0039C layers do not equal the adjustment line';
  END IF;
END \$\$;
$COMMIT_OR_ROLLBACK;
SQL
echo ">>> $MODE finished ($COMMIT_OR_ROLLBACK)"
