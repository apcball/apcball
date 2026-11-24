#!/usr/bin/env bash
# Quant-shift for MIRROR PAIRS (method piloted on FCA0003100, user 2026-11-09): the MOGEN_OB documents are correct, imex Initial plugs
# +n at location A / -n at location B are fixed by moving n of QUANT from A to B (total unchanged) and withdrawing OUR SVL correction
# layers of that product at the two warehouses (G1/G2/flush-pair 'Reverse FIFO Reset Flush (...)', 'Missing receipt SVL...',
# 'Re-baseline adjustment ... group F/D' and their zero-qty group moves), so SVL == quant == OB + moves.
# If after the withdrawal a PRE-cut-off residue remains per warehouse (group-F pairs: flush/reset layers do not net to 0) and it is an exact
# mirror between the two warehouses, a plain value-neutral pair dated 2026-03-30 16:59:59.999999 zeroes it, so pre-OB SVL == 0 per warehouse.
# Each product runs in its own sub-transaction; it is SKIPPED (not failed) with a reason when a precondition/post-check fails:
#   - exactly two locations with Initial != 0, equal and opposite;  - receiving/sending target quant must be >= 0;
#   - source available (quantity - reserved) >= n;  - one quant record per location;  - after the change SVL (all-time and window)
#   == quant at both warehouses;  - product SVL total value change <= 0.02;  - Initial 0 at both locations.
# Modes: check (plan only, rolls back) | dry (backup, execute, report, ROLLBACK) | apply CODE[,CODE...] (backup, execute those only, COMMIT).
# apply REQUIRES an explicit product list (only products whose status was OK in dry are changed).
# Reverse: restore the touched rows from the backup dump (stock_quant, stock_valuation_layer, stock_move).
set -euo pipefail
MODE="${1:-check}"; LIST="${2:-}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply [CODE,CODE...]" >&2; exit 2;; esac
[ "$MODE" = apply ] && [ -z "$LIST" ] && { echo "apply needs an explicit product list" >&2; exit 2; }
ALL="301010008,401020002,402010001,403030003,404030004,406010069,409110001,409250055,60101040145,60104010008,60104010010,FCA0006100,FCA0025100,FCA0045100,FCA0065100,FCA0248120,FU0033FC1560,MA0142101,MA332B1101,MO006901110,MU0002101,SPW031100"
[ -z "$LIST" ] && LIST="$ALL"
if ! [[ "$LIST" =~ ^[A-Za-z0-9,._+-]+$ ]]; then echo "bad list" >&2; exit 2; fi
REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'
BODY=$(cat <<'SQLEOF'
CREATE TABLE IF NOT EXISTS pg_temp.dummy(x int);
CREATE FUNCTION pg_temp.initial(p int, loc int) RETURNS numeric LANGUAGE sql AS $f$
 SELECT coalesce((SELECT sum(quantity) FROM stock_quant WHERE product_id=p AND location_id=loc),0) - coalesce((
  SELECT sum(CASE WHEN ldst=loc THEN q ELSE 0 END)-sum(CASE WHEN lsrc=loc THEN q ELSE 0 END) FROM (
   SELECT sml.location_id lsrc, sml.location_dest_id ldst, sml.quantity_product_uom q FROM stock_move m JOIN stock_move_line sml ON sml.move_id=m.id
     WHERE m.product_id=p AND m.state='done' AND m.date>='2026-03-30 17:00' AND sml.quantity<>0 AND loc IN (sml.location_id, sml.location_dest_id)
   UNION ALL
   SELECT m.location_id, m.location_dest_id, m.product_qty FROM stock_move m WHERE m.product_id=p AND m.state='done' AND m.date>='2026-03-30 17:00'
     AND loc IN (m.location_id, m.location_dest_id) AND NOT EXISTS (SELECT 1 FROM stock_move_line x WHERE x.move_id=m.id AND x.quantity<>0)) t),0) $f$;
CREATE TEMP TABLE res(code text, status text, reason text, loc_a text, loc_b text, n numeric, layers int, layer_value numeric, svl_a numeric, q_a numeric, svl_b numeric, q_b numeric);
CREATE TEMP TABLE todo AS SELECT code, row_number() OVER () rn FROM unnest(string_to_array('@@LIST@@',',')) code;
SQLEOF
)
RUN=$(cat <<'SQLEOF'
DO $$
DECLARE r record; pid int; a int; b int; n numeric; nloc int; wa int; wb int; qa record; qb record; nl int; lv numeric; vb numeric; va numeric; ini_a numeric; ini_b numeric;
        sa numeric; sb numeric; wsa numeric; wsb numeric; qta numeric; qtb numeric; la text; lb text; pa_q numeric; pa_v numeric; pb_q numeric; pb_v numeric;
BEGIN
  FOR r IN SELECT code FROM todo ORDER BY rn LOOP
    BEGIN
      SELECT id INTO pid FROM product_product WHERE default_code=r.code;
      IF pid IS NULL THEN RAISE EXCEPTION 'product not found'; END IF;
      SELECT count(*) INTO nloc FROM (SELECT DISTINCT lid FROM (
        SELECT location_id lid FROM stock_quant WHERE product_id=pid
        UNION SELECT location_id FROM stock_move_line WHERE product_id=pid AND state='done' AND date>='2026-03-30 17:00'
        UNION SELECT location_dest_id FROM stock_move_line WHERE product_id=pid AND state='done' AND date>='2026-03-30 17:00'
        UNION SELECT location_id FROM stock_move WHERE product_id=pid AND state='done' AND date>='2026-03-30 17:00'
        UNION SELECT location_dest_id FROM stock_move WHERE product_id=pid AND state='done' AND date>='2026-03-30 17:00') u
        JOIN stock_location sl ON sl.id=u.lid WHERE sl.usage IN ('internal','transit') AND abs(pg_temp.initial(pid,u.lid))>0.0001) z;
      IF nloc<>2 THEN RAISE EXCEPTION 'locations with Initial != 0: % (need exactly 2)', nloc; END IF;
      SELECT lid, pg_temp.initial(pid,lid) INTO a, n FROM (SELECT DISTINCT lid FROM (
        SELECT location_id lid FROM stock_quant WHERE product_id=pid UNION SELECT location_id FROM stock_move_line WHERE product_id=pid AND state='done' AND date>='2026-03-30 17:00'
        UNION SELECT location_dest_id FROM stock_move_line WHERE product_id=pid AND state='done' AND date>='2026-03-30 17:00'
        UNION SELECT location_id FROM stock_move WHERE product_id=pid AND state='done' AND date>='2026-03-30 17:00'
        UNION SELECT location_dest_id FROM stock_move WHERE product_id=pid AND state='done' AND date>='2026-03-30 17:00') u
        JOIN stock_location sl ON sl.id=u.lid WHERE sl.usage IN ('internal','transit')) x WHERE pg_temp.initial(pid,lid)>0.0001;
      SELECT lid INTO b FROM (SELECT DISTINCT lid FROM (
        SELECT location_id lid FROM stock_quant WHERE product_id=pid UNION SELECT location_id FROM stock_move_line WHERE product_id=pid AND state='done' AND date>='2026-03-30 17:00'
        UNION SELECT location_dest_id FROM stock_move_line WHERE product_id=pid AND state='done' AND date>='2026-03-30 17:00'
        UNION SELECT location_id FROM stock_move WHERE product_id=pid AND state='done' AND date>='2026-03-30 17:00'
        UNION SELECT location_dest_id FROM stock_move WHERE product_id=pid AND state='done' AND date>='2026-03-30 17:00') u
        JOIN stock_location sl ON sl.id=u.lid WHERE sl.usage IN ('internal','transit')) x WHERE pg_temp.initial(pid,lid)<-0.0001;
      IF a IS NULL OR b IS NULL THEN RAISE EXCEPTION 'need one + and one - location'; END IF;
      ini_a := pg_temp.initial(pid,a); ini_b := pg_temp.initial(pid,b);
      IF abs(ini_a+ini_b)>0.0001 THEN RAISE EXCEPTION 'not a mirror pair (% / %)', ini_a, ini_b; END IF;
      n := ini_a;
      SELECT complete_name, warehouse_id INTO la, wa FROM stock_location WHERE id=a;
      SELECT complete_name, warehouse_id INTO lb, wb FROM stock_location WHERE id=b;
      SELECT count(*) INTO nl FROM stock_quant WHERE product_id=pid AND location_id=a;
      IF nl>1 THEN RAISE EXCEPTION 'several quant records at source'; END IF;
      SELECT count(*) INTO nl FROM stock_quant WHERE product_id=pid AND location_id=b;
      IF nl>1 THEN RAISE EXCEPTION 'several quant records at target'; END IF;
      SELECT * INTO qa FROM stock_quant WHERE product_id=pid AND location_id=a;
      SELECT * INTO qb FROM stock_quant WHERE product_id=pid AND location_id=b;
      qta := coalesce(qa.quantity,0) - n; qtb := coalesce(qb.quantity,0) + n;
      IF qta < -0.0001 OR qtb < -0.0001 THEN RAISE EXCEPTION 'target quantity would be negative (source %, target %)', qta, qtb; END IF;
      IF coalesce(qa.quantity,0) - coalesce(qa.reserved_quantity,0) < n THEN RAISE EXCEPTION 'source reserved % of % (need % free)', qa.reserved_quantity, qa.quantity, n; END IF;
      SELECT round(sum(value)::numeric,2) INTO vb FROM stock_valuation_layer WHERE product_id=pid;
      -- quant shift
      UPDATE stock_quant SET quantity=quantity-n, write_date=now() AT TIME ZONE 'UTC' WHERE id=qa.id;
      IF qb.id IS NULL THEN
        CREATE TEMP TABLE IF NOT EXISTS qn AS SELECT * FROM stock_quant WHERE false;
        DELETE FROM qn; INSERT INTO qn SELECT * FROM stock_quant WHERE id=qa.id;
        UPDATE qn SET id=nextval(pg_get_serial_sequence('stock_quant','id')), location_id=b, quantity=n, reserved_quantity=0, create_date=now() AT TIME ZONE 'UTC', write_date=now() AT TIME ZONE 'UTC';
        INSERT INTO stock_quant SELECT * FROM qn;
      ELSE
        UPDATE stock_quant SET quantity=quantity+n, write_date=now() AT TIME ZONE 'UTC' WHERE id=qb.id;
      END IF;
      -- withdraw our correction layers at the two warehouses
      SELECT count(*), coalesce(round(sum(value)::numeric,2),0) INTO nl, lv FROM stock_valuation_layer
        WHERE product_id=pid AND warehouse_id IN (wa,wb) AND (description LIKE 'Reverse FIFO Reset Flush (%' OR description LIKE 'Missing receipt SVL%' OR description LIKE 'Re-baseline adjustment 2026-03-31 - group%');
      DELETE FROM stock_valuation_layer WHERE product_id=pid AND warehouse_id IN (wa,wb) AND (description LIKE 'Reverse FIFO Reset Flush (%' OR description LIKE 'Missing receipt SVL%' OR description LIKE 'Re-baseline adjustment 2026-03-31 - group%');
      DELETE FROM stock_move WHERE product_id=pid AND (name LIKE 'groupF re-baseline%' OR name LIKE 'groupD re-baseline%') AND NOT EXISTS (SELECT 1 FROM stock_valuation_layer l WHERE l.stock_move_id=stock_move.id);
      -- zero the PRE-cut-off residue per warehouse with a plain mirror pair dated just before the cut-off (like the flush layers)
      SELECT coalesce(sum(quantity),0), coalesce(sum(value),0) INTO pa_q, pa_v FROM stock_valuation_layer WHERE product_id=pid AND warehouse_id=wa AND COALESCE(accounting_date,create_date)<'2026-03-30 17:00';
      SELECT coalesce(sum(quantity),0), coalesce(sum(value),0) INTO pb_q, pb_v FROM stock_valuation_layer WHERE product_id=pid AND warehouse_id=wb AND COALESCE(accounting_date,create_date)<'2026-03-30 17:00';
      IF abs(pa_q)>0.0001 OR abs(pb_q)>0.0001 THEN
        IF wa=wb THEN RAISE EXCEPTION 'pre-cutoff residue in the same warehouse (% / %)', pa_q, pb_q; END IF;
        IF abs(pa_q+pb_q)>0.0001 OR abs(pa_v+pb_v)>0.02 THEN RAISE EXCEPTION 'pre-cutoff residue is not a mirror (qty % / %, value % / %)', pa_q, pb_q, pa_v, pb_v; END IF;
        INSERT INTO stock_valuation_layer (company_id, product_id, description, quantity, unit_cost, value, remaining_qty, remaining_value, warehouse_id, current_warehouse_id, create_uid, write_uid, create_date, write_date, accounting_date)
        VALUES (1, pid, 'Reverse FIFO Reset Flush (pre-cutoff residue fix) - '||r.code||' WH '||la, -pa_q, abs(CASE WHEN pa_q<>0 THEN pa_v/pa_q ELSE 0 END), -pa_v, 0, 0, wa, wa, 2, 2, TIMESTAMP '2026-03-30 16:59:59.999999', now() AT TIME ZONE 'UTC', TIMESTAMP '2026-03-30 16:59:59.999999'),
               (1, pid, 'Reverse FIFO Reset Flush (pre-cutoff residue fix) - '||r.code||' WH '||lb, -pb_q, abs(CASE WHEN pb_q<>0 THEN pb_v/pb_q ELSE 0 END), -pb_v, 0, 0, wb, wb, 2, 2, TIMESTAMP '2026-03-30 16:59:59.999999', now() AT TIME ZONE 'UTC', TIMESTAMP '2026-03-30 16:59:59.999999');
        nl := nl + 2;
      END IF;
      -- post-checks
      IF abs(pg_temp.initial(pid,a))>0.0001 OR abs(pg_temp.initial(pid,b))>0.0001 THEN RAISE EXCEPTION 'Initial not zero after change'; END IF;
      SELECT round(sum(value)::numeric,2) INTO va FROM stock_valuation_layer WHERE product_id=pid;
      IF abs(va-vb)>0.02 THEN RAISE EXCEPTION 'product SVL value changes by % (limit 0.02)', va-vb; END IF;
      SELECT coalesce(sum(quantity),0) INTO sa FROM stock_valuation_layer WHERE product_id=pid AND warehouse_id=wa;
      SELECT coalesce(sum(quantity),0) INTO wsa FROM stock_valuation_layer WHERE product_id=pid AND warehouse_id=wa AND COALESCE(accounting_date,create_date)>='2026-03-30 17:00';
      SELECT coalesce(sum(quantity),0) INTO qta FROM stock_quant q JOIN stock_location l ON l.id=q.location_id WHERE q.product_id=pid AND l.warehouse_id=wa AND l.usage IN ('internal','transit');
      IF wa<>wb THEN
        SELECT coalesce(sum(quantity),0) INTO sb FROM stock_valuation_layer WHERE product_id=pid AND warehouse_id=wb;
        SELECT coalesce(sum(quantity),0) INTO wsb FROM stock_valuation_layer WHERE product_id=pid AND warehouse_id=wb AND COALESCE(accounting_date,create_date)>='2026-03-30 17:00';
        SELECT coalesce(sum(quantity),0) INTO qtb FROM stock_quant q JOIN stock_location l ON l.id=q.location_id WHERE q.product_id=pid AND l.warehouse_id=wb AND l.usage IN ('internal','transit');
        IF abs(sa-qta)>0.0001 OR abs(wsa-qta)>0.0001 OR abs(sb-qtb)>0.0001 OR abs(wsb-qtb)>0.0001 THEN RAISE EXCEPTION 'SVL != quant after change: A svl % win % quant %, B svl % win % quant %', sa, wsa, qta, sb, wsb, qtb; END IF;
      ELSE
        sb:=sa; wsb:=wsa; qtb:=qta;
        IF abs(sa-qta)>0.0001 OR abs(wsa-qta)>0.0001 THEN RAISE EXCEPTION 'SVL != quant after change (same warehouse): svl % win % quant %', sa, wsa, qta; END IF;
      END IF;
      INSERT INTO res VALUES (r.code,'OK','',la,lb,n,nl,lv,sa,qta,sb,qtb);
    EXCEPTION WHEN OTHERS THEN
      INSERT INTO res(code,status,reason) VALUES (r.code,'SKIPPED',SQLERRM);
    END;
  END LOOP;
END $$;
\echo '== result per product (SKIPPED rows were rolled back individually and changed nothing)'
SELECT code, status, loc_a "from (Initial +)", loc_b "to (Initial -)", n, layers layers_withdrawn, layer_value, svl_a, q_a, svl_b, q_b, reason FROM res ORDER BY status DESC, code;
SQLEOF
)
BODY="${BODY//@@LIST@@/$LIST}"
if [ "$MODE" = check ]; then
  { printf 'BEGIN;\n%s\n%s\nROLLBACK;\n' "$BODY" "$RUN"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q"; echo "== check = full plan executed inside a transaction and rolled back"; exit 0
fi
COMMIT_OR_ROLLBACK=$([ "$MODE" = apply ] && echo COMMIT || echo ROLLBACK)
STAMP=$(date +%Y%m%d_%H%M%S)
echo ">>> backup stock_quant + stock_valuation_layer + stock_move on mog-prod (~/db_backups/quantshift_pairs_${STAMP}.dump)"
ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_quant -t stock_valuation_layer -t stock_move MOG_LIVE -f ~/db_backups/quantshift_pairs_${STAMP}.dump && ls -l ~/db_backups/quantshift_pairs_${STAMP}.dump"
{ printf 'BEGIN;\n%s\n%s\n%s;\n' "$BODY" "$RUN" "$COMMIT_OR_ROLLBACK"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q"
echo ">>> $MODE finished ($COMMIT_OR_ROLLBACK)"
