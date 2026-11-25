#!/usr/bin/env bash
# 3ACA0041100 (product 4540) @RM01 on MOG_LIVE: qty 0 but SVL value -7,901.06 (all-time == window; FIFO report sees it).
# Cause: RM-NI<->RM01 transfers booked at 904.089/unit instead of ~110-114/unit:
#   09-21 RM-NI->RM01 10: RM-NI out -9,040.89 (layer 273642) but RM01 in +1,099.60 (273641)  -> 7,941.29 value lost in transit
#   10-24 RM01->RM-NI 10: both legs +/-9,040.89 (297460/297461), 10-27 MOB in +1,139.83 (297260) ; MOB out 09-21 -1,099.60 (273741)
#   RM01 net = 1,099.60 - 1,099.60 - 9,040.89 + 1,139.83 = -7,901.06 ; RM-NI = 2,177.75 (= receipt 1,099.60 + freight 1,078.15) is already right.
# Fix: ONE qty-0 revaluation layer at RM01 +7,901.06 dated inside the window (2026-10-27 14:30:00). History, quants, queue untouched.
# Limitation: buz_new_stock_card ignores qty-0 layers in range -> card value for RM01 still shows -7,901.06 (qty OK).
# Modes: check | dry (backup, insert + post-check, ROLLBACK) | apply (COMMIT)
# Rollback: DELETE FROM stock_valuation_layer WHERE description LIKE 'Revaluation (3ACA0041100 RM01%';
set -euo pipefail
MODE="${1:-check}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply" >&2; exit 2;; esac
REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'

BODY=$(cat <<'SQLEOF'
CREATE TEMP TABLE st AS SELECT p.id pid, w.id wid,
 (SELECT count(*) FROM product_product x WHERE x.default_code='3ACA0041100') n_prod,
 (SELECT coalesce(sum(quantity),0) FROM stock_valuation_layer l WHERE l.product_id=p.id AND l.warehouse_id=w.id) q,
 (SELECT round(coalesce(sum(value),0),2) FROM stock_valuation_layer l WHERE l.product_id=p.id AND l.warehouse_id=w.id) v,
 (SELECT round(coalesce(sum(value),0),2) FROM stock_valuation_layer l WHERE l.product_id=p.id AND l.warehouse_id=w.id AND COALESCE(l.accounting_date,l.create_date)>='2026-03-30 17:00') wv,
 (SELECT coalesce(sum(q.quantity),0) FROM stock_quant q JOIN stock_location sl ON sl.id=q.location_id WHERE q.product_id=p.id AND sl.warehouse_id=w.id AND sl.usage IN ('internal','transit')) quant,
 (SELECT round(sum(value),2) FROM stock_valuation_layer l WHERE l.product_id=p.id) tot_v,
 (SELECT count(*) FROM stock_valuation_layer l WHERE l.product_id=p.id AND l.description LIKE 'Revaluation (3ACA0041100 RM01%') done
FROM product_product p, stock_warehouse w WHERE p.default_code='3ACA0041100' AND w.code='RM01';
\echo '== preconditions'
SELECT * FROM st;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM st WHERE n_prod=1 AND q=0 AND v=-7901.06 AND wv=-7901.06 AND quant=0 AND done=0) THEN RAISE EXCEPTION 'precondition failed'; END IF;
END $$;
SQLEOF
)

WRITE=$(cat <<'SQLEOF'
INSERT INTO stock_valuation_layer
  (company_id, product_id, description, quantity, unit_cost, value, remaining_qty, remaining_value,
   warehouse_id, current_warehouse_id, location_id, create_uid, write_uid, create_date, write_date, accounting_date)
SELECT 1, pid, 'Revaluation (3ACA0041100 RM01 transfer cost 904.089/unit vs 110-114; restore -7,901.06)', 0, 0, 7901.06, 0, 0,
       wid, wid, 108, 2, 2, TIMESTAMP '2026-10-27 14:30:00', now() AT TIME ZONE 'UTC', TIMESTAMP '2026-10-27 14:30:00' FROM st;
\echo '== post-check'
SELECT w.code wh, round(sum(l.quantity),2) q, round(sum(l.value),2) v,
  round(sum(l.value) FILTER (WHERE COALESCE(l.accounting_date,l.create_date)>='2026-03-30 17:00'),2) wv
FROM stock_valuation_layer l JOIN stock_warehouse w ON w.id=l.warehouse_id WHERE l.product_id=(SELECT pid FROM st) GROUP BY 1 ORDER BY 1;
DO $$
DECLARE tv numeric;
BEGIN
  SELECT round(sum(value),2) INTO tv FROM stock_valuation_layer WHERE product_id=(SELECT pid FROM st);
  IF (SELECT round(sum(value),2) FROM stock_valuation_layer WHERE product_id=(SELECT pid FROM st) AND warehouse_id=(SELECT wid FROM st))<>0
     OR (SELECT round(sum(value),2) FROM stock_valuation_layer WHERE product_id=(SELECT pid FROM st) AND warehouse_id=(SELECT wid FROM st) AND COALESCE(accounting_date,create_date)>='2026-03-30 17:00')<>0
     OR (SELECT sum(quantity) FROM stock_valuation_layer WHERE product_id=(SELECT pid FROM st) AND warehouse_id=(SELECT wid FROM st))<>0
     OR tv <> (SELECT tot_v FROM st)+7901.06 THEN RAISE EXCEPTION 'post-check failed'; END IF;
  RAISE NOTICE 'post-check ok: RM01 0/0 all-time and window, product total value %', tv;
END $$;
SQLEOF
)

if [ "$MODE" = check ]; then
  { printf 'BEGIN;\n%s\nROLLBACK;\n' "$BODY"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q"
  exit 0
fi
COMMIT_OR_ROLLBACK=$([ "$MODE" = apply ] && echo COMMIT || echo ROLLBACK)
STAMP=$(date +%Y%m%d_%H%M%S)
echo ">>> backup stock_valuation_layer (~/db_backups/svl_3ACA_RM01_${STAMP}.dump)"
ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_valuation_layer MOG_LIVE -f ~/db_backups/svl_3ACA_RM01_${STAMP}.dump && ls -l ~/db_backups/svl_3ACA_RM01_${STAMP}.dump"
{ printf 'BEGIN;\n%s\n%s\n%s;\n' "$BODY" "$WRITE" "$COMMIT_OR_ROLLBACK"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q"
echo ">>> $MODE finished ($COMMIT_OR_ROLLBACK)"
