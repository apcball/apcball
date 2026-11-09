#!/usr/bin/env bash
# Restore the UNBUILD component moves whose done quantity was zeroed by the backdate / "modification of past move" damage
# (user 2026-11-09: "UB/00008 มีของเข้า stock" - the stock DID come in). For each done move with reference UB/%, since the cut-off, whose
# only move line has quantity 0 and whose SVL layers net to 0 (one or more original +q layers and "Correction of ..." layers = -q):
#   * move line quantity (and quantity_product_uom) := header qty q; stock_move.quantity := q
#   * delete the "Correction of ..." SVL layer(s) (the original +q layer stays; value restored)
#   * stock_quant at the destination location += q (record cloned from the same product's quant when none exists there)
# A correction layer that is referenced by stock_valuation_layer_usage (FIFO consumption links) is SKIPPED (needs a separate FIFO decision).
# Source must be a virtual location (Production); an internal source is SKIPPED. FIFO remaining_* of the restored layer is NOT touched
# (queue drift is a separate, known item). Each move runs in its own sub-transaction: SKIPPED with a reason when a check fails.
# Modes: check (plan, rolled back) | dry (backup, execute, report, ROLLBACK) | apply ALL (or apply UB/00008,UB/00009,...) -> COMMIT
# Reverse: restore stock_move / stock_move_line / stock_valuation_layer / stock_quant from the backup dump taken before apply.
set -euo pipefail
MODE="${1:-check}"; LIST="${2:-ALL}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply [ALL|UB/00008,...]" >&2; exit 2;; esac
[ "$MODE" = apply ] && [ -z "${2:-}" ] && { echo "apply needs ALL or an explicit reference list" >&2; exit 2; }
if ! [[ "$LIST" =~ ^[A-Za-z0-9,/._-]+$ ]]; then echo "bad list" >&2; exit 2; fi
REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'
BODY=$(cat <<'SQLEOF'
CREATE FUNCTION pg_temp.initial(p int, loc int) RETURNS numeric LANGUAGE sql AS $f$
 SELECT coalesce((SELECT sum(quantity) FROM stock_quant WHERE product_id=p AND location_id=loc),0) - coalesce((
  SELECT sum(CASE WHEN ldst=loc THEN q ELSE 0 END)-sum(CASE WHEN lsrc=loc THEN q ELSE 0 END) FROM (
   SELECT sml.location_id lsrc, sml.location_dest_id ldst, sml.quantity_product_uom q FROM stock_move m JOIN stock_move_line sml ON sml.move_id=m.id
     WHERE m.product_id=p AND m.state='done' AND m.date>='2026-03-30 17:00' AND sml.quantity<>0 AND loc IN (sml.location_id, sml.location_dest_id)
   UNION ALL
   SELECT m.location_id, m.location_dest_id, m.product_qty FROM stock_move m WHERE m.product_id=p AND m.state='done' AND m.date>='2026-03-30 17:00'
     AND loc IN (m.location_id, m.location_dest_id) AND NOT EXISTS (SELECT 1 FROM stock_move_line x WHERE x.move_id=m.id AND x.quantity<>0)) t),0) $f$;
CREATE TEMP TABLE res(ref text, move_id int, status text, reason text, product text, dest text, qty numeric, restored_value numeric, init_before numeric, init_after numeric);
CREATE TEMP TABLE sel AS SELECT m.id, m.reference, m.product_id pid, m.product_qty q, m.location_id lsrc, m.location_dest_id ldst
 FROM stock_move m WHERE m.state='done' AND m.date>='2026-03-30 17:00' AND m.reference LIKE 'UB/%' AND m.reference NOT LIKE 'IMEX-REBASELINE%'
  AND NOT EXISTS (SELECT 1 FROM stock_move_line x WHERE x.move_id=m.id AND x.quantity<>0)
  AND ('@@LIST@@'='ALL' OR m.reference = ANY(string_to_array('@@LIST@@',',')));
CREATE TEMP TABLE sums AS SELECT (SELECT round(sum(value)::numeric,2) FROM stock_valuation_layer WHERE product_id IN (SELECT pid FROM sel)) v_before,
  (SELECT count(*) FROM sel) n_sel;
\echo '== moves selected (expect 67 for ALL)'
SELECT count(*) selected, count(distinct pid) products FROM sel;
DO $$
DECLARE r record; ml record; nl int; sq numeric; negq numeric; negv numeric; posq numeric; nq int; qid int; dst_usage text; src_usage text; ib numeric; ia numeric; pcode text; dname text;
BEGIN
  FOR r IN SELECT * FROM sel ORDER BY id LOOP
    BEGIN
      SELECT default_code INTO pcode FROM product_product WHERE id=r.pid;
      SELECT complete_name, usage INTO dname, dst_usage FROM stock_location WHERE id=r.ldst;
      SELECT usage INTO src_usage FROM stock_location WHERE id=r.lsrc;
      IF dst_usage NOT IN ('internal','transit') THEN RAISE EXCEPTION 'destination % is not internal/transit', dname; END IF;
      IF src_usage IN ('internal','transit') THEN RAISE EXCEPTION 'source is an internal location'; END IF;
      SELECT count(*) INTO nl FROM stock_move_line WHERE move_id=r.id;
      IF nl<>1 THEN RAISE EXCEPTION 'move has % lines (need 1)', nl; END IF;
      SELECT * INTO ml FROM stock_move_line WHERE move_id=r.id;
      IF ml.quantity<>0 THEN RAISE EXCEPTION 'line quantity not 0'; END IF;
      SELECT coalesce(sum(quantity),0) INTO sq FROM stock_valuation_layer WHERE stock_move_id=r.id;
      SELECT coalesce(sum(quantity),0), coalesce(sum(value),0), count(*) INTO negq, negv, nq FROM stock_valuation_layer WHERE stock_move_id=r.id AND description LIKE 'Correction of%';
      SELECT coalesce(sum(quantity),0) INTO posq FROM stock_valuation_layer WHERE stock_move_id=r.id AND description NOT LIKE 'Correction of%';
      IF abs(sq)>0.0001 OR nq=0 OR abs(negq+r.q)>0.0001 OR abs(posq-r.q)>0.0001 THEN RAISE EXCEPTION 'SVL not original +% and correction -% (layers net %, correction %, other %)', r.q, r.q, sq, negq, posq; END IF;
      ib := pg_temp.initial(r.pid, r.ldst);
      -- quant
      SELECT id INTO qid FROM stock_quant WHERE product_id=r.pid AND location_id=r.ldst ORDER BY id LIMIT 1;
      IF qid IS NOT NULL THEN
        UPDATE stock_quant SET quantity=quantity+r.q, write_date=now() AT TIME ZONE 'UTC' WHERE id=qid;
      ELSE
        SELECT id INTO qid FROM stock_quant WHERE product_id=r.pid AND lot_id IS NULL ORDER BY id LIMIT 1;
        IF qid IS NULL THEN SELECT id INTO qid FROM stock_quant WHERE lot_id IS NULL AND package_id IS NULL AND owner_id IS NULL AND quantity>0 ORDER BY id LIMIT 1; END IF;
        IF qid IS NULL THEN RAISE EXCEPTION 'no quant record to clone'; END IF;
        DROP TABLE IF EXISTS qn; CREATE TEMP TABLE qn AS SELECT * FROM stock_quant WHERE id=qid;
        UPDATE qn SET id=nextval(pg_get_serial_sequence('stock_quant','id')), product_id=r.pid, location_id=r.ldst, quantity=r.q, reserved_quantity=0, lot_id=NULL, package_id=NULL, owner_id=NULL, in_date=now() AT TIME ZONE 'UTC', create_date=now() AT TIME ZONE 'UTC', write_date=now() AT TIME ZONE 'UTC';
        INSERT INTO stock_quant SELECT * FROM qn;
      END IF;
      UPDATE stock_move_line SET quantity=r.q, quantity_product_uom=r.q, write_date=now() AT TIME ZONE 'UTC' WHERE id=ml.id;
      UPDATE stock_move SET quantity=r.q, write_date=now() AT TIME ZONE 'UTC' WHERE id=r.id;
      DELETE FROM stock_valuation_layer WHERE stock_move_id=r.id AND description LIKE 'Correction of%';
      ia := pg_temp.initial(r.pid, r.ldst);
      INSERT INTO res VALUES (r.reference, r.id, 'OK', '', pcode, dname, r.q, -negv, ib, ia);
    EXCEPTION WHEN OTHERS THEN
      INSERT INTO res(ref, move_id, status, reason, qty) VALUES (r.reference, r.id, 'SKIPPED', SQLERRM, r.q);
    END;
  END LOOP;
END $$;
\echo '== summary'
SELECT status, count(*) moves, round(sum(qty),2) qty, round(coalesce(sum(restored_value),0),2) restored_value FROM res GROUP BY status ORDER BY status;
\echo '== SKIPPED (changed nothing)'
SELECT ref, move_id, reason FROM res WHERE status='SKIPPED' ORDER BY move_id;
\echo '== per product / destination after (Initial before -> after, rows still nonzero are other causes)'
SELECT product, dest, count(*) moves, round(sum(qty),2) restored_qty, round(sum(restored_value),2) restored_value, min(init_before) init_before_first, max(init_after) init_after_last FROM res WHERE status='OK' GROUP BY 1,2 ORDER BY 1,2;
DO $$ BEGIN
  IF (SELECT count(*) FROM stock_valuation_layer l WHERE l.stock_move_id IN (SELECT move_id FROM res WHERE status='OK') AND l.description LIKE 'Correction of%')<>0 THEN RAISE EXCEPTION 'correction layers still present'; END IF;
  IF (SELECT count(*) FROM stock_move_line ml JOIN stock_move m ON m.id=ml.move_id WHERE m.id IN (SELECT move_id FROM res WHERE status='OK') AND (ml.quantity<>m.product_qty OR m.quantity<>m.product_qty OR ml.quantity<>ml.quantity_product_uom))<>0 THEN RAISE EXCEPTION 'line/move quantity mismatch after restore'; END IF;
  IF (SELECT count(*) FROM stock_quant WHERE quantity<0 AND product_id IN (SELECT pid FROM sel) AND id IN (SELECT id FROM stock_quant WHERE write_date>=now()-interval '5 minutes'))>0 THEN RAISE NOTICE 'note: some touched quants are negative'; END IF;
END $$;
SQLEOF
)
BODY="${BODY//@@LIST@@/$LIST}"
if [ "$MODE" = check ]; then
  { printf 'BEGIN;\n%s\nROLLBACK;\n' "$BODY"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q"; echo "== check = plan executed inside a transaction and rolled back"; exit 0
fi
COMMIT_OR_ROLLBACK=$([ "$MODE" = apply ] && echo COMMIT || echo ROLLBACK)
STAMP=$(date +%Y%m%d_%H%M%S)
echo ">>> backup stock_move + stock_move_line + stock_valuation_layer + stock_quant on mog-prod (~/db_backups/ub_restore_${STAMP}.dump)"
ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_move -t stock_move_line -t stock_valuation_layer -t stock_quant MOG_LIVE -f ~/db_backups/ub_restore_${STAMP}.dump && ls -l ~/db_backups/ub_restore_${STAMP}.dump"
{ printf 'BEGIN;\n%s\n%s;\n' "$BODY" "$COMMIT_OR_ROLLBACK"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q"
echo ">>> $MODE finished ($COMMIT_OR_ROLLBACK)"
