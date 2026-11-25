#!/usr/bin/env bash
# 504110001 @RM02 on MOG_LIVE: buz_new_stock_card value ledger ends at 8,250 with qty 0.
# The card sums only SVL with stock_move_id AND location_id=RM02/Stock (opening: location_id + accounting_date; range: per move,
# direction by quantity sign). The move-less layers (305167 qty -50/value 0, 306414 qty 0/value -8,250) are invisible to it.
# Fix: attach the -50 layer to the stock-card correction move 375009 (location 116) and carry the -8,250 on it:
#   UPDATE 305167: stock_move_id=375009, location_id=116, value=-8250, unit_cost=165   ;  DELETE 306414 (value merged into 305167)
# Net SVL per warehouse unchanged (qty -50 / value -8,250 before and after), window unchanged, quants untouched.
# Modes: check | dry (backup, apply + post-check, ROLLBACK) | apply (COMMIT)
# Rollback: UPDATE stock_valuation_layer SET stock_move_id=NULL, location_id=NULL, value=0, unit_cost=0 WHERE id=305167;
#           then re-insert 306414 from the backup dump (qty 0, value -8250, wh 14, acct 2026-03-30 16:59:59.999999, product 11535).
set -euo pipefail
MODE="${1:-check}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply" >&2; exit 2;; esac
REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'

BODY=$(cat <<'SQLEOF'
CREATE TEMP TABLE st AS SELECT
 (SELECT count(*) FROM stock_valuation_layer WHERE id=305167 AND product_id=11535 AND quantity=-50 AND value=0 AND stock_move_id IS NULL AND location_id IS NULL) a_ok,
 (SELECT count(*) FROM stock_valuation_layer WHERE id=306414 AND product_id=11535 AND quantity=0 AND value=-8250 AND stock_move_id IS NULL) b_ok,
 (SELECT count(*) FROM stock_move WHERE id=375009 AND reference='STOCKCARD-FIX-504110001' AND state='done' AND product_id=11535) m_ok,
 (SELECT round(coalesce(sum(value),0),2) FROM stock_valuation_layer WHERE product_id=11535 AND location_id=116 AND stock_move_id IS NOT NULL) card_v,
 (SELECT round(sum(value),2) FROM stock_valuation_layer WHERE product_id=11535) svl_v,
 (SELECT sum(quantity) FROM stock_valuation_layer WHERE product_id=11535) svl_q,
 (SELECT round(sum(value),2) FROM stock_valuation_layer WHERE product_id=11535 AND COALESCE(accounting_date,create_date)>='2026-03-30 17:00') win_v;
\echo '== preconditions (card_v = what stock card shows as ending value)'
SELECT * FROM st;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM st WHERE a_ok=1 AND b_ok=1 AND m_ok=1 AND card_v=8250 AND svl_v=0 AND svl_q=0) THEN RAISE EXCEPTION 'precondition failed'; END IF;
END $$;
SQLEOF
)

WRITE=$(cat <<'SQLEOF'
UPDATE stock_valuation_layer SET stock_move_id=375009, location_id=116, value=-8250, unit_cost=165, write_date=now() AT TIME ZONE 'UTC' WHERE id=305167;
DELETE FROM stock_valuation_layer WHERE id=306414;
\echo '== post-check'
SELECT (SELECT round(coalesce(sum(value),0),2) FROM stock_valuation_layer WHERE product_id=11535 AND location_id=116 AND stock_move_id IS NOT NULL) card_v_after,
       (SELECT round(sum(value),2) FROM stock_valuation_layer WHERE product_id=11535) svl_v_after,
       (SELECT sum(quantity) FROM stock_valuation_layer WHERE product_id=11535) svl_q_after,
       (SELECT round(sum(value),2) FROM stock_valuation_layer WHERE product_id=11535 AND COALESCE(accounting_date,create_date)>='2026-03-30 17:00') win_v_after,
       (SELECT win_v FROM st) win_v_before;
DO $$ BEGIN
  IF (SELECT round(coalesce(sum(value),0),2) FROM stock_valuation_layer WHERE product_id=11535 AND location_id=116 AND stock_move_id IS NOT NULL)<>0
     OR (SELECT round(sum(value),2) FROM stock_valuation_layer WHERE product_id=11535)<>0
     OR (SELECT sum(quantity) FROM stock_valuation_layer WHERE product_id=11535)<>0
     OR (SELECT round(sum(value),2) FROM stock_valuation_layer WHERE product_id=11535 AND COALESCE(accounting_date,create_date)>='2026-03-30 17:00')<>(SELECT win_v FROM st) THEN
    RAISE EXCEPTION 'post-check failed';
  END IF;
  RAISE NOTICE 'post-check ok: card value 0, SVL 0/0, window value unchanged';
END $$;
SQLEOF
)

if [ "$MODE" = check ]; then
  { printf 'BEGIN;\n%s\nROLLBACK;\n' "$BODY"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q"
  exit 0
fi
COMMIT_OR_ROLLBACK=$([ "$MODE" = apply ] && echo COMMIT || echo ROLLBACK)
STAMP=$(date +%Y%m%d_%H%M%S)
echo ">>> backup stock_valuation_layer (~/db_backups/svl_scvalue504110001_${STAMP}.dump)"
ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_valuation_layer MOG_LIVE -f ~/db_backups/svl_scvalue504110001_${STAMP}.dump && ls -l ~/db_backups/svl_scvalue504110001_${STAMP}.dump"
{ printf 'BEGIN;\n%s\n%s\n%s;\n' "$BODY" "$WRITE" "$COMMIT_OR_ROLLBACK"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q"
echo ">>> $MODE finished ($COMMIT_OR_ROLLBACK)"
