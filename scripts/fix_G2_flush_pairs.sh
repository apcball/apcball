#!/usr/bin/env bash
# Group G2 repair (7 products, accounting chose option A in groupG2.xlsx 2026-11-05) on MOG_LIVE.
# Not done (accounting said "ไม่ทำ"): 60101040145, ACS0021100, MF025R123, SP0025100, SWH006100.
#
# SVL ledger split between two warehouses left by the 2026-03-30 FIFO Reset Flush; the report window is wrong
# the same way as the all-time ledger, so every repair layer is dated INSIDE the window (2026-03-31 00:00, like
# the IMEX-REBASELINE layers) -> all-time == window == quant afterwards.
#
#   403030003  RM02 +12 / RM03 -12
#   FCA0003100 FG10 +3  / RM01 -3
#   FCA0006100, FCA0025100, FCA0045100, FCA0065100, FCA0248120   FG10 +1 / RM01 -1
#
# Option A = value-neutral: qty x average unit cost of the SOURCE warehouse (the side over quant), both sides same
# abs value, so each product's total value is unchanged. Plain SVL pair, no stock_move, remaining 0.
# Does not touch queue (remaining_*), quants, moves, journals.
#
# Modes: check (preconditions + proposed rows, rolls back) | dry (backup, insert + post-checks, ROLLBACK) | apply (COMMIT)
# Rollback after apply: DELETE FROM stock_valuation_layer WHERE description LIKE 'Reverse FIFO Reset Flush (G2 ledger fix%';
set -euo pipefail
MODE="${1:-check}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply" >&2; exit 2;; esac
REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'

BODY=$(cat <<'SQLEOF'
CREATE TEMP TABLE pr(code text, wh_inc text, wh_dec text, n numeric);
INSERT INTO pr VALUES ('403030003','RM02','RM03',12),('FCA0003100','FG10','RM01',3),('FCA0006100','FG10','RM01',1),
                      ('FCA0025100','FG10','RM01',1),('FCA0045100','FG10','RM01',1),('FCA0065100','FG10','RM01',1),('FCA0248120','FG10','RM01',1);
CREATE TEMP TABLE st AS
SELECT pr.*, p.id pid, wi.id wi_id, wd.id wd_id,
  (SELECT count(*) FROM product_product x WHERE x.default_code=pr.code) n_prod,
  -- guard sum = SVL excluding IMEX-REBASELINE-tagged layers
  (SELECT coalesce(sum(l.quantity),0) FROM stock_valuation_layer l LEFT JOIN stock_move sm ON sm.id=l.stock_move_id WHERE l.product_id=p.id AND l.warehouse_id=wi.id AND COALESCE(sm.reference,'') NOT LIKE 'IMEX-REBASELINE%') inc_svl,
  (SELECT coalesce(sum(l.quantity),0) FROM stock_valuation_layer l LEFT JOIN stock_move sm ON sm.id=l.stock_move_id WHERE l.product_id=p.id AND l.warehouse_id=wd.id AND COALESCE(sm.reference,'') NOT LIKE 'IMEX-REBASELINE%') dec_svl,
  (SELECT coalesce(sum(q.quantity),0) FROM stock_quant q JOIN stock_location sl ON sl.id=q.location_id WHERE q.product_id=p.id AND sl.warehouse_id=wi.id AND sl.usage IN ('internal','transit')) inc_quant,
  (SELECT coalesce(sum(q.quantity),0) FROM stock_quant q JOIN stock_location sl ON sl.id=q.location_id WHERE q.product_id=p.id AND sl.warehouse_id=wd.id AND sl.usage IN ('internal','transit')) dec_quant,
  (SELECT sum(l.quantity) FROM stock_valuation_layer l WHERE l.product_id=p.id AND l.warehouse_id=wd.id) dec_all_q,
  (SELECT sum(l.value) FROM stock_valuation_layer l WHERE l.product_id=p.id AND l.warehouse_id=wd.id) dec_all_v,
  (SELECT sum(l.quantity) FROM stock_valuation_layer l WHERE l.product_id=p.id AND l.warehouse_id=wi.id AND COALESCE(l.accounting_date,l.create_date)>='2026-03-30 17:00') inc_win_q,
  (SELECT sum(l.quantity) FROM stock_valuation_layer l WHERE l.product_id=p.id AND l.warehouse_id=wd.id AND COALESCE(l.accounting_date,l.create_date)>='2026-03-30 17:00') dec_win_q,
  (SELECT round(sum(l.value),2) FROM stock_valuation_layer l WHERE l.product_id=p.id) tot_v,
  (SELECT count(*) FROM stock_valuation_layer l WHERE l.product_id=p.id AND l.description LIKE 'Reverse FIFO Reset Flush (G2 ledger fix%') done
FROM pr JOIN product_product p ON p.default_code=pr.code
        JOIN stock_warehouse wi ON wi.code=pr.wh_inc JOIN stock_warehouse wd ON wd.code=pr.wh_dec;
ALTER TABLE st ADD COLUMN unit numeric, ADD COLUMN val numeric;
UPDATE st SET unit = dec_all_v/dec_all_q, val = round(n*dec_all_v/dec_all_q, 2);
\echo '== preconditions: inc_svl = inc_quant - n, dec_svl = dec_quant + n, windows == SVL (window is wrong the same way), not yet applied'
SELECT code, wh_inc, inc_svl, inc_quant, inc_win_q, wh_dec, dec_svl, dec_quant, dec_win_q, n, round(unit,4) unit, val, tot_v, done FROM st ORDER BY code;
DO $$
DECLARE bad int;
BEGIN
  IF (SELECT count(*) FROM st) <> 7 THEN RAISE EXCEPTION 'expected 7 products'; END IF;
  SELECT count(*) INTO bad FROM st WHERE n_prod<>1 OR inc_svl<>inc_quant-n OR dec_svl<>dec_quant+n
     OR inc_win_q<>inc_svl OR dec_win_q<>dec_svl OR done<>0 OR dec_all_q<=0 OR val<=0;
  IF bad<>0 THEN RAISE EXCEPTION 'precondition failed on % products', bad; END IF;
END $$;
SQLEOF
)

