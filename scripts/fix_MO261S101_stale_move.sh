#!/usr/bin/env bash
# MO261S101 @ FG50: move 221604 (LOJ0078963, 2026-04-08, hdr qty 7, move line 0, SVL +7/-7 net 0) is a stale duplicate of the real
# move 221607 (same ref/locs/date, move line 1, SVL +7-1-5). imex counts the header qty 7 as an extra In leg -> Initial -7 (user 2026-11-09).
# Fix: header product_qty/product_uom_qty/quantity := 0 (Q=7 to reverse). Quant/SVL/real move untouched. Same method as fix_twin_zero_line_moves.sh.
# Modes: check | dry (backup, update, report, ROLLBACK) | apply (COMMIT)
set -euo pipefail
MODE="${1:-check}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply" >&2; exit 2;; esac
REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'
IDS="221604"
BODY=$(cat <<SQLEOF
CREATE TEMP TABLE tw AS SELECT m.id, m.product_id, m.location_id, m.location_dest_id, m.product_qty q, m.reference FROM stock_move m WHERE m.id IN ($IDS);
CREATE FUNCTION pg_temp.initial(p int, loc int) RETURNS numeric LANGUAGE sql AS \$f\$
 SELECT coalesce((SELECT sum(quantity) FROM stock_quant WHERE product_id=p AND location_id=loc),0) - coalesce((
  SELECT sum(CASE WHEN ldst=loc THEN q ELSE 0 END)-sum(CASE WHEN lsrc=loc THEN q ELSE 0 END) FROM (
   SELECT sml.location_id lsrc, sml.location_dest_id ldst, sml.quantity_product_uom q FROM stock_move m JOIN stock_move_line sml ON sml.move_id=m.id
     WHERE m.product_id=p AND m.state='done' AND m.date>='2026-03-30 17:00' AND sml.quantity<>0 AND loc IN (sml.location_id, sml.location_dest_id)
   UNION ALL
   SELECT m.location_id, m.location_dest_id, m.product_qty FROM stock_move m WHERE m.product_id=p AND m.state='done' AND m.date>='2026-03-30 17:00'
     AND loc IN (m.location_id, m.location_dest_id) AND NOT EXISTS (SELECT 1 FROM stock_move_line x WHERE x.move_id=m.id AND x.quantity<>0)) t),0) \$f\$;
CREATE TEMP TABLE ib AS SELECT t.id, pg_temp.initial(t.product_id,t.location_id) i_src, pg_temp.initial(t.product_id,t.location_dest_id) i_dst FROM tw t;
DO \$\$ BEGIN
  IF (SELECT count(*) FROM tw)<>1 THEN RAISE EXCEPTION 'expected 1 move'; END IF;
  IF (SELECT count(*) FROM tw JOIN stock_move m ON m.id=tw.id WHERE m.state='done' AND m.product_qty>0
        AND NOT EXISTS (SELECT 1 FROM stock_move_line x WHERE x.move_id=m.id AND x.quantity<>0)
        AND EXISTS (SELECT 1 FROM stock_move d WHERE d.id<>m.id AND d.state='done' AND d.product_id=m.product_id AND d.reference=m.reference
          AND d.location_id=m.location_id AND d.location_dest_id=m.location_dest_id AND d.date=m.date
          AND EXISTS (SELECT 1 FROM stock_move_line y WHERE y.move_id=d.id AND y.quantity<>0)))<>1
  THEN RAISE EXCEPTION 'preconditions failed (done, no line, qty>0, sibling done move same ref/locs/date WITH a move line)'; END IF;
  IF (SELECT count(*) FROM tw JOIN stock_valuation_layer l ON l.stock_move_id=tw.id GROUP BY tw.id HAVING abs(sum(l.quantity))>0.0001 LIMIT 1)>0
  THEN RAISE EXCEPTION 'a twin has net non-zero SVL quantity'; END IF;
END \$\$;
SQLEOF
)
WRITE=$(cat <<SQLEOF
UPDATE stock_move SET product_qty=0, product_uom_qty=0, quantity=0, write_date=now() AT TIME ZONE 'UTC' WHERE id IN ($IDS);
CREATE TEMP TABLE ia AS SELECT t.id, pg_temp.initial(t.product_id,t.location_id) i_src, pg_temp.initial(t.product_id,t.location_dest_id) i_dst FROM tw t;
\echo '== per twin: product, src/dst loc, Initial before -> after (src | dst)'
SELECT pp.default_code, t.id, t.reference, t.location_id src, t.location_dest_id dst, t.q, b.i_src||' -> '||a.i_src src_init, b.i_dst||' -> '||a.i_dst dst_init
FROM tw t JOIN product_product pp ON pp.id=t.product_id JOIN ib b ON b.id=t.id JOIN ia a ON a.id=t.id ORDER BY 1,2;
\echo '== sums of |Initial| over the 30 sides: before / after'
SELECT (SELECT round(sum(abs(i_src))+sum(abs(i_dst)),4) FROM ib) before_abs, (SELECT round(sum(abs(i_src))+sum(abs(i_dst)),4) FROM ia) after_abs;
SQLEOF
)
if [ "$MODE" = check ]; then
  { printf 'BEGIN;\n%s\nROLLBACK;\n' "$BODY"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q"; echo "== check ok"; exit 0
fi
END=$([ "$MODE" = apply ] && echo COMMIT || echo ROLLBACK)
STAMP=$(date +%Y%m%d_%H%M%S)
echo ">>> backup stock_move on mog-prod (~/db_backups/stale_zero_${STAMP}.dump)"
ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_move MOG_LIVE -f ~/db_backups/stale_zero_${STAMP}.dump && ls -l ~/db_backups/stale_zero_${STAMP}.dump"
{ printf 'BEGIN;\n%s\n%s\n%s;\n' "$BODY" "$WRITE" "$END"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q -P pager=off"
echo ">>> $MODE finished ($END)"
