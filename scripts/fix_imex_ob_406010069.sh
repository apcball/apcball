#!/usr/bin/env bash
# 406010069 (product 10355): imex Initial plug PD01/Stock +200 / RM02/Stock -200 fixed INSIDE the MOGEN_OB reseed
# (user rule 2026-11-05: everything before the OB must be 0). The reseed put all 600 at RM02 (move line 148852, picking
# RM02/IN/00362) although 200 were physically at PD01 (the pre-cutoff RM02->PD01 transfer that the FIFO Reset Flush
# neutralised; SVL already fixed by pair 302735/302736).
#   * RM02 OB line 148852 / move 159042:  600 -> 400
#   * NEW OB move + move line at PD01/Stock +200 inside the PD01 reseed picking 16271 (PD01/PD01RE/00002, MOGEN_OB),
#     cloned from that picking's move 211027 / line 198879; no SVL (pair layers already carry it), no quant change.
# Modes: check | dry (backup, change, post-checks, ROLLBACK) | apply (COMMIT)
# Rollback after apply:
#   DELETE FROM stock_move_line WHERE move_id IN (SELECT id FROM stock_move WHERE backdate_remark='OB add 406010069 2026-11-05');
#   DELETE FROM stock_move WHERE backdate_remark='OB add 406010069 2026-11-05';
#   UPDATE stock_move_line SET quantity=600, quantity_product_uom=600 WHERE id=148852;
#   UPDATE stock_move SET product_uom_qty=600, product_qty=600, quantity=600 WHERE id=159042;
set -euo pipefail
MODE="${1:-check}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply" >&2; exit 2;; esac
REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'

