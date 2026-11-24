#!/usr/bin/env bash
# OBSOLETE (2026-11-09): user confirmed the MOGEN_OB amounts are CORRECT; Initial plugs must NOT be fixed by editing/adding OB lines or rows before the OB.
# The OB edits applied on 2026-11-05 were reverted on 2026-11-09. DO NOT RUN. Kept only for history.
# MA0142101 (product 3969): imex Initial plug FG10/Stock +2 / FG40/Stock -2 fixed INSIDE the MOGEN_OB reseed
# (user rule 2026-11-05: everything before the OB must be 0).
#   * FG40 OB (picking FG40/FG40/00001): the last two 1-unit lines (move lines 192970 / 192971, moves 203160 / 203161) -> 0
#   * NEW OB move + move line at FG10/Stock +2 inside the FG10 reseed picking 15046 (FG10/FG10/00063, MOGEN_OB), cloned from
#     that picking's move 170017 / line 159827; no SVL (group-F rebaseline pair 303222/303223 already carries it), no quant change.
# Modes: check | dry (backup, change, post-checks, ROLLBACK) | apply (COMMIT)
# Rollback after apply:
#   DELETE FROM stock_move_line WHERE move_id IN (SELECT id FROM stock_move WHERE backdate_remark='OB add MA0142101 2026-11-05');
#   DELETE FROM stock_move WHERE backdate_remark='OB add MA0142101 2026-11-05';
#   UPDATE stock_move_line SET quantity=1, quantity_product_uom=1 WHERE id IN (192970,192971);
#   UPDATE stock_move SET product_uom_qty=1, product_qty=1, quantity=1 WHERE id IN (203160,203161);
set -euo pipefail
MODE="${1:-check}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply" >&2; exit 2;; esac
REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'

