#!/usr/bin/env bash
# DRAFT FOR ACCOUNTING REVIEW - 403030003 stock card OPENING VALUE at cutoff 2026-03-30 17:00 UTC.
# Qty opening is 0 at RM02/Stock, PD01/Stock, RM03/FXF (fixed 2026-11-17, moves 379159), imex initial value is 0, but the
# stock card sums SVL (location_id in scope, accounting_date < cutoff) = RM02 +18,404.40 / PD01 -17,825.00 / FXF -9,300.00.
# Cause: 03-30 reset layer RM02 -493 @539.99 vs FIFO in-layers @775/525.84; BLOJ003202 layer 84487 (-23/-17,825) booked at
# PD01 while its move line drains RM02; BROJ0006938/40 layers (-12 @775) booked at FXF one-sided.
# Proposal: ONE qty-0 value-only layer per location dated 2026-03-30 16:59:59.999999 (before the report window 17:00, so the
# FIFO/imex window and quants are untouched) bringing each location's opening value to 0.
#   RM02 -18,404.40 / PD01 +17,825.00 / FXF +9,300.00   => product SVL total value +8,720.60  (ACCOUNTING DECISION)
# Modes:  check = read-only preconditions + proposal;  dry = execute in a transaction then ROLLBACK;
#         apply = pg_dump backup then COMMIT (accounting signed off 2026-11-17).
# Rollback if ever applied: DELETE FROM stock_valuation_layer WHERE description LIKE 'STOCKCARD-OPENING-VALUE-FIX 403030003%';
set -euo pipefail
MODE="${1:-check}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply" >&2; exit 2;; esac
REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'
CHK=0; [ "$MODE" = check ] && CHK=1
APPLY=0; [ "$MODE" = apply ] && APPLY=1
if [ "$MODE" = apply ]; then
  TS=$(date +%Y%m%d_%H%M%S)
  ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_quant -t stock_valuation_layer -t stock_move -t stock_move_line MOG_LIVE -f ~/db_backups/stockcard_opening_value_403030003_$TS.dump && ls -l ~/db_backups/stockcard_opening_value_403030003_$TS.dump"
fi

ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -X -v ON_ERROR_STOP=1 -v check=$CHK -v apply=$APPLY -P pager=off" <<'SQL'
BEGIN;
CREATE TEMP TABLE pr AS SELECT p.id pid, pt.categ_id FROM product_product p JOIN product_template pt ON pt.id=p.product_tmpl_id WHERE p.default_code='403030003';
CREATE TEMP TABLE loc(id int, code text, whid int, expected numeric);
INSERT INTO loc SELECT l.id, l.complete_name, l.warehouse_id, e.v FROM stock_location l
  JOIN (VALUES ('RM02/Stock',18404.40),('PD01/Stock',-17825.00),('RM03/FXF',-9300.00)) e(n,v) ON e.n=l.complete_name WHERE l.usage='internal';

-- mirror of buz.stock.card.report._layer_scope_domain + _accounting_date_before_domain for a single-location scope
CREATE FUNCTION pg_temp.open_val(pid int, loc int) RETURNS numeric LANGUAGE sql AS $f$
  SELECT coalesce(round(sum(v.value)::numeric,2),0) FROM stock_valuation_layer v
  LEFT JOIN stock_move m ON m.id=v.stock_move_id LEFT JOIN stock_location dl ON dl.id=m.location_dest_id
  WHERE v.product_id=pid AND v.company_id=1 AND COALESCE(v.accounting_date,v.create_date) < '2026-03-30 17:00'
    AND ( (v.location_id=loc AND (v.quantity<=0 OR v.stock_move_id IS NULL OR m.location_dest_id=loc OR dl.usage NOT IN ('internal','transit')))
       OR (v.quantity>0 AND v.location_id IS DISTINCT FROM loc AND m.location_dest_id=loc AND m.location_id<>loc) );
$f$;

\echo '== current stock card opening value per location vs expected =='
SELECT l.code, l.whid, pg_temp.open_val((SELECT pid FROM pr), l.id) opening_value, l.expected FROM loc l ORDER BY l.code;

DO $$
DECLARE r record; bad int;
BEGIN
  IF (SELECT count(*) FROM loc)<>3 THEN RAISE EXCEPTION 'locations not found'; END IF;
  FOR r IN SELECT * FROM loc LOOP
    IF pg_temp.open_val((SELECT pid FROM pr), r.id) IS DISTINCT FROM r.expected THEN
      RAISE EXCEPTION 'opening value of % is %, expected % (data changed - re-review)', r.code, pg_temp.open_val((SELECT pid FROM pr), r.id), r.expected;
    END IF;
  END LOOP;
  IF EXISTS (SELECT 1 FROM stock_valuation_layer WHERE description LIKE 'STOCKCARD-OPENING-VALUE-FIX 403030003%') THEN RAISE EXCEPTION 'already applied'; END IF;
  -- qty ledger at cutoff must already be 0 at the three locations
  SELECT count(*) INTO bad FROM loc l WHERE abs(coalesce((SELECT sum(CASE WHEN ml.location_dest_id=l.id THEN ml.quantity ELSE -ml.quantity END) FROM stock_move_line ml
     WHERE ml.product_id=(SELECT pid FROM pr) AND ml.state='done' AND ml.date<='2026-03-30 17:00' AND (ml.location_id=l.id OR ml.location_dest_id=l.id) AND NOT (ml.location_id=l.id AND ml.location_dest_id=l.id)),0))>0.0001;
  IF bad<>0 THEN RAISE EXCEPTION 'qty opening not 0 at % locations', bad; END IF;
