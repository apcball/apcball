#!/usr/bin/env bash
# Group B repair on MOG_LIVE (accounting marked all 7 rows "ทำ" in groupB_for_accounting_2026-11-11.xlsx).
# Qty-0 plain SVL layers (no stock_move, remaining 0) clearing value left stuck at qty 0 by the
# "pre-cutoff residue fix" layers (qty-only, value 0):
#   write-off : 504110001 RM02 (-8,250 pre + -500 window), 3AC0031100 FG50 -1,397.44, 3ACA0041100 FG50 -2,603.68
#   swap pairs: 201030398 RM01 -467.77 <-> 511010014 RM01 +467.77 ; (ไม่ใช้)C2S0001HI020000 RM01 -14 <-> 504040003 RM01 +14
# Pre-cutoff part dated 2026-03-30 16:59:59.999999 (invisible to the FIFO report, which sums acct_date >= 17:00 UTC);
# window part dated 2026-03-31 00:00 (window is wrong only for 504110001). Does not touch quants, moves, queue (remaining_*).
# NOT fixed here: 504110001 queue ghost (layer 282860 rem 50), 3ACA0041100 RM01 window -7,901.06, MO010S101 (on hold).
#
# Modes: check (preconditions, rolls back) | dry (backup, insert + post-checks, ROLLBACK) | apply (COMMIT)
# Rollback after apply: DELETE FROM stock_valuation_layer WHERE description LIKE 'Reverse FIFO Reset Flush (groupB ledger fix%';
set -euo pipefail
MODE="${1:-check}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply" >&2; exit 2;; esac
REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'

BODY=$(cat <<'SQLEOF'
CREATE TEMP TABLE pr(code text, wh text, exp_quant numeric, exp_pre_v numeric, exp_win_v numeric, d_pre numeric, d_win numeric);
INSERT INTO pr VALUES
 ('504110001','RM02',0,8250.00,500.00,-8250.00,-500.00),
 ('3AC0031100','FG50',0,1397.44,0,-1397.44,0),
 ('3ACA0041100','FG50',0,2603.68,0,-2603.68,0),
 ('201030398','RM01',0,467.77,0,-467.77,0),
 ('511010014','RM01',14,-467.77,467.77,467.77,0),
 ('(ไม่ใช้)C2S0001HI020000','RM01',0,14.00,0,-14.00,0),
 ('504040003','RM01',0.4,-14.00,14.00,14.00,0);
CREATE TEMP TABLE st AS
SELECT pr.*, p.id pid, w.id wid,
  (SELECT count(*) FROM product_product x WHERE x.default_code=pr.code) n_prod,
  (SELECT coalesce(sum(l.quantity),0) FROM stock_valuation_layer l WHERE l.product_id=p.id AND l.warehouse_id=w.id) all_q,
  (SELECT coalesce(round(sum(l.value),2),0) FROM stock_valuation_layer l WHERE l.product_id=p.id AND l.warehouse_id=w.id AND COALESCE(l.accounting_date,l.create_date)< '2026-03-30 17:00') pre_v,
  (SELECT coalesce(round(sum(l.value),2),0) FROM stock_valuation_layer l WHERE l.product_id=p.id AND l.warehouse_id=w.id AND COALESCE(l.accounting_date,l.create_date)>='2026-03-30 17:00') win_v,
  (SELECT coalesce(sum(q.quantity),0) FROM stock_quant q JOIN stock_location sl ON sl.id=q.location_id WHERE q.product_id=p.id AND sl.warehouse_id=w.id AND sl.usage IN ('internal','transit')) quant,
  (SELECT count(*) FROM stock_valuation_layer l WHERE l.product_id=p.id AND l.description LIKE 'Reverse FIFO Reset Flush (groupB ledger fix%') done
FROM pr JOIN product_product p ON p.default_code=pr.code JOIN stock_warehouse w ON w.code=pr.wh;
\echo '== preconditions: pre_v/win_v/quant equal expected, all_q == quant, not yet applied'
SELECT code, wh, all_q, quant, pre_v, win_v, d_pre, d_win, done FROM st ORDER BY code;
DO $$
DECLARE bad int;
BEGIN
  IF (SELECT count(*) FROM st) <> 7 THEN RAISE EXCEPTION 'expected 7 rows'; END IF;
  SELECT count(*) INTO bad FROM st WHERE n_prod<>1 OR pre_v<>exp_pre_v OR win_v<>exp_win_v OR quant<>exp_quant OR all_q<>quant OR done<>0;
  IF bad<>0 THEN RAISE EXCEPTION 'precondition failed on % rows', bad; END IF;
  IF (SELECT sum(d_pre+d_win) FROM st WHERE code IN ('201030398','511010014','(ไม่ใช้)C2S0001HI020000','504040003'))<>0 THEN RAISE EXCEPTION 'swap pairs not net zero'; END IF;
END $$;
SQLEOF
)

