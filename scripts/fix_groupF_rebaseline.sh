#!/usr/bin/env bash
# Group F re-baseline (accounting approved all 39 rows "ทำ", file groupF_for_accounting_2026-11-05.xlsx) on MOG_LIVE.
#
# Rows: scripts/data/groupF_rebaseline_2026-11-05.csv (override with CSV=path; row count and net value are read from the CSV; 2026-11-06 re-apply = 36 rows, MO 770 rows left out because the user fixed its date) (code, wh, quant, all-time/window qty+value, layer qty/value).
# State today for each row: all-time SVL == quant, report window (acct_date >= 2026-03-30 17:00 UTC) != quant.
# Per row adds, like MT00811210 (fix_MT00811210_rebaseline.sh) and the 10 IMEX-REBASELINE products:
#   * stock_move ref IMEX-REBASELINE-20260331, state done, NO move line (imex/stock card unaffected, quant untouched)
#   * SVL layer  qty = all-time - window, value = all-time value - window value, remaining 0,
#                accounting_date 2026-03-31 00:00 (inside window), tagged to that move so the
#                negative-balance guard (1b955289, live) skips it.
# Effect: report window == all-time value/qty == quant... the all-time ledger drifts by the layer (guard skips tagged).
# Net value of the 39 layers: -33,450.48. FIFO queue, quants, journal entries untouched.
# NEVER run stock_fifo_by_warehouse_recal on these product/warehouses (replay counts tagged layers as consumption).
#
# Modes: check (read-only live compare) | dry (backup, insert+post-checks, ROLLBACK) | apply (COMMIT only if all checks pass)
# Rollback after apply: DELETE FROM stock_valuation_layer WHERE description LIKE 'Re-baseline adjustment 2026-03-31 - groupF%';
#                       DELETE FROM stock_move WHERE name LIKE 'groupF re-baseline%';
set -euo pipefail
MODE="${1:-check}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply" >&2; exit 2;; esac
HERE="$(cd "$(dirname "$0")" && pwd)"
CSV="${CSV:-$HERE/data/groupF_rebaseline_2026-11-05.csv}"
N_ROWS=$(( $(wc -l < "$CSV") - 1 ))
NET_VAL=$(awk -F, 'NR>1{s+=$9} END{printf "%.2f", s}' "$CSV")
REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'

# temp table c from CSV + live state table s; mismatch view
SETUP=$(cat <<'SQLEOF'
CREATE TEMP TABLE c(code text, wh text, quant numeric, all_q numeric, win_q numeric, all_v numeric, win_v numeric, layer_q numeric, layer_v numeric);
\copy c FROM STDIN WITH (FORMAT csv, HEADER true)
SQLEOF
)
LIVE=$(cat <<'SQLEOF'
CREATE TEMP TABLE s AS
SELECT c.*, p.id pid, w.id wid,
  (SELECT count(*) FROM product_product pp WHERE pp.default_code=c.code) n_prod,
  (SELECT sum(l.quantity) FROM stock_valuation_layer l WHERE l.product_id=p.id AND l.warehouse_id=w.id) l_all_q,
  (SELECT round(sum(l.value),2) FROM stock_valuation_layer l WHERE l.product_id=p.id AND l.warehouse_id=w.id) l_all_v,
  (SELECT sum(l.quantity) FROM stock_valuation_layer l WHERE l.product_id=p.id AND l.warehouse_id=w.id AND COALESCE(l.accounting_date,l.create_date)>='2026-03-30 17:00') l_win_q,
  (SELECT round(sum(l.value),2) FROM stock_valuation_layer l WHERE l.product_id=p.id AND l.warehouse_id=w.id AND COALESCE(l.accounting_date,l.create_date)>='2026-03-30 17:00') l_win_v,
  (SELECT coalesce(sum(q.quantity),0) FROM stock_quant q JOIN stock_location sl ON sl.id=q.location_id WHERE q.product_id=p.id AND sl.warehouse_id=w.id AND sl.usage IN ('internal','transit')) l_quant,
  (SELECT count(*) FROM stock_valuation_layer l WHERE l.product_id=p.id AND l.warehouse_id=w.id AND l.description LIKE 'Re-baseline adjustment 2026-03-31 - groupF%') l_done
FROM c LEFT JOIN product_product p ON p.default_code=c.code LEFT JOIN stock_warehouse w ON w.code=c.wh;
\echo '== rows whose live state differs from the Excel snapshot (expect none)'
SELECT code, wh, n_prod, quant, l_quant, all_q, l_all_q, win_q, l_win_q, all_v, l_all_v, win_v, l_win_v, l_done
FROM s WHERE n_prod<>1 OR pid IS NULL OR wid IS NULL OR l_quant<>quant OR l_all_q<>all_q OR l_win_q<>win_q
  OR abs(l_all_v-all_v)>0.01 OR abs(l_win_v-win_v)>0.01 OR l_done<>0;
SELECT count(*) AS rows_total, count(*) FILTER (WHERE n_prod=1 AND pid IS NOT NULL AND wid IS NOT NULL AND l_quant=quant AND l_all_q=all_q AND l_win_q=win_q AND abs(l_all_v-all_v)<=0.01 AND abs(l_win_v-win_v)<=0.01 AND l_done=0) AS rows_ok, round(sum(layer_v),2) AS net_value FROM s;
SQLEOF
)

