#!/usr/bin/env bash
# 3ACA0041100 (product 4540) RM-NI <-> RM01 transfers on MOG_LIVE: SVL booked 904.089/unit although both moves carry
# custom_cost_price 109.96 (use_custom_cost = t): RM01260900141 (09-21, RM-NI->RM01) and its return RM01261000163 (10-24, RM01->RM-NI).
# Only 3 layers in the whole DB have unit_cost 904.089 (273642, 297460, 297461). Corrected to 109.96 x 10 = 1,099.60 each:
#   273642 RM-NI out  -9,040.89 -> -1,099.60     297460 RM-NI in  +9,040.89 -> +1,099.60     297461 RM01 out  -9,040.89 -> -1,099.60
# and the qty-0 revaluation layer 306441 (+7,901.06, applied earlier today as a stop-gap) is deleted.
# Result: RM-NI 10 / 2,177.75 (unchanged), RM01 0 qty / +40.23 (MOB261000218 in at 113.983 vs MOB out 109.96 - left as is),
#         product total 8,394.00 -> 8,434.23. Quants, queue (remaining_*, origin_remaining_*), moves untouched.
# Modes: check | dry (backup, apply + post-check, ROLLBACK) | apply (COMMIT)
# Rollback: UPDATE stock_valuation_layer SET value=-9040.89, unit_cost=904.0890 WHERE id IN (273642,297461);
#           UPDATE stock_valuation_layer SET value=9040.89, unit_cost=904.0890 WHERE id=297460; re-insert 306441 from the backup dump.
set -euo pipefail
MODE="${1:-check}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply" >&2; exit 2;; esac
REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'

BODY=$(cat <<'SQLEOF'
CREATE TEMP TABLE st AS SELECT
 (SELECT count(*) FROM stock_valuation_layer WHERE id=273642 AND product_id=4540 AND quantity=-10 AND value=-9040.89) a1,
 (SELECT count(*) FROM stock_valuation_layer WHERE id=297460 AND product_id=4540 AND quantity=10 AND value=9040.89) a2,
 (SELECT count(*) FROM stock_valuation_layer WHERE id=297461 AND product_id=4540 AND quantity=-10 AND value=-9040.89) a3,
 (SELECT count(*) FROM stock_valuation_layer WHERE id=306441 AND product_id=4540 AND quantity=0 AND value=7901.06) a4,
 (SELECT count(*) FROM stock_move WHERE id IN (340475,363657) AND custom_cost_price=109.96 AND use_custom_cost) a5,
 (SELECT count(*) FROM stock_valuation_layer WHERE round(unit_cost,3)=904.089) n_904,
 (SELECT round(sum(value),2) FROM stock_valuation_layer WHERE product_id=4540) tot_v;
\echo '== preconditions'
SELECT * FROM st;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM st WHERE a1=1 AND a2=1 AND a3=1 AND a4=1 AND a5=2 AND n_904=3 AND tot_v=8394.00) THEN RAISE EXCEPTION 'precondition failed'; END IF;
END $$;
SQLEOF
)

WRITE=$(cat <<'SQLEOF'
UPDATE stock_valuation_layer SET value=-1099.60, unit_cost=109.9600, write_date=now() AT TIME ZONE 'UTC' WHERE id IN (273642,297461);
UPDATE stock_valuation_layer SET value=1099.60, unit_cost=109.9600, write_date=now() AT TIME ZONE 'UTC' WHERE id=297460;
DELETE FROM stock_valuation_layer WHERE id=306441;
\echo '== post-check'
SELECT w.code wh, round(sum(l.quantity),2) q, round(sum(l.value),2) v,
  round(sum(l.value) FILTER (WHERE COALESCE(l.accounting_date,l.create_date)>='2026-03-30 17:00'),2) wv
FROM stock_valuation_layer l JOIN stock_warehouse w ON w.id=l.warehouse_id WHERE l.product_id=4540 GROUP BY 1 ORDER BY 1;
DO $$
DECLARE rmni numeric; rm01 numeric; tot numeric;
BEGIN
  SELECT round(sum(value),2) INTO rmni FROM stock_valuation_layer WHERE product_id=4540 AND warehouse_id=(SELECT id FROM stock_warehouse WHERE code='RM-NI');
  SELECT round(sum(value),2) INTO rm01 FROM stock_valuation_layer WHERE product_id=4540 AND warehouse_id=(SELECT id FROM stock_warehouse WHERE code='RM01');
  SELECT round(sum(value),2) INTO tot FROM stock_valuation_layer WHERE product_id=4540;
  IF rmni<>2177.75 OR rm01<>40.23 OR tot<>8434.23 OR (SELECT count(*) FROM stock_valuation_layer WHERE round(unit_cost,3)=904.089)<>0 THEN
    RAISE EXCEPTION 'post-check failed: RM-NI % RM01 % total %', rmni, rm01, tot;
  END IF;
  RAISE NOTICE 'post-check ok: RM-NI 2177.75, RM01 40.23, total 8434.23, no 904.089 layers left';
END $$;
SQLEOF
)

if [ "$MODE" = check ]; then
  { printf 'BEGIN;\n%s\nROLLBACK;\n' "$BODY"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q"
  exit 0
fi
COMMIT_OR_ROLLBACK=$([ "$MODE" = apply ] && echo COMMIT || echo ROLLBACK)
STAMP=$(date +%Y%m%d_%H%M%S)
echo ">>> backup stock_valuation_layer (~/db_backups/svl_3ACA_tc_${STAMP}.dump)"
ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_valuation_layer MOG_LIVE -f ~/db_backups/svl_3ACA_tc_${STAMP}.dump && ls -l ~/db_backups/svl_3ACA_tc_${STAMP}.dump"
{ printf 'BEGIN;\n%s\n%s\n%s;\n' "$BODY" "$WRITE" "$COMMIT_OR_ROLLBACK"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q"
echo ">>> $MODE finished ($COMMIT_OR_ROLLBACK)"