WRITE=$(cat <<'SQLEOF'
CREATE TEMP TABLE before AS SELECT product_id pid, round(sum(value),2) v FROM stock_valuation_layer WHERE product_id IN (SELECT pid FROM st) GROUP BY product_id;
INSERT INTO stock_valuation_layer
  (company_id, product_id, description, quantity, unit_cost, value, remaining_qty, remaining_value,
   warehouse_id, current_warehouse_id, create_uid, write_uid, create_date, write_date, accounting_date)
SELECT 1, pid, 'Reverse FIFO Reset Flush (groupB ledger fix) - ' || code || ' WH ' || wh, 0, 0, d_pre, 0, 0,
       wid, wid, 2, 2, TIMESTAMP '2026-03-30 16:59:59.999999', now() AT TIME ZONE 'UTC', TIMESTAMP '2026-03-30 16:59:59.999999'
FROM st WHERE d_pre<>0
UNION ALL
SELECT 1, pid, 'Reverse FIFO Reset Flush (groupB ledger fix, window) - ' || code || ' WH ' || wh, 0, 0, d_win, 0, 0,
       wid, wid, 2, 2, TIMESTAMP '2026-03-31 00:00:00', now() AT TIME ZONE 'UTC', TIMESTAMP '2026-03-31 00:00:00'
FROM st WHERE d_win<>0;
CREATE TEMP TABLE po AS
SELECT st.code, st.wh, st.exp_quant,
  (SELECT coalesce(sum(l.quantity),0) FROM stock_valuation_layer l WHERE l.product_id=st.pid AND l.warehouse_id=st.wid) all_q,
  (SELECT coalesce(round(sum(l.value),2),0) FROM stock_valuation_layer l WHERE l.product_id=st.pid AND l.warehouse_id=st.wid) all_v,
  (SELECT coalesce(round(sum(l.value),2),0) FROM stock_valuation_layer l WHERE l.product_id=st.pid AND l.warehouse_id=st.wid AND COALESCE(l.accounting_date,l.create_date)>='2026-03-30 17:00') w_v,
  (SELECT coalesce(sum(l.quantity),0) FROM stock_valuation_layer l WHERE l.product_id=st.pid AND l.warehouse_id=st.wid AND COALESCE(l.accounting_date,l.create_date)>='2026-03-30 17:00') w_q,
  st.win_v + st.d_win exp_w_v, st.pre_v + st.win_v + st.d_pre + st.d_win exp_all_v,
  (SELECT coalesce(sum(q.quantity),0) FROM stock_quant q JOIN stock_location sl ON sl.id=q.location_id WHERE q.product_id=st.pid AND sl.warehouse_id=st.wid AND sl.usage IN ('internal','transit')) quant
FROM st;
\echo '== post-check: all_q == window qty == quant, all_v and window value as planned, quants unchanged'
SELECT * FROM po ORDER BY code;
DO $$
DECLARE bad int; delta numeric;
BEGIN
  SELECT count(*) INTO bad FROM po WHERE all_q<>quant OR w_q<>quant OR quant<>exp_quant OR all_v<>exp_all_v OR w_v<>exp_w_v;
  SELECT coalesce(sum(a.v2 - b.v),0) INTO delta FROM before b JOIN (SELECT product_id pid, round(sum(value),2) v2 FROM stock_valuation_layer GROUP BY 1) a ON a.pid=b.pid;
  IF bad<>0 THEN RAISE EXCEPTION 'post-check failed on % rows', bad; END IF;
  IF delta <> -12751.12 THEN RAISE EXCEPTION 'net value change % <> -12751.12', delta; END IF;
  IF (SELECT count(*) FROM stock_valuation_layer WHERE description LIKE 'Reverse FIFO Reset Flush (groupB ledger fix%')<>8 THEN RAISE EXCEPTION 'expected 8 layers'; END IF;
  RAISE NOTICE 'post-check ok: 8 layers, net value change %', delta;
END $$;
SQLEOF
)

if [ "$MODE" = check ]; then
  { printf 'BEGIN;\n%s\nROLLBACK;\n' "$BODY"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q"
  exit 0
fi
COMMIT_OR_ROLLBACK=$([ "$MODE" = apply ] && echo COMMIT || echo ROLLBACK)
STAMP=$(date +%Y%m%d_%H%M%S)
echo ">>> backup stock_valuation_layer on mog-prod (~/db_backups/svl_groupB_${STAMP}.dump)"
ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_valuation_layer MOG_LIVE -f ~/db_backups/svl_groupB_${STAMP}.dump && ls -l ~/db_backups/svl_groupB_${STAMP}.dump"
{ printf 'BEGIN;\n%s\n%s\n%s;\n' "$BODY" "$WRITE" "$COMMIT_OR_ROLLBACK"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q"
echo ">>> $MODE finished ($COMMIT_OR_ROLLBACK)"
