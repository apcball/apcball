#!/usr/bin/env bash
# MO010S101 @FG10: imex Initial -1 = pre-cutoff negative history (quant == all-time documents, 20). User 2026-11-10 chose option 2 (like LTL12010):
# give the quant the missing unit so quant == window documents (21), rebaseline SVL 303644 (move 371679) shrinks -2 -> -1 so window SVL == quant.
# Change: FG10/Stock quant 20 -> 21, Virtual Locations/Inventory adjustment quant -1 (counter), SVL 303644 qty -2/-712.32 -> -1/-356.16 (+ move name/description text).
# The RM01 leg (move 371680 / SVL 303645, +1) is untouched. Product total quant stays 0. FIFO queue (remaining_qty, +4 drift before) NOT touched.
# Modes: check | dry (backup, change, post-checks, ROLLBACK) | apply (COMMIT)
# Reverse: restore from ~/db_backups/mo010s101_undo_*.dump (stock_quant, stock_move, stock_valuation_layer) or recreate layer/move from the printed row dump.
set -euo pipefail
MODE="${1:-check}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply" >&2; exit 2;; esac
REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'
BODY=$(cat <<'SQLEOF'
CREATE TEMP TABLE c AS SELECT
 (SELECT id FROM product_product WHERE default_code='MO010S101') pid,
 (SELECT id FROM stock_location WHERE usage='internal' AND complete_name LIKE '%FG10/Stock') fg10,
 (SELECT id FROM stock_location WHERE usage='inventory' AND complete_name='Virtual Locations/Inventory adjustment') adj,
 (SELECT quantity FROM stock_quant WHERE product_id=(SELECT id FROM product_product WHERE default_code='MO010S101') AND location_id=(SELECT id FROM stock_location WHERE usage='internal' AND complete_name LIKE '%FG10/Stock')) q_fg10,
 (SELECT count(*) FROM stock_quant WHERE product_id=(SELECT id FROM product_product WHERE default_code='MO010S101') AND location_id=(SELECT id FROM stock_location WHERE usage='inventory' AND complete_name='Virtual Locations/Inventory adjustment')) n_adj_rows,
 (SELECT quantity||'/'||value||'/'||warehouse_id FROM stock_valuation_layer WHERE id=303644 AND stock_move_id=371679) l_rb,
 (SELECT count(*) FROM stock_valuation_layer WHERE stock_valuation_layer_id=303644 OR origin_valuation_layer_id=303644) n_children,
 (SELECT count(*) FROM stock_valuation_layer_usage WHERE stock_valuation_layer_id=303644 OR dest_stock_valuation_layer_id=303644) n_usage,
 (SELECT count(*) FROM mrp_period_cost_alloc WHERE svl_id=303644 OR base_layer_id=303644 OR reversal_svl_id=303644 OR origin_layer_id=303644) n_mrp,
 (SELECT count(*) FROM stock_count_adjustment_mismatch WHERE svl_id=303644) n_mm,
 (SELECT account_move_id FROM stock_valuation_layer WHERE id=303644) acct,
 (SELECT quantity FROM stock_quant WHERE product_id=(SELECT id FROM product_product WHERE default_code='MO010S101') AND location_id=(SELECT id FROM stock_location WHERE usage='inventory' AND complete_name='Virtual Locations/Inventory adjustment')) q_adj;
\echo '== preconditions (expect q_fg10 20, n_adj_rows 1, l_rb -2/-712.32/1, counts 0, acct NULL)'
SELECT * FROM c;
DO $$ BEGIN
 IF (SELECT q_fg10 FROM c)<>20 OR (SELECT n_adj_rows FROM c)<>1 OR (SELECT l_rb FROM c) NOT LIKE '-2.0%/-712.32%/1'
  OR (SELECT n_children+n_usage+n_mrp+n_mm FROM c)<>0 OR (SELECT acct FROM c) IS NOT NULL THEN RAISE EXCEPTION 'preconditions failed'; END IF;
END $$;
\echo '== row dump (reversal)'
SELECT id, quantity, value, unit_cost, description, remaining_qty, remaining_value FROM stock_valuation_layer WHERE id=303644;
SELECT id, name FROM stock_move WHERE id=371679;
SELECT id, location_id, quantity FROM stock_quant WHERE product_id=(SELECT pid FROM c) AND location_id IN (SELECT fg10 FROM c UNION SELECT adj FROM c);
CREATE FUNCTION pg_temp.initial(p int, loc int) RETURNS numeric LANGUAGE sql AS $f$
 SELECT coalesce((SELECT sum(quantity) FROM stock_quant WHERE product_id=p AND location_id=loc),0) - coalesce((
  SELECT sum(CASE WHEN ldst=loc THEN q ELSE 0 END)-sum(CASE WHEN lsrc=loc THEN q ELSE 0 END) FROM (
   SELECT sml.location_id lsrc, sml.location_dest_id ldst, sml.quantity_product_uom q FROM stock_move m JOIN stock_move_line sml ON sml.move_id=m.id
     WHERE m.product_id=p AND m.state='done' AND m.date>='2026-03-30 17:00' AND sml.quantity<>0 AND loc IN (sml.location_id, sml.location_dest_id)
   UNION ALL
   SELECT m.location_id, m.location_dest_id, m.product_qty FROM stock_move m WHERE m.product_id=p AND m.state='done' AND m.date>='2026-03-30 17:00'
     AND loc IN (m.location_id, m.location_dest_id) AND NOT EXISTS (SELECT 1 FROM stock_move_line x WHERE x.move_id=m.id AND x.quantity<>0)) t),0) $f$;
\echo '== Initial before / window SVL wh1 before'
SELECT pg_temp.initial(pid,fg10) init, (SELECT sum(quantity) FROM stock_valuation_layer WHERE product_id=pid AND warehouse_id=1 AND coalesce(accounting_date,create_date)>='2026-03-30 17:00') win_svl FROM c;
SQLEOF
)
WRITE=$(cat <<'SQLEOF'
UPDATE stock_quant SET quantity=quantity+1, write_date=now() AT TIME ZONE 'UTC' WHERE product_id=(SELECT pid FROM c) AND location_id=(SELECT fg10 FROM c);
UPDATE stock_quant SET quantity=quantity-1, write_date=now() AT TIME ZONE 'UTC' WHERE product_id=(SELECT pid FROM c) AND location_id=(SELECT adj FROM c);
UPDATE stock_valuation_layer SET quantity=-1, value=-356.16, unit_cost=CASE WHEN unit_cost IS NULL THEN NULL ELSE unit_cost END, description=replace(description,'-2.0','-1.0') WHERE id=303644;
UPDATE stock_move SET name=replace(name,'-2.0','-1.0') WHERE id=371679;
\echo '== Initial after (expect 0) / window SVL wh1 (expect 21)'
SELECT pg_temp.initial(pid,fg10) init, (SELECT sum(quantity) FROM stock_valuation_layer WHERE product_id=pid AND warehouse_id=1 AND coalesce(accounting_date,create_date)>='2026-03-30 17:00') win_svl FROM c;
DO $$ DECLARE i numeric; w numeric; qt numeric; qf numeric;
BEGIN
 SELECT pg_temp.initial(pid,fg10) INTO i FROM c;
 SELECT coalesce(sum(quantity),0) INTO w FROM stock_valuation_layer WHERE product_id=(SELECT pid FROM c) AND warehouse_id=1 AND coalesce(accounting_date,create_date)>='2026-03-30 17:00';
 SELECT coalesce(sum(quantity),0) INTO qt FROM stock_quant WHERE product_id=(SELECT pid FROM c);
 SELECT quantity INTO qf FROM stock_quant WHERE product_id=(SELECT pid FROM c) AND location_id=(SELECT fg10 FROM c);
 IF i<>0 THEN RAISE EXCEPTION 'Initial % not 0', i; END IF;
 IF w<>qf OR qf<>21 THEN RAISE EXCEPTION 'window SVL % vs quant FG10 % (want 21)', w, qf; END IF;
 IF qt<>0 THEN RAISE EXCEPTION 'product total quant % should stay 0', qt; END IF;
 RAISE NOTICE 'post-check ok: Initial 0, window SVL wh1 == FG10 quant == 21, product total quant 0';
END $$;
SQLEOF
)
OUT=/tmp/mo010s101_undo_$(date +%Y%m%d_%H%M%S).out
if [ "$MODE" = check ]; then
  { printf 'BEGIN;\n%s\nROLLBACK;\n' "$BODY"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q" 2>&1 | tee "$OUT"; grep -q "ERROR:" "$OUT" && { echo ">>> CHECK FAILED" >&2; exit 1; }; echo "== check ok"; exit 0
fi
COMMIT_OR_ROLLBACK=$([ "$MODE" = apply ] && echo COMMIT || echo ROLLBACK)
STAMP=$(date +%Y%m%d_%H%M%S)
echo ">>> backup stock_quant/stock_move/stock_valuation_layer on mog-prod (~/db_backups/mo010s101_undo_${STAMP}.dump)"
ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_quant -t stock_move -t stock_valuation_layer MOG_LIVE -f ~/db_backups/mo010s101_undo_${STAMP}.dump && ls -l ~/db_backups/mo010s101_undo_${STAMP}.dump"
{ printf 'BEGIN;\n%s\n%s\n%s;\n' "$BODY" "$WRITE" "$COMMIT_OR_ROLLBACK"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q" 2>&1 | tee "$OUT"
if grep -q "ERROR:" "$OUT"; then echo ">>> FAILED (nothing committed): $(grep -m1 'ERROR:' "$OUT")" >&2; exit 1; fi
echo ">>> $MODE finished ($COMMIT_OR_ROLLBACK); output $OUT"
