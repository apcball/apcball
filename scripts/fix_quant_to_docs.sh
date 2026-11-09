#!/usr/bin/env bash
# Quant := DOCUMENTS (OB + done moves) for one-sided rows whose physical count matched the documents (user 2026-11-09:
# RM02_ST01_AS01_checklist_2026-11-09.xlsx, all 10 rows "นับตรงกับเอกสาร"; "ต้องลบ rebase line ออกด้วย ถึงจะตรง").
# Per (product, location): stock_quant at that location := quantity - Initial (record cloned when none exists); our correction layers at that
# warehouse are withdrawn ('Re-baseline adjustment ... group%', 'Reverse FIFO Reset Flush (%', 'Missing receipt SVL%' + the zero-qty groupF/D tag moves);
# PRE=qty adds ONE plain qty-only layer (value 0) dated 2026-03-30 16:59:59.999999 cancelling the pre-cut-off residue so SVL all-time == window == quant.
# SKIPPED (not failed) with a reason when: new quantity would be negative or below the reserved quantity, several quant records, SVL window != quant.
# Modes: check | dry | apply ALL|CODE,...   env PRE=skip|qty|add (default qty).  Same engine as fix_fg40_quant_to_docs.sh but a (code, location, warehouse) table.
set -euo pipefail
MODE="${1:-check}"; LIST="${2:-ALL}"; PRE="${PRE:-qty}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: [PRE=add|skip] $0 check|dry|apply [ALL|CODE,...]" >&2; exit 2;; esac
case "$PRE" in add|skip|qty) ;; *) echo "PRE must be add, qty or skip" >&2; exit 2;; esac
[ "$MODE" = apply ] && [ -z "${2:-}" ] && { echo "apply needs ALL or an explicit list" >&2; exit 2; }
if [[ "$LIST" == *[\;\'\"\\\ ]* || -z "$LIST" ]]; then echo "bad list" >&2; exit 2; fi
ALLC="ASS007,504110001,404030004,408010021,404020022,509030002,304010025,401020002,501190003,501190001"
[ "$LIST" = ALL ] && LIST="$ALLC"
REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'
BODY=$(cat <<'SQLEOF'
CREATE TEMP TABLE tgt(code text, loc int, wh int);
INSERT INTO tgt VALUES ('ASS007',20,2),('504110001',116,14),('404030004',116,14),('408010021',116,14),('404020022',116,14),('509030002',116,14),('304010025',116,14),('401020002',116,14),('501190003',156,19),('501190001',156,19),('201030398',108,13),('(ไม่ใช้)C2S0001HI020000',108,13),('504040003',108,13),('511010014',108,13);
CREATE FUNCTION pg_temp.initial(p int, loc int) RETURNS numeric LANGUAGE sql AS $f$
 SELECT coalesce((SELECT sum(quantity) FROM stock_quant WHERE product_id=p AND location_id=loc),0) - coalesce((
  SELECT sum(CASE WHEN ldst=loc THEN q ELSE 0 END)-sum(CASE WHEN lsrc=loc THEN q ELSE 0 END) FROM (
   SELECT sml.location_id lsrc, sml.location_dest_id ldst, sml.quantity_product_uom q FROM stock_move m JOIN stock_move_line sml ON sml.move_id=m.id
     WHERE m.product_id=p AND m.state='done' AND m.date>='2026-03-30 17:00' AND sml.quantity<>0 AND loc IN (sml.location_id, sml.location_dest_id)
   UNION ALL
   SELECT m.location_id, m.location_dest_id, m.product_qty FROM stock_move m WHERE m.product_id=p AND m.state='done' AND m.date>='2026-03-30 17:00'
     AND loc IN (m.location_id, m.location_dest_id) AND NOT EXISTS (SELECT 1 FROM stock_move_line x WHERE x.move_id=m.id AND x.quantity<>0)) t),0) $f$;
CREATE TEMP TABLE res(code text, status text, reason text, quant_before numeric, quant_after numeric, withdrawn_layers int, withdrawn_value numeric, pre_q numeric, pre_v numeric, svl_all_after numeric, svl_win_after numeric, value_change numeric);
DO $$
DECLARE c text; tl int; tw int; pid int; ini numeric; qb numeric; qa numeric; nl int; wv numeric; pq numeric; pv numeric; sa numeric; sw numeric; vb numeric; va numeric; qid int; resq numeric;
BEGIN
  FOR c, tl, tw IN SELECT t.code, t.loc, t.wh FROM tgt t WHERE t.code = ANY(string_to_array('@@LIST@@',',')) ORDER BY t.code LOOP
    BEGIN
      SELECT id INTO pid FROM product_product WHERE default_code=c;
      IF pid IS NULL THEN RAISE EXCEPTION 'product not found'; END IF;
      IF (SELECT count(*) FROM stock_quant WHERE product_id=pid AND location_id=tl)>1 THEN RAISE EXCEPTION 'several quant records'; END IF;
      SELECT id, quantity, reserved_quantity INTO qid, qb, resq FROM stock_quant WHERE product_id=pid AND location_id=tl ORDER BY id LIMIT 1;
      IF qid IS NULL THEN qb:=0; resq:=0; END IF;
      ini := pg_temp.initial(pid,tl);
      IF abs(ini)<0.0001 THEN RAISE EXCEPTION 'Initial already 0'; END IF;
      qa := qb - ini;
      IF qa < resq - 0.0001 OR qa < 0 THEN RAISE EXCEPTION 'new quantity % below reserved % or negative', qa, resq; END IF;
      SELECT round(sum(value)::numeric,2) INTO vb FROM stock_valuation_layer WHERE product_id=pid;
      IF qid IS NOT NULL THEN
        UPDATE stock_quant SET quantity=qa, write_date=now() AT TIME ZONE 'UTC' WHERE id=qid;
      ELSE
        SELECT id INTO qid FROM stock_quant WHERE product_id=pid AND lot_id IS NULL ORDER BY id LIMIT 1;
        IF qid IS NULL THEN SELECT id INTO qid FROM stock_quant WHERE lot_id IS NULL AND package_id IS NULL AND owner_id IS NULL AND quantity>0 ORDER BY id LIMIT 1; END IF;
        IF qid IS NULL THEN RAISE EXCEPTION 'no quant record to clone'; END IF;
        DROP TABLE IF EXISTS qn; CREATE TEMP TABLE qn AS SELECT * FROM stock_quant WHERE id=qid;
        UPDATE qn SET id=nextval(pg_get_serial_sequence('stock_quant','id')), product_id=pid, location_id=tl, quantity=qa, reserved_quantity=0, lot_id=NULL, package_id=NULL, owner_id=NULL, in_date=now() AT TIME ZONE 'UTC', create_date=now() AT TIME ZONE 'UTC', write_date=now() AT TIME ZONE 'UTC';
        INSERT INTO stock_quant SELECT * FROM qn;
      END IF;
      SELECT count(*), coalesce(round(sum(value)::numeric,2),0) INTO nl, wv FROM stock_valuation_layer WHERE product_id=pid AND warehouse_id=tw AND (description LIKE 'Re-baseline adjustment 2026-03-31 - group%' OR description LIKE 'Reverse FIFO Reset Flush (%' OR description LIKE 'Missing receipt SVL%');
      DELETE FROM stock_valuation_layer WHERE product_id=pid AND warehouse_id=tw AND (description LIKE 'Re-baseline adjustment 2026-03-31 - group%' OR description LIKE 'Reverse FIFO Reset Flush (%' OR description LIKE 'Missing receipt SVL%');
      DELETE FROM stock_move WHERE product_id=pid AND (name LIKE 'groupF re-baseline%' OR name LIKE 'groupD re-baseline%') AND NOT EXISTS (SELECT 1 FROM stock_valuation_layer l WHERE l.stock_move_id=stock_move.id);
      SELECT coalesce(sum(quantity),0), coalesce(round(sum(value)::numeric,2),0) INTO pq, pv FROM stock_valuation_layer WHERE product_id=pid AND warehouse_id=tw AND COALESCE(accounting_date,create_date)<'2026-03-30 17:00';
      IF '@@PRE@@' IN ('add','qty') AND abs(pq)>0.0001 THEN
        INSERT INTO stock_valuation_layer (company_id, product_id, description, quantity, unit_cost, value, remaining_qty, remaining_value, warehouse_id, current_warehouse_id, create_uid, write_uid, create_date, write_date, accounting_date)
        VALUES (1, pid, 'Reverse FIFO Reset Flush (pre-cutoff residue fix) - '||c||' WH '||(SELECT code FROM stock_warehouse WHERE id=tw), -pq, CASE WHEN '@@PRE@@'='qty' THEN 0 ELSE abs(pv/pq) END, CASE WHEN '@@PRE@@'='qty' THEN 0 ELSE -pv END, 0, 0, tw, tw, 2, 2, TIMESTAMP '2026-03-30 16:59:59.999999', now() AT TIME ZONE 'UTC', TIMESTAMP '2026-03-30 16:59:59.999999');
      END IF;
      IF abs(pg_temp.initial(pid,tl))>0.0001 THEN RAISE EXCEPTION 'Initial not zero after change'; END IF;
      SELECT coalesce(sum(quantity),0) INTO sa FROM stock_valuation_layer WHERE product_id=pid AND warehouse_id=tw;
      SELECT coalesce(sum(quantity),0) INTO sw FROM stock_valuation_layer WHERE product_id=pid AND warehouse_id=tw AND COALESCE(accounting_date,create_date)>='2026-03-30 17:00';
      IF abs(sw - (SELECT coalesce(sum(q.quantity),0) FROM stock_quant q JOIN stock_location l ON l.id=q.location_id WHERE q.product_id=pid AND l.warehouse_id=tw AND l.usage IN ('internal','transit')))>0.0001 THEN RAISE EXCEPTION 'SVL window % != quant at the warehouse', sw; END IF;
      SELECT round(sum(value)::numeric,2) INTO va FROM stock_valuation_layer WHERE product_id=pid;
      INSERT INTO res VALUES (c,'OK','',qb,qa,nl,wv,pq,pv,sa,sw,va-vb);
    EXCEPTION WHEN OTHERS THEN
      INSERT INTO res(code,status,reason) VALUES (c,'SKIPPED',SQLERRM);
    END;
  END LOOP;
END $$;
\echo '== result per product (SKIPPED rolled back individually)'
SELECT code, status, quant_before, quant_after, withdrawn_layers, withdrawn_value, pre_q, pre_v, svl_all_after, svl_win_after, value_change, reason FROM res ORDER BY status DESC, code;
SELECT count(*) FILTER (WHERE status='OK') ok, count(*) FILTER (WHERE status='SKIPPED') skipped, round(sum(value_change),2) total_value_change,
  round(sum(quant_after-quant_before),2) total_quant_change FROM res;
SQLEOF
)
BODY="${BODY//@@LIST@@/$LIST}"; BODY="${BODY//@@PRE@@/$PRE}"
if [ "$MODE" = check ]; then
  { printf 'BEGIN;\n%s\nROLLBACK;\n' "$BODY"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q"; echo "== check = plan executed inside a transaction and rolled back (PRE=$PRE)"; exit 0
fi
COMMIT_OR_ROLLBACK=$([ "$MODE" = apply ] && echo COMMIT || echo ROLLBACK)
STAMP=$(date +%Y%m%d_%H%M%S)
echo ">>> backup stock_quant + stock_valuation_layer + stock_move on mog-prod (~/db_backups/quant_docs_${STAMP}.dump)"
ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_quant -t stock_valuation_layer -t stock_move MOG_LIVE -f ~/db_backups/quant_docs_${STAMP}.dump && ls -l ~/db_backups/quant_docs_${STAMP}.dump"
{ printf 'BEGIN;\n%s\n%s;\n' "$BODY" "$COMMIT_OR_ROLLBACK"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q"
echo ">>> $MODE finished ($COMMIT_OR_ROLLBACK, PRE=$PRE)"