BODY=$(cat <<'SQLEOF'
CREATE TEMP TABLE c AS SELECT (SELECT id FROM product_product WHERE default_code='MA0142101') pid;
CREATE FUNCTION pg_temp.initial(loc int) RETURNS numeric LANGUAGE sql AS $f$
 SELECT coalesce((SELECT sum(quantity) FROM stock_quant WHERE product_id=(SELECT pid FROM c) AND location_id=loc),0)
  - coalesce((SELECT sum(CASE WHEN ml.location_dest_id=loc THEN ml.quantity ELSE 0 END)-sum(CASE WHEN ml.location_id=loc THEN ml.quantity ELSE 0 END)
      FROM stock_move_line ml WHERE ml.product_id=(SELECT pid FROM c) AND ml.state='done' AND ml.date>='2026-03-30 17:00' AND (ml.location_dest_id=loc OR ml.location_id=loc)),0) $f$;
\echo '== preconditions (expect init FG10 +2, FG40 -2, both FG40 OB lines qty 1 in MOGEN_OB picking, picking 15046 done/MOGEN_OB, template present, not applied)'
SELECT pg_temp.initial(8) init_fg10, pg_temp.initial(76) init_fg40,
 (SELECT string_agg(quantity::text,',') FROM stock_move_line WHERE id IN (192970,192971)) fg40_lines,
 (SELECT pk.state||'/'||pt.name FROM stock_picking pk JOIN res_partner pt ON pt.id=pk.partner_id WHERE pk.id=15046) picking,
 (SELECT count(*) FROM stock_move_line WHERE id=159827 AND move_id=170017 AND picking_id=15046) template_ok,
 (SELECT count(*) FROM stock_move WHERE backdate_remark='OB add MA0142101 2026-11-05') already;
DO $$ BEGIN
  IF pg_temp.initial(8)<>2 OR pg_temp.initial(76)<>-2 THEN RAISE EXCEPTION 'initial plugs not +2/-2'; END IF;
  IF (SELECT count(*) FROM stock_move_line ml JOIN stock_move m ON m.id=ml.move_id WHERE ml.id IN (192970,192971) AND ml.move_id IN (203160,203161) AND ml.quantity=1 AND m.quantity=1 AND ml.product_id=(SELECT pid FROM c) AND ml.location_dest_id=76)<>2 THEN RAISE EXCEPTION 'FG40 OB lines are not the expected 1-unit lines'; END IF;
  IF (SELECT count(*) FROM stock_move_line WHERE id=159827 AND move_id=170017 AND picking_id=15046)<>1 THEN RAISE EXCEPTION 'template line missing'; END IF;
  IF (SELECT count(*) FROM stock_move WHERE backdate_remark='OB add MA0142101 2026-11-05')<>0 THEN RAISE EXCEPTION 'already applied'; END IF;
END $$;
SQLEOF
)
WRITE=$(cat <<'SQLEOF'
CREATE TEMP TABLE sums AS SELECT (SELECT round(sum(quantity),4) FROM stock_quant WHERE product_id=(SELECT pid FROM c)) q,
  (SELECT count(*) FROM stock_valuation_layer WHERE product_id=(SELECT pid FROM c)) svl_c,
  (SELECT round(sum(value)::numeric,2) FROM stock_valuation_layer WHERE product_id=(SELECT pid FROM c)) svl_v,
  (SELECT count(*) FROM stock_move_line WHERE picking_id=15046) pk_lines;
UPDATE stock_move_line SET quantity=0, quantity_product_uom=0, write_date=now() AT TIME ZONE 'UTC' WHERE id IN (192970,192971);
UPDATE stock_move SET product_uom_qty=0, product_qty=0, quantity=0, write_date=now() AT TIME ZONE 'UTC' WHERE id IN (203160,203161);
CREATE TEMP TABLE m AS SELECT * FROM stock_move WHERE id=170017;
UPDATE m SET id=nextval(pg_get_serial_sequence('stock_move','id')), product_id=(SELECT pid FROM c),
  product_uom=(SELECT t.uom_id FROM product_product p JOIN product_template t ON t.id=p.product_tmpl_id WHERE p.id=(SELECT pid FROM c)),
  name='MA0142101 OB (added: 2 physically at FG10 before cut-off)', product_qty=2, product_uom_qty=2, quantity=2,
  location_dest_id=8, sale_line_id=NULL, purchase_line_id=NULL, group_id=NULL, rule_id=NULL, orderpoint_id=NULL, product_packaging_id=NULL,
  weight=coalesce((SELECT weight FROM product_product WHERE id=(SELECT pid FROM c)),0)*2, backdate_remark='OB add MA0142101 2026-11-05',
  create_date=now() AT TIME ZONE 'UTC', write_date=now() AT TIME ZONE 'UTC';
INSERT INTO stock_move SELECT * FROM m;
CREATE TEMP TABLE l AS SELECT * FROM stock_move_line WHERE id=159827;
UPDATE l SET id=nextval(pg_get_serial_sequence('stock_move_line','id')), move_id=(SELECT id FROM m), product_id=(SELECT pid FROM c),
  product_uom_id=(SELECT product_uom FROM m), quantity=2, quantity_product_uom=2, location_dest_id=8,
  lot_id=NULL, package_id=NULL, result_package_id=NULL, owner_id=NULL, description_picking=NULL, batch_id=NULL, workorder_id=NULL, production_id=NULL,
  create_date=now() AT TIME ZONE 'UTC', write_date=now() AT TIME ZONE 'UTC';
INSERT INTO stock_move_line SELECT * FROM l;
\echo '== post-check'
SELECT pg_temp.initial(8) init_fg10, pg_temp.initial(76) init_fg40,
 (SELECT string_agg(quantity::text,',') FROM stock_move_line WHERE id IN (192970,192971)) fg40_lines,
 (SELECT quantity||' @ '||location_dest_id FROM stock_move_line WHERE move_id=(SELECT id FROM m)) new_line, (SELECT count(*) FROM stock_move_line WHERE picking_id=15046) pk_lines;
DO $$ BEGIN
  IF pg_temp.initial(8)<>0 OR pg_temp.initial(76)<>0 THEN RAISE EXCEPTION 'Initial not zero'; END IF;
  IF (SELECT round(sum(quantity),4) FROM stock_quant WHERE product_id=(SELECT pid FROM c)) IS DISTINCT FROM (SELECT q FROM sums)
     OR (SELECT count(*) FROM stock_valuation_layer WHERE product_id=(SELECT pid FROM c))<>(SELECT svl_c FROM sums)
     OR (SELECT round(sum(value)::numeric,2) FROM stock_valuation_layer WHERE product_id=(SELECT pid FROM c)) IS DISTINCT FROM (SELECT svl_v FROM sums)
     OR (SELECT count(*) FROM stock_move_line WHERE picking_id=15046)<>(SELECT pk_lines FROM sums)+1 THEN RAISE EXCEPTION 'post-check failed (quant/SVL/picking lines)'; END IF;
  IF (SELECT count(*) FROM stock_move_line ml JOIN stock_move m2 ON m2.id=ml.move_id WHERE (ml.id IN (192970,192971) OR ml.id=(SELECT id FROM l)) AND (m2.quantity<>ml.quantity OR ml.quantity<>ml.quantity_product_uom))<>0 THEN RAISE EXCEPTION 'move/line mismatch'; END IF;
  RAISE NOTICE 'post-check ok: Initial FG10 and FG40 are 0, quants and SVL unchanged';
END $$;
SQLEOF
)
if [ "$MODE" = check ]; then
  { printf 'BEGIN;\n%s\nROLLBACK;\n' "$BODY"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q"
  echo "== check ok"; exit 0
fi
COMMIT_OR_ROLLBACK=$([ "$MODE" = apply ] && echo COMMIT || echo ROLLBACK)
STAMP=$(date +%Y%m%d_%H%M%S)
echo ">>> backup stock_move + stock_move_line on mog-prod (~/db_backups/imex_obMA0142_${STAMP}.dump)"
ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_move -t stock_move_line MOG_LIVE -f ~/db_backups/imex_obMA0142_${STAMP}.dump && ls -l ~/db_backups/imex_obMA0142_${STAMP}.dump"
{ printf 'BEGIN;\n%s\n%s\n%s;\n' "$BODY" "$WRITE" "$COMMIT_OR_ROLLBACK"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q"
echo ">>> $MODE finished ($COMMIT_OR_ROLLBACK)"