if [ "$MODE" = check ]; then
  # temp tables only (real tables never written); whole thing ends in ROLLBACK
  { printf 'BEGIN;\n%s\n' "$SETUP"; cat "$CSV"; printf '\\.\n%s\nROLLBACK;\n' "$LIVE"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -q"
  exit 0
fi

COMMIT_OR_ROLLBACK=$([ "$MODE" = apply ] && echo COMMIT || echo ROLLBACK)
STAMP=$(date +%Y%m%d_%H%M%S)
echo ">>> backup stock_valuation_layer + stock_move on mog-prod (~/db_backups/groupF_rebase_${STAMP}.dump)"
ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_valuation_layer -t stock_move MOG_LIVE -f ~/db_backups/groupF_rebase_${STAMP}.dump && ls -l ~/db_backups/groupF_rebase_${STAMP}.dump"

INSERTS=$(cat <<'SQLEOF'
DO $$
DECLARE bad int; r record; mid int; lid int; ucost numeric; stock_loc int; inv_loc int := 14;
BEGIN
  SELECT count(*) INTO bad FROM s WHERE n_prod<>1 OR pid IS NULL OR wid IS NULL OR l_quant<>quant OR l_all_q<>all_q OR l_win_q<>win_q
    OR abs(l_all_v-all_v)>0.01 OR abs(l_win_v-win_v)>0.01 OR l_done<>0;
  IF bad<>0 THEN RAISE EXCEPTION 'precondition failed: % rows differ from snapshot', bad; END IF;
  IF (SELECT count(*) FROM s) <> @@N@@ THEN RAISE EXCEPTION 'expected @@N@@ rows'; END IF;
  FOR r IN SELECT * FROM s ORDER BY code, wh LOOP
    SELECT lot_stock_id INTO stock_loc FROM stock_warehouse WHERE id=r.wid;
    ucost := abs(r.layer_v / r.layer_q);
    DROP TABLE IF EXISTS m; DROP TABLE IF EXISTS l;
    CREATE TEMP TABLE m AS SELECT * FROM stock_move WHERE id=332738;
    UPDATE m SET id = nextval(pg_get_serial_sequence('stock_move','id')), product_id = r.pid,
      name = 'groupF re-baseline adj (report only) ' || r.layer_q || ' @2026-03-31 ' || r.code || '/' || r.wh || '; one SVL; no move line',
      product_uom = (SELECT t.uom_id FROM product_product p JOIN product_template t ON t.id=p.product_tmpl_id WHERE p.id=r.pid),
      product_qty = abs(r.layer_q), product_uom_qty = abs(r.layer_q), quantity = abs(r.layer_q),
      weight = coalesce((SELECT weight FROM product_product WHERE id=r.pid),0) * abs(r.layer_q),
      location_id = CASE WHEN r.layer_q<0 THEN stock_loc ELSE inv_loc END,
      location_dest_id = CASE WHEN r.layer_q<0 THEN inv_loc ELSE stock_loc END,
      backdate_remark = 'groupF rebaseline 2026-11-05', create_date = now() AT TIME ZONE 'UTC', write_date = now() AT TIME ZONE 'UTC';
    INSERT INTO stock_move SELECT * FROM m;
    SELECT id INTO mid FROM m;
    CREATE TEMP TABLE l AS SELECT * FROM stock_valuation_layer WHERE id=265529;
    UPDATE l SET id = nextval(pg_get_serial_sequence('stock_valuation_layer','id')), product_id = r.pid,
      categ_id = (SELECT t.categ_id FROM product_product p JOIN product_template t ON t.id=p.product_tmpl_id WHERE p.id=r.pid),
      stock_move_id = mid, warehouse_id = r.wid, current_warehouse_id = r.wid,
      description = 'Re-baseline adjustment 2026-03-31 - groupF ' || r.code || ' @' || r.wh || ' pre-cutoff FIFO-reset residue ' || r.layer_q,
      quantity = r.layer_q, unit_cost = ucost, value = r.layer_v, remaining_qty = 0, remaining_value = 0,
      accounting_date = '2026-03-31 00:00:00', create_date = now() AT TIME ZONE 'UTC', write_date = now() AT TIME ZONE 'UTC';
    INSERT INTO stock_valuation_layer SELECT * FROM l;
    DROP TABLE m; DROP TABLE l;
  END LOOP;
END $$;
-- post-checks
CREATE TEMP TABLE s2 AS
SELECT s.code, s.wh, s.quant, s.all_q, s.all_v, s.layer_q, s.layer_v,
  (SELECT sum(l.quantity) FROM stock_valuation_layer l WHERE l.product_id=s.pid AND l.warehouse_id=s.wid) a_q,
  (SELECT round(sum(l.value),2) FROM stock_valuation_layer l WHERE l.product_id=s.pid AND l.warehouse_id=s.wid) a_v,
  (SELECT sum(l.quantity) FROM stock_valuation_layer l WHERE l.product_id=s.pid AND l.warehouse_id=s.wid AND COALESCE(l.accounting_date,l.create_date)>='2026-03-30 17:00') w_q,
  (SELECT round(sum(l.value),2) FROM stock_valuation_layer l WHERE l.product_id=s.pid AND l.warehouse_id=s.wid AND COALESCE(l.accounting_date,l.create_date)>='2026-03-30 17:00') w_v,
  (SELECT coalesce(sum(l.quantity),0) FROM stock_valuation_layer l LEFT JOIN stock_move sm ON sm.id=l.stock_move_id
     WHERE l.product_id=s.pid AND l.warehouse_id=s.wid AND COALESCE(sm.reference,'') NOT LIKE 'IMEX-REBASELINE%') g_q,
  (SELECT sum(l.remaining_qty) FROM stock_valuation_layer l WHERE l.product_id=s.pid AND l.warehouse_id=s.wid) queue_q,
  s.l_quant
FROM s;
\echo '== post-check rows that fail (expect none): window qty == quant, window value == old all-time value, guard sum == quant, all-time == old + layer'
SELECT * FROM s2 WHERE w_q<>l_quant OR abs(w_v-all_v)>0.01 OR g_q<>l_quant OR a_q<>all_q+layer_q OR abs(a_v-(all_v+layer_v))>0.01;
DO $$
DECLARE bad int; nl int; nm int; net numeric;
BEGIN
  SELECT count(*) INTO bad FROM s2 WHERE w_q<>l_quant OR abs(w_v-all_v)>0.01 OR g_q<>l_quant OR a_q<>all_q+layer_q OR abs(a_v-(all_v+layer_v))>0.01;
  SELECT count(*), round(sum(value),2) INTO nl, net FROM stock_valuation_layer WHERE description LIKE 'Re-baseline adjustment 2026-03-31 - groupF%';
  SELECT count(*) INTO nm FROM stock_move WHERE name LIKE 'groupF re-baseline%';
  IF bad<>0 OR nl<>@@N@@ OR nm<>@@N@@ OR net<>@@NET@@ THEN
    RAISE EXCEPTION 'post-check failed: bad rows %, layers %, moves %, net value %', bad, nl, nm, net;
  END IF;
  RAISE NOTICE 'post-check ok: @@N@@ layers, @@N@@ moves, net value %', net;
END $$;
SQLEOF
)

INSERTS="${INSERTS//@@N@@/$N_ROWS}"
INSERTS="${INSERTS//@@NET@@/$NET_VAL}"
{ printf 'BEGIN;\n%s\n' "$SETUP"; cat "$CSV"; printf '\\.\n%s\n%s\n%s;\n' "$LIVE" "$INSERTS" "$COMMIT_OR_ROLLBACK"; } \
  | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q"
echo ">>> $MODE finished ($COMMIT_OR_ROLLBACK)"