WRITE=$(cat <<'SQLEOF'
INSERT INTO stock_valuation_layer
  (company_id, product_id, description, quantity, unit_cost, value, remaining_qty, remaining_value,
   warehouse_id, current_warehouse_id, create_uid, write_uid, create_date, write_date, accounting_date)
SELECT 1, pid, 'Reverse FIFO Reset Flush (G2 ledger fix) - ' || code || ' WH ' || wh_inc, n, unit, val, 0, 0,
       wi_id, wi_id, 2, 2, TIMESTAMP '2026-03-31 00:00:00', now() AT TIME ZONE 'UTC', TIMESTAMP '2026-03-31 00:00:00' FROM st
UNION ALL
SELECT 1, pid, 'Reverse FIFO Reset Flush (G2 ledger fix) - ' || code || ' WH ' || wh_dec, -n, unit, -val, 0, 0,
       wd_id, wd_id, 2, 2, TIMESTAMP '2026-03-31 00:00:00', now() AT TIME ZONE 'UTC', TIMESTAMP '2026-03-31 00:00:00' FROM st;
CREATE TEMP TABLE po AS
SELECT st.code, w.code wh, w.id wid, st.pid, st.tot_v,
  (SELECT coalesce(sum(l.quantity),0) FROM stock_valuation_layer l LEFT JOIN stock_move sm ON sm.id=l.stock_move_id WHERE l.product_id=st.pid AND l.warehouse_id=w.id AND COALESCE(sm.reference,'') NOT LIKE 'IMEX-REBASELINE%') g_q,
  (SELECT sum(l.quantity) FROM stock_valuation_layer l WHERE l.product_id=st.pid AND l.warehouse_id=w.id AND COALESCE(l.accounting_date,l.create_date)>='2026-03-30 17:00') w_q,
  (SELECT coalesce(sum(q.quantity),0) FROM stock_quant q JOIN stock_location sl ON sl.id=q.location_id WHERE q.product_id=st.pid AND sl.warehouse_id=w.id AND sl.usage IN ('internal','transit')) quant,
  (SELECT round(sum(l.value),2) FROM stock_valuation_layer l WHERE l.product_id=st.pid) new_tot_v
FROM st JOIN stock_warehouse w ON w.id IN (st.wi_id, st.wd_id);
\echo '== post-check (after insert): all-time == window == quant on both warehouses, product total value unchanged'
SELECT * FROM po ORDER BY code, wh;
DO $$
DECLARE bad int;
BEGIN
  SELECT count(*) INTO bad FROM po WHERE g_q<>quant OR w_q<>quant OR new_tot_v<>tot_v;
  IF bad<>0 OR (SELECT count(*) FROM stock_valuation_layer WHERE description LIKE 'Reverse FIFO Reset Flush (G2 ledger fix%')<>14 THEN
    RAISE EXCEPTION 'post-check failed on % rows', bad;
  END IF;
  RAISE NOTICE 'post-check ok: 14 layers, all-time == window == quant, totals unchanged';
END $$;
SQLEOF
)

if [ "$MODE" = check ]; then
  { printf 'BEGIN;\n%s\nROLLBACK;\n' "$BODY"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q"
  exit 0
fi
COMMIT_OR_ROLLBACK=$([ "$MODE" = apply ] && echo COMMIT || echo ROLLBACK)
STAMP=$(date +%Y%m%d_%H%M%S)
echo ">>> backup stock_valuation_layer on mog-prod (~/db_backups/svl_G2_${STAMP}.dump)"
ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_valuation_layer MOG_LIVE -f ~/db_backups/svl_G2_${STAMP}.dump && ls -l ~/db_backups/svl_G2_${STAMP}.dump"
{ printf 'BEGIN;\n%s\n%s\n%s;\n' "$BODY" "$WRITE" "$COMMIT_OR_ROLLBACK"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q"
echo ">>> $MODE finished ($COMMIT_OR_ROLLBACK)"