BODY=$(cat <<'SQLEOF'
CREATE TEMP TABLE c AS SELECT
 (SELECT id FROM product_product WHERE default_code='406010069') pid,
 (SELECT coalesce(sum(quantity),0) FROM stock_quant q WHERE q.product_id=(SELECT id FROM product_product WHERE default_code='406010069') AND q.location_id=92) q_pd,
 (SELECT coalesce(sum(quantity),0) FROM stock_quant q WHERE q.product_id=(SELECT id FROM product_product WHERE default_code='406010069') AND q.location_id=116) q_rm;
CREATE FUNCTION pg_temp.initial(loc int) RETURNS numeric LANGUAGE sql AS $f$
 SELECT coalesce((SELECT sum(quantity) FROM stock_quant WHERE product_id=(SELECT pid FROM c) AND location_id=loc),0)
  - coalesce((SELECT sum(CASE WHEN ml.location_dest_id=loc THEN ml.quantity ELSE 0 END)-sum(CASE WHEN ml.location_id=loc THEN ml.quantity ELSE 0 END)
      FROM stock_move_line ml WHERE ml.product_id=(SELECT pid FROM c) AND ml.state='done' AND ml.date>='2026-03-30 17:00' AND (ml.location_dest_id=loc OR ml.location_id=loc)),0) $f$;
\echo '== preconditions (expect init PD01 +200, RM02 -200, RM02 OB line 600, picking 16271 done/MOGEN_OB, template present, not applied)'
SELECT pg_temp.initial(92) init_pd01, pg_temp.initial(116) init_rm02,
 (SELECT quantity FROM stock_move_line WHERE id=148852) rm02_ob_qty,
 (SELECT pk.state||'/'||pt.name FROM stock_picking pk JOIN res_partner pt ON pt.id=pk.partner_id WHERE pk.id=16271) picking,
 (SELECT count(*) FROM stock_move_line WHERE id=198879 AND move_id=211027 AND picking_id=16271) template_ok,
 (SELECT count(*) FROM stock_move WHERE backdate_remark='OB add 406010069 2026-11-05') already;
DO $$ BEGIN
  IF pg_temp.initial(92)<>200 OR pg_temp.initial(116)<>-200 THEN RAISE EXCEPTION 'initial plugs not +200/-200'; END IF;
  IF (SELECT quantity FROM stock_move_line WHERE id=148852)<>600 OR (SELECT quantity FROM stock_move WHERE id=159042)<>600 THEN RAISE EXCEPTION 'RM02 OB line is not 600'; END IF;
  IF (SELECT count(*) FROM stock_move_line WHERE id=198879 AND move_id=211027 AND picking_id=16271)<>1 THEN RAISE EXCEPTION 'template line missing'; END IF;
  IF (SELECT count(*) FROM stock_move WHERE backdate_remark='OB add 406010069 2026-11-05')<>0 THEN RAISE EXCEPTION 'already applied'; END IF;
END $$;
SQLEOF
)
WRITE=$(cat <<'SQLEOF'
CREATE TEMP TABLE sums AS SELECT (SELECT round(sum(quantity),4) FROM stock_quant WHERE product_id=(SELECT pid FROM c)) q,
  (SELECT count(*) FROM stock_valuation_layer WHERE product_id=(SELECT pid FROM c)) svl_c,
  (SELECT round(sum(value)::numeric,2) FROM stock_valuation_layer WHERE product_id=(SELECT pid FROM c)) svl_v,
  (SELECT count(*) FROM stock_move_line WHERE picking_id=16271) pk_lines;
UPDATE stock_move_line SET quantity=400, quantity_product_uom=400, write_date=now() AT TIME ZONE 'UTC' WHERE id=148852;
UPDATE stock_move SET product_uom_qty=400, product_qty=400, quantity=400, write_date=now() AT TIME ZONE 'UTC' WHERE id=159042;
CREATE TEMP TABLE m AS SELECT * FROM stock_move WHERE id=211027;
UPDATE m SET id=nextval(pg_get_serial_sequence('stock_move','id')), product_id=(SELECT pid FROM c),
  product_uom=(SELECT t.uom_id FROM product_product p JOIN product_template t ON t.id=p.product_tmpl_id WHERE p.id=(SELECT pid FROM c)),
  name='406010069 OB (added: 200 physically at PD01 before cut-off)', product_qty=200, product_uom_qty=200, quantity=200,
  location_dest_id=92, sale_line_id=NULL, purchase_line_id=NULL, group_id=NULL, rule_id=NULL, orderpoint_id=NULL, product_packaging_id=NULL,
  weight=coalesce((SELECT weight FROM product_product WHERE id=(SELECT pid FROM c)),0)*200, backdate_remark='OB add 406010069 2026-11-05',
  create_date=now() AT TIME ZONE 'UTC', write_date=now() AT TIME ZONE 'UTC';
INSERT INTO stock_move SELECT * FROM m;
CREATE TEMP TABLE l AS SELECT * FROM stock_move_line WHERE id=198879;
UPDATE l SET id=nextval(pg_get_serial_sequence('stock_move_line','id')), move_id=(SELECT id FROM m), product_id=(SELECT pid FROM c),
  product_uom_id=(SELECT product_uom FROM m), quantity=200, quantity_product_uom=200, location_dest_id=92,
  lot_id=NULL, package_id=NULL, result_package_id=NULL, owner_id=NULL, description_picking=NULL, batch_id=NULL, workorder_id=NULL, production_id=NULL,
  create_date=now() AT TIME ZONE 'UTC', write_date=now() AT TIME ZONE 'UTC';
INSERT INTO stock_move_line SELECT * FROM l;
\echo '== post-check'
SELECT pg_temp.initial(92) init_pd01, pg_temp.initial(116) init_rm02,
 (SELECT quantity FROM stock_move_line WHERE id=148852) rm02_ob_qty,
 (SELECT quantity||' @ '||location_dest_id FROM stock_move_line WHERE move_id=(SELECT id FROM m)) new_line, (SELECT count(*) FROM stock_move_line WHERE picking_id=16271) pk_lines;
DO $$ BEGIN
  IF pg_temp.initial(92)<>0 OR pg_temp.initial(116)<>0 THEN RAISE EXCEPTION 'Initial not zero'; END IF;
  IF (SELECT round(sum(quantity),4) FROM stock_quant WHERE product_id=(SELECT pid FROM c)) IS DISTINCT FROM (SELECT q FROM sums)
     OR (SELECT count(*) FROM stock_valuation_layer WHERE product_id=(SELECT pid FROM c))<>(SELECT svl_c FROM sums)
     OR (SELECT round(sum(value)::numeric,2) FROM stock_valuation_layer WHERE product_id=(SELECT pid FROM c)) IS DISTINCT FROM (SELECT svl_v FROM sums)
     OR (SELECT count(*) FROM stock_move_line WHERE picking_id=16271)<>(SELECT pk_lines FROM sums)+1 THEN RAISE EXCEPTION 'post-check failed (quant/SVL/picking lines)'; END IF;
  IF (SELECT count(*) FROM stock_move_line ml JOIN stock_move m2 ON m2.id=ml.move_id WHERE ml.id IN (148852,(SELECT id FROM l)) AND (m2.quantity<>ml.quantity OR ml.quantity<>ml.quantity_product_uom))<>0 THEN RAISE EXCEPTION 'move/line mismatch'; END IF;
  RAISE NOTICE 'post-check ok: Initial PD01 and RM02 are 0, quants and SVL unchanged';
END $$;
SQLEOF
)
if [ "$MODE" = check ]; then
  { printf 'BEGIN;\n%s\nROLLBACK;\n' "$BODY"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q"
  echo "== check ok"; exit 0
fi
COMMIT_OR_ROLLBACK=$([ "$MODE" = apply ] && echo COMMIT || echo ROLLBACK)
STAMP=$(date +%Y%m%d_%H%M%S)
echo ">>> backup stock_move + stock_move_line on mog-prod (~/db_backups/imex_ob406_${STAMP}.dump)"
ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_move -t stock_move_line MOG_LIVE -f ~/db_backups/imex_ob406_${STAMP}.dump && ls -l ~/db_backups/imex_ob406_${STAMP}.dump"
{ printf 'BEGIN;\n%s\n%s\n%s;\n' "$BODY" "$WRITE" "$COMMIT_OR_ROLLBACK"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q"
echo ">>> $MODE finished ($COMMIT_OR_ROLLBACK)"
