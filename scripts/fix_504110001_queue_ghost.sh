#!/usr/bin/env bash
# 504110001 @RM02 on MOG_LIVE: FIFO queue ghost. Layer 282860 (RM02/2609082, +50 / 8,750, 2026-10-07) still has
# remaining_qty 50 / remaining_value 8,750 although quant = 0 and SVL qty = 0 (the 10-07 receipt was never consumed;
# outs drew from older layers). Next out/receipt would price from this phantom layer.
# Writes ONLY remaining_qty/remaining_value of that one layer -> 0. SVL quantity/value, quants, moves, journals untouched.
# NOT touched: origin_remaining_* (landed-cost bookkeeping, nonzero on 8 consumed layers of this product).
# Modes: check (rolls back) | dry (backup, update + post-check, ROLLBACK) | apply (COMMIT)
# Rollback after apply: UPDATE stock_valuation_layer SET remaining_qty=50, remaining_value=8750 WHERE id=282860;
set -euo pipefail
MODE="${1:-check}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply" >&2; exit 2;; esac
REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'

BODY=$(cat <<'SQLEOF'
CREATE TEMP TABLE st AS
SELECT l.id, l.remaining_qty, l.remaining_value, l.quantity, l.value, l.warehouse_id, l.product_id,
  (SELECT count(*) FROM stock_valuation_layer x WHERE x.product_id=l.product_id AND x.id<>l.id AND (coalesce(x.remaining_qty,0)<>0 OR coalesce(x.remaining_value,0)<>0)) other_rem,
  (SELECT coalesce(sum(x.quantity),0) FROM stock_valuation_layer x WHERE x.product_id=l.product_id AND x.warehouse_id=l.warehouse_id) wh_svl_q,
  (SELECT coalesce(sum(q.quantity),0) FROM stock_quant q JOIN stock_location sl ON sl.id=q.location_id WHERE q.product_id=l.product_id AND sl.warehouse_id=l.warehouse_id AND sl.usage IN ('internal','transit')) wh_quant,
  (SELECT round(sum(x.value),2) FROM stock_valuation_layer x WHERE x.product_id=l.product_id) tot_v
FROM stock_valuation_layer l WHERE l.id=282860 AND l.product_id=11535;
\echo '== preconditions'
SELECT * FROM st;
DO $$
BEGIN
  IF (SELECT count(*) FROM st)<>1 THEN RAISE EXCEPTION 'layer 282860 not found'; END IF;
  IF NOT EXISTS (SELECT 1 FROM st WHERE remaining_qty=50 AND remaining_value=8750 AND quantity=50 AND other_rem=0 AND wh_svl_q=0 AND wh_quant=0) THEN
    RAISE EXCEPTION 'precondition failed (layer not 50/8750, other remaining layers exist, or qty/quant not 0)';
  END IF;
END $$;
SQLEOF
)

WRITE=$(cat <<'SQLEOF'
UPDATE stock_valuation_layer SET remaining_qty=0, remaining_value=0, write_date=now() AT TIME ZONE 'UTC' WHERE id=282860 AND product_id=11535;
\echo '== post-check'
SELECT (SELECT coalesce(sum(remaining_qty),0) FROM stock_valuation_layer WHERE product_id=11535) rem_q_all,
       (SELECT coalesce(sum(remaining_value),0) FROM stock_valuation_layer WHERE product_id=11535) rem_v_all,
       (SELECT round(sum(value),2) FROM stock_valuation_layer WHERE product_id=11535) svl_v,
       (SELECT tot_v FROM st) svl_v_before;
DO $$
BEGIN
  IF (SELECT coalesce(sum(remaining_qty),0) FROM stock_valuation_layer WHERE product_id=11535)<>0
     OR (SELECT coalesce(sum(remaining_value),0) FROM stock_valuation_layer WHERE product_id=11535)<>0
     OR (SELECT round(sum(value),2) FROM stock_valuation_layer WHERE product_id=11535)<>(SELECT tot_v FROM st) THEN
    RAISE EXCEPTION 'post-check failed';
  END IF;
  RAISE NOTICE 'post-check ok: queue 0/0, SVL value unchanged';
END $$;
SQLEOF
)

if [ "$MODE" = check ]; then
  { printf 'BEGIN;\n%s\nROLLBACK;\n' "$BODY"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q"
  exit 0
fi
COMMIT_OR_ROLLBACK=$([ "$MODE" = apply ] && echo COMMIT || echo ROLLBACK)
STAMP=$(date +%Y%m%d_%H%M%S)
echo ">>> backup stock_valuation_layer (~/db_backups/svl_504110001q_${STAMP}.dump)"
ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_valuation_layer MOG_LIVE -f ~/db_backups/svl_504110001q_${STAMP}.dump && ls -l ~/db_backups/svl_504110001q_${STAMP}.dump"
{ printf 'BEGIN;\n%s\n%s\n%s;\n' "$BODY" "$WRITE" "$COMMIT_OR_ROLLBACK"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q"
echo ">>> $MODE finished ($COMMIT_OR_ROLLBACK)"