END $$;

\echo '== proposal: qty-0 value layer per location, dated 2026-03-30 16:59:59.999999 =='
SELECT l.code, l.whid warehouse_id, -l.expected AS layer_value FROM loc l ORDER BY l.code;
SELECT sum(-expected) AS product_svl_total_value_change FROM loc;

CREATE TEMP TABLE snap AS SELECT
  (SELECT round(sum(quantity),4) FROM stock_quant WHERE product_id=(SELECT pid FROM pr)) quant_q,
  (SELECT count(*) FROM stock_valuation_layer WHERE product_id<>(SELECT pid FROM pr)) other_svl,
  (SELECT round(sum(quantity),4) FROM stock_valuation_layer WHERE product_id=(SELECT pid FROM pr)) svl_q,
  (SELECT round(sum(value)::numeric,2) FROM stock_valuation_layer WHERE product_id=(SELECT pid FROM pr)) svl_v,
  (SELECT string_agg(warehouse_id||':'||q||':'||v, ',' ORDER BY warehouse_id) FROM (SELECT coalesce(warehouse_id,0) warehouse_id, round(sum(quantity),4) q, round(sum(value)::numeric,2) v
     FROM stock_valuation_layer WHERE product_id=(SELECT pid FROM pr) AND COALESCE(accounting_date,create_date)>='2026-03-30 17:00' GROUP BY 1) x) window_by_wh;

\if :check
\echo 'check ok (read-only, nothing inserted)'
ROLLBACK;
\q
\endif

DO $$
DECLARE r record; bad int; s record;
BEGIN
  FOR r IN SELECT * FROM loc LOOP
    INSERT INTO stock_valuation_layer (company_id, product_id, categ_id, description, quantity, unit_cost, value, remaining_qty, remaining_value,
      warehouse_id, current_warehouse_id, location_id, location_complete_name, location_type, locked, create_uid, write_uid, create_date, write_date, accounting_date)
    VALUES (1, (SELECT pid FROM pr), (SELECT categ_id FROM pr),
      'STOCKCARD-OPENING-VALUE-FIX 403030003 '||r.code||' (value-only, pre-cutoff)', 0, 0, -r.expected, 0, 0,
      r.whid, r.whid, r.id, r.code, 'internal', false, 2, 2, now() AT TIME ZONE 'UTC', now() AT TIME ZONE 'UTC', TIMESTAMP '2026-03-30 16:59:59.999999');
  END LOOP;
  SELECT count(*) INTO bad FROM loc l WHERE pg_temp.open_val((SELECT pid FROM pr), l.id)<>0;
  IF bad<>0 THEN RAISE EXCEPTION 'opening value not 0 at % locations after insert', bad; END IF;
  SELECT * INTO s FROM snap;
  IF s.quant_q IS DISTINCT FROM (SELECT round(sum(quantity),4) FROM stock_quant WHERE product_id=(SELECT pid FROM pr))
     OR s.other_svl<>(SELECT count(*) FROM stock_valuation_layer WHERE product_id<>(SELECT pid FROM pr))
     OR s.svl_q IS DISTINCT FROM (SELECT round(sum(quantity),4) FROM stock_valuation_layer WHERE product_id=(SELECT pid FROM pr))
     OR s.window_by_wh IS DISTINCT FROM (SELECT string_agg(warehouse_id||':'||q||':'||v, ',' ORDER BY warehouse_id) FROM (SELECT coalesce(warehouse_id,0) warehouse_id, round(sum(quantity),4) q, round(sum(value)::numeric,2) v
        FROM stock_valuation_layer WHERE product_id=(SELECT pid FROM pr) AND COALESCE(accounting_date,create_date)>='2026-03-30 17:00' GROUP BY 1) x)
  THEN RAISE EXCEPTION 'post-check failed: quant / SVL qty / window per warehouse changed'; END IF;
  RAISE NOTICE 'post-check ok: opening value 0 at 3 locations; quants, SVL qty, report-window layers unchanged; product SVL value % -> %', s.svl_v, (SELECT round(sum(value)::numeric,2) FROM stock_valuation_layer WHERE product_id=(SELECT pid FROM pr));
END $$;
\echo '== inserted layers =='
SELECT id, location_complete_name, warehouse_id, quantity, value, accounting_date FROM stock_valuation_layer WHERE description LIKE 'STOCKCARD-OPENING-VALUE-FIX 403030003%' ORDER BY id;
\if :apply
COMMIT;
\else
ROLLBACK;
\endif
SQL
