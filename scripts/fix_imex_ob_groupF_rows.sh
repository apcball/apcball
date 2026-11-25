#!/usr/bin/env bash
# OBSOLETE (2026-11-09): user confirmed the MOGEN_OB amounts are CORRECT; Initial plugs must NOT be fixed by editing/adding OB lines or rows before the OB.
# The OB edits applied on 2026-11-05 were reverted on 2026-11-09. DO NOT RUN. Kept only for history.
# imex Initial of the group-F one-sided / cross-code rows (user rule 2026-11-05/06: opening = MOGEN_OB only, Initial 0).
# imex Initial (true report logic: stock_move legs, header fallback when a move has no move line) = quant - net moves since cut-off.
# For each row below it edits the MOGEN_OB reseed (picking partner 'MOGEN_OB', 2026-03-31 00:50-01:00) at that location:
#   delta > 0 : +delta on the largest existing OB move/line there, or a NEW OB move+line cloned from a MOGEN_OB picking of that
#               location (when the product has none);
#   delta < 0 : -|delta| on the largest OB move/line there (it must be >= |delta|).
# Only stock_move / stock_move_line change; quants, SVL, queue untouched.
# NOT included (not fixable at OB): ASS007 AS01 +15 (the AS01 warehouse has NO MOGEN_OB reseed picking at all), 404020022 RM02 -11, 504040003 RM01 -0.4, 511010014 RM01 -14, ESA0004110 FG50 -1, LTL12010 FG10 -1,
#   MT24NTC101 FG40 -4 (OB smaller than the excess / none), MU0002101 FG30 +1 / FG40 -1 (needs count).
# Modes: check | dry (backup, change, post-checks, ROLLBACK) | apply (COMMIT). Optional 2nd arg: comma list of codes.
# Reverse after apply: new rows carry stock_move.backdate_remark='OB groupF rows 2026-11-09' (DELETE their lines+moves); edited rows:
#   the script prints the reverse UPDATE statements (save them).
set -euo pipefail
MODE="${1:-check}"; ONLY="${2:-}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply [codes]" >&2; exit 2;; esac
if [ -n "$ONLY" ] && ! [[ "$ONLY" =~ ^[^\'\;]+$ ]]; then echo "bad list" >&2; exit 2; fi
FILTER=""; [ -n "$ONLY" ] && FILTER="DELETE FROM rr WHERE code <> ALL(string_to_array('$ONLY',','));"
REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'
BODY=$(cat <<'SQLEOF'
CREATE TEMP TABLE rr(code text, lid int, delta numeric);
INSERT INTO rr VALUES
 ('(ไม่ใช้)C2S0001HI020000',108,0.4),('201030398',108,14),('3AC0031100',84,1),('3ACA0041100',84,2),('504110001',116,50),('MT019E101',76,2),
 ('501190001',156,20),('501190003',156,20),
 ('408010021',116,-20),('MO010S101',8,-1),('MO0026101',76,-3),('MO005N101.',76,-3),('MT0014101',76,-2),('MT0020101',76,-1),('MT0021101',76,-5),('MT024NB+101',76,-2);
@@FILTER@@
CREATE FUNCTION pg_temp.initial(p int, loc int) RETURNS numeric LANGUAGE sql AS $f$
 SELECT coalesce((SELECT sum(quantity) FROM stock_quant WHERE product_id=p AND location_id=loc),0) - coalesce((
  SELECT sum(CASE WHEN ldst=loc THEN q ELSE 0 END)-sum(CASE WHEN lsrc=loc THEN q ELSE 0 END) FROM (
   SELECT sml.location_id lsrc, sml.location_dest_id ldst, sml.quantity_product_uom q FROM stock_move m JOIN stock_move_line sml ON sml.move_id=m.id
     WHERE m.product_id=p AND m.state='done' AND m.date>='2026-03-30 17:00' AND sml.quantity<>0 AND loc IN (sml.location_id, sml.location_dest_id)
   UNION ALL
   SELECT m.location_id, m.location_dest_id, m.product_qty FROM stock_move m WHERE m.product_id=p AND m.state='done' AND m.date>='2026-03-30 17:00'
     AND loc IN (m.location_id, m.location_dest_id) AND NOT EXISTS (SELECT 1 FROM stock_move_line x WHERE x.move_id=m.id AND x.quantity<>0)) t),0) $f$;
CREATE TEMP TABLE obl AS
SELECT ml.id mlid, ml.move_id, ml.product_id pid, ml.location_dest_id lid, ml.quantity q, ml.picking_id
FROM stock_move_line ml JOIN stock_picking pk ON pk.id=ml.picking_id JOIN res_partner pt ON pt.id=pk.partner_id
WHERE ml.state='done' AND ml.date>='2026-03-31 00:50' AND ml.date<'2026-03-31 01:00' AND pt.name='MOGEN_OB'
  AND ml.product_id IN (SELECT id FROM product_product WHERE default_code IN (SELECT code FROM rr));
CREATE TEMP TABLE st AS
SELECT rr.*, p.id pid, (SELECT count(*) FROM product_product x WHERE x.default_code=rr.code) n_prod, pg_temp.initial(p.id, rr.lid) init,
 (SELECT mlid FROM obl WHERE pid=p.id AND lid=rr.lid ORDER BY q DESC, mlid LIMIT 1) ob_ml,
 (SELECT q FROM obl WHERE pid=p.id AND lid=rr.lid ORDER BY q DESC, mlid LIMIT 1) ob_q,
 (SELECT pk.id FROM stock_picking pk JOIN res_partner pt ON pt.id=pk.partner_id JOIN stock_move_line ml ON ml.picking_id=pk.id WHERE pt.name='MOGEN_OB' AND ml.location_dest_id=rr.lid AND ml.date>='2026-03-31 00:50' AND ml.date<'2026-03-31 01:00' GROUP BY pk.id ORDER BY count(*) DESC, pk.id LIMIT 1) tpl_pk
FROM rr JOIN product_product p ON p.default_code=rr.code;
ALTER TABLE st ADD COLUMN tpl_ml int, ADD COLUMN tpl_mv int;
UPDATE st SET tpl_ml=(SELECT min(ml.id) FROM stock_move_line ml WHERE ml.picking_id=st.tpl_pk AND ml.location_dest_id=st.lid), tpl_mv=(SELECT ml.move_id FROM stock_move_line ml WHERE ml.id=(SELECT min(ml2.id) FROM stock_move_line ml2 WHERE ml2.picking_id=st.tpl_pk AND ml2.location_dest_id=st.lid));
\echo '== preconditions that FAIL (expect none): Initial == +delta, decrease fits in the largest OB line, template exists for new lines, not already applied'
SELECT code, lid, delta, init, ob_ml, ob_q, tpl_pk FROM st WHERE n_prod<>1 OR init<>delta
   OR (delta<0 AND (ob_ml IS NULL OR ob_q<-delta)) OR (delta>0 AND ob_ml IS NULL AND tpl_ml IS NULL);
DO $$ BEGIN
  IF (SELECT count(*) FROM st)<>(SELECT count(*) FROM rr) OR (SELECT count(*) FROM st)=0 THEN RAISE EXCEPTION 'row list mismatch'; END IF;
  IF (SELECT count(*) FROM st WHERE n_prod<>1 OR init<>delta OR (delta<0 AND (ob_ml IS NULL OR ob_q<-delta)) OR (delta>0 AND ob_ml IS NULL AND tpl_ml IS NULL))<>0 THEN RAISE EXCEPTION 'precondition failed'; END IF;
  IF (SELECT count(*) FROM stock_move WHERE backdate_remark='OB groupF rows 2026-11-09')<>0 THEN RAISE EXCEPTION 'already applied'; END IF;
END $$;
SQLEOF
)
WRITE=$(cat <<'SQLEOF'
CREATE TEMP TABLE sums AS SELECT (SELECT round(sum(quantity),4) FROM stock_quant WHERE product_id IN (SELECT pid FROM st)) q,
  (SELECT count(*) FROM stock_valuation_layer WHERE product_id IN (SELECT pid FROM st)) c, (SELECT round(sum(value)::numeric,2) FROM stock_valuation_layer WHERE product_id IN (SELECT pid FROM st)) v;
\echo '== reverse statements for edited OB lines (save):'
SELECT format('UPDATE stock_move_line SET quantity=quantity-(%s), quantity_product_uom=quantity_product_uom-(%s) WHERE id=%s; UPDATE stock_move SET product_uom_qty=product_uom_qty-(%s), product_qty=product_qty-(%s), quantity=quantity-(%s) WHERE id=%s;', delta, delta, ob_ml, delta, delta, delta, (SELECT move_id FROM stock_move_line WHERE id=ob_ml)) FROM st WHERE ob_ml IS NOT NULL ORDER BY ob_ml;
UPDATE stock_move m SET product_uom_qty=m.product_uom_qty+s.delta, product_qty=m.product_qty+s.delta, quantity=m.quantity+s.delta, write_date=now() AT TIME ZONE 'UTC'
 FROM st s JOIN stock_move_line ml ON ml.id=s.ob_ml WHERE s.ob_ml IS NOT NULL AND m.id=ml.move_id;
UPDATE stock_move_line ml SET quantity=ml.quantity+s.delta, quantity_product_uom=ml.quantity_product_uom+s.delta, write_date=now() AT TIME ZONE 'UTC' FROM st s WHERE s.ob_ml IS NOT NULL AND ml.id=s.ob_ml;
DO $$
DECLARE r record; nmid int;
BEGIN
  FOR r IN SELECT * FROM st WHERE ob_ml IS NULL AND delta>0 ORDER BY code LOOP
    DROP TABLE IF EXISTS m; DROP TABLE IF EXISTS l;
    CREATE TEMP TABLE m AS SELECT * FROM stock_move WHERE id=r.tpl_mv;
    UPDATE m SET id=nextval(pg_get_serial_sequence('stock_move','id')), product_id=r.pid,
      product_uom=(SELECT t.uom_id FROM product_product p JOIN product_template t ON t.id=p.product_tmpl_id WHERE p.id=r.pid),
      name=r.code||' OB (added: stock physically present before cut-off)', product_qty=r.delta, product_uom_qty=r.delta, quantity=r.delta, location_dest_id=r.lid,
      sale_line_id=NULL, purchase_line_id=NULL, group_id=NULL, rule_id=NULL, orderpoint_id=NULL, product_packaging_id=NULL,
      weight=coalesce((SELECT weight FROM product_product WHERE id=r.pid),0)*r.delta, backdate_remark='OB groupF rows 2026-11-09',
      create_date=now() AT TIME ZONE 'UTC', write_date=now() AT TIME ZONE 'UTC';
    INSERT INTO stock_move SELECT * FROM m;
    SELECT id INTO nmid FROM m;
    CREATE TEMP TABLE l AS SELECT * FROM stock_move_line WHERE id=r.tpl_ml;
    UPDATE l SET id=nextval(pg_get_serial_sequence('stock_move_line','id')), move_id=nmid, product_id=r.pid, product_uom_id=(SELECT product_uom FROM m),
      quantity=r.delta, quantity_product_uom=r.delta, location_dest_id=r.lid, lot_id=NULL, package_id=NULL, result_package_id=NULL, owner_id=NULL,
      description_picking=NULL, batch_id=NULL, workorder_id=NULL, production_id=NULL, create_date=now() AT TIME ZONE 'UTC', write_date=now() AT TIME ZONE 'UTC';
    INSERT INTO stock_move_line SELECT * FROM l;
    DROP TABLE m; DROP TABLE l;
  END LOOP;
END $$;
\echo '== post-check rows that FAIL (expect none): Initial 0'
SELECT code, lid, pg_temp.initial(pid, lid) init_after FROM st WHERE abs(pg_temp.initial(pid, lid))>0.0001;
DO $$
DECLARE bad int; mv int; q2 numeric; c2 int; v2 numeric;
BEGIN
  SELECT count(*) INTO bad FROM st WHERE abs(pg_temp.initial(pid, lid))>0.0001;
  SELECT count(*) INTO mv FROM stock_move_line ml JOIN stock_move m ON m.id=ml.move_id WHERE ml.product_id IN (SELECT pid FROM st) AND ml.date>='2026-03-31 00:50' AND ml.date<'2026-03-31 01:00' AND (m.quantity<>ml.quantity OR ml.quantity<>ml.quantity_product_uom OR ml.quantity<0);
  SELECT round(sum(quantity),4) INTO q2 FROM stock_quant WHERE product_id IN (SELECT pid FROM st);
  SELECT count(*), round(sum(value)::numeric,2) INTO c2, v2 FROM stock_valuation_layer WHERE product_id IN (SELECT pid FROM st);
  IF bad<>0 OR mv<>0 OR q2 IS DISTINCT FROM (SELECT q FROM sums) OR c2<>(SELECT c FROM sums) OR v2 IS DISTINCT FROM (SELECT v FROM sums) THEN RAISE EXCEPTION 'post-check failed: bad %, move/line mismatch %, quant %, svl % %', bad, mv, q2, c2, v2; END IF;
  RAISE NOTICE 'post-check ok: % rows, Initial 0, quants and SVL unchanged', (SELECT count(*) FROM st);
END $$;
SQLEOF
)
BODY="${BODY//@@FILTER@@/$FILTER}"
if [ "$MODE" = check ]; then
  { printf 'BEGIN;\n%s\nROLLBACK;\n' "$BODY"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q"; echo "== check ok"; exit 0
fi
COMMIT_OR_ROLLBACK=$([ "$MODE" = apply ] && echo COMMIT || echo ROLLBACK)
STAMP=$(date +%Y%m%d_%H%M%S)
echo ">>> backup stock_move + stock_move_line on mog-prod (~/db_backups/imex_obF_${STAMP}.dump)"
ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_move -t stock_move_line MOG_LIVE -f ~/db_backups/imex_obF_${STAMP}.dump && ls -l ~/db_backups/imex_obF_${STAMP}.dump"
{ printf 'BEGIN;\n%s\n%s\n%s;\n' "$BODY" "$WRITE" "$COMMIT_OR_ROLLBACK"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q"
echo ">>> $MODE finished ($COMMIT_OR_ROLLBACK)"
