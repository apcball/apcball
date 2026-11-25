#!/usr/bin/env bash
# LTL12010 @FG10: imex Initial -1 (user 2026-11-10 chose option 2: remove the IMEX-REBASELINE layer, give the quant back).
# State before: ADJ2 layer 181324 (+1/+675.23, remaining 0) was cancelled by group-F rebaseline layer 303635 (-1/-675.23, move 371670),
# rebaseline also parked the +1 quant on Virtual Locations/Inventory adjustment (quant 28835 = +1), FG10/Stock quant 0 -> imex Initial = 0 - 1 = -1.
# Undo: delete layer 303635 + move 371670 (no lines, no GL), FG10/Stock quant +1 (new row), Inventory-adjustment quant 28835 1 -> 0,
# ADJ2 layer 181324 remaining 0 -> 1 / 675.23 (FIFO queue == quant). Product total quant stays 0.
# Modes: check | dry (backup, change, post-checks, ROLLBACK) | apply (COMMIT)
# Reverse: restore from ~/db_backups/ltl12010_undo_*.dump (stock_quant, stock_move, stock_valuation_layer) or recreate layer/move from the printed row dump.
set -euo pipefail
MODE="${1:-check}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply" >&2; exit 2;; esac
REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'
BODY=$(cat <<'SQLEOF'
CREATE TEMP TABLE c AS SELECT
 (SELECT id FROM product_product WHERE default_code='LTL12010') pid,
 (SELECT id FROM stock_location WHERE usage='internal' AND complete_name LIKE '%FG10/Stock') fg10,
 (SELECT quantity FROM stock_quant WHERE id=28835) q_adj,
 (SELECT count(*) FROM stock_quant q WHERE q.product_id=(SELECT id FROM product_product WHERE default_code='LTL12010') AND q.location_id=(SELECT id FROM stock_location WHERE usage='internal' AND complete_name LIKE '%FG10/Stock')) q_fg10_rows,
 (SELECT quantity||'/'||value||'/'||coalesce(remaining_qty,0) FROM stock_valuation_layer WHERE id=303635 AND stock_move_id=371670) l_rebase,
 (SELECT remaining_qty||'/'||coalesce(remaining_value,0)||'/'||value FROM stock_valuation_layer WHERE id=181324 AND stock_move_id=222172) l_adj2,
 (SELECT count(*) FROM stock_move_line WHERE move_id=371670) n_lines,
 (SELECT count(*) FROM stock_valuation_layer WHERE stock_valuation_layer_id=303635 OR origin_valuation_layer_id=303635) n_children,
 (SELECT count(*) FROM stock_valuation_layer_usage WHERE stock_valuation_layer_id=303635 OR dest_stock_valuation_layer_id=303635) n_usage,
 (SELECT count(*) FROM stock_valuation_layer_landed_cost WHERE valuation_layer_id=303635) n_lc,
 (SELECT count(*) FROM stock_move_move_rel WHERE move_orig_id=371670 OR move_dest_id=371670) n_rel,
 (SELECT count(*) FROM mrp_period_cost_alloc WHERE svl_id=303635 OR base_layer_id=303635 OR reversal_svl_id=303635 OR origin_layer_id=303635) n_mrp,
 (SELECT count(*) FROM stock_count_adjustment_mismatch WHERE svl_id=303635) n_mm,
 (SELECT account_move_id FROM stock_valuation_layer WHERE id=303635) acct;
\echo '== preconditions (expect q_adj 1, q_fg10_rows 0, l_rebase -1/-675.23/0, l_adj2 0/0/675.23, all counts 0, acct NULL)'
SELECT * FROM c;
DO $$ BEGIN
 IF (SELECT q_adj FROM c)<>1 OR (SELECT q_fg10_rows FROM c)<>0 OR (SELECT l_rebase FROM c) NOT LIKE '-1.0%/-675.23%/0%' OR (SELECT l_adj2 FROM c) NOT LIKE '0%/0%/675.23%'
  OR (SELECT n_lines+n_children+n_usage+n_lc+n_rel+n_mrp+n_mm FROM c)<>0 OR (SELECT acct FROM c) IS NOT NULL THEN RAISE EXCEPTION 'preconditions failed'; END IF;
END $$;
\echo '== row dump of what is changed (for reversal)'
SELECT * FROM stock_valuation_layer WHERE id IN (303635,181324);
SELECT id, name, reference, state, product_id, product_qty, location_id, location_dest_id, date FROM stock_move WHERE id=371670;
SELECT id, quantity FROM stock_quant WHERE id=28835;
CREATE FUNCTION pg_temp.initial(p int, loc int) RETURNS numeric LANGUAGE sql AS $f$
 SELECT coalesce((SELECT sum(quantity) FROM stock_quant WHERE product_id=p AND location_id=loc),0) - coalesce((
  SELECT sum(CASE WHEN ldst=loc THEN q ELSE 0 END)-sum(CASE WHEN lsrc=loc THEN q ELSE 0 END) FROM (
   SELECT sml.location_id lsrc, sml.location_dest_id ldst, sml.quantity_product_uom q FROM stock_move m JOIN stock_move_line sml ON sml.move_id=m.id
     WHERE m.product_id=p AND m.state='done' AND m.date>='2026-03-30 17:00' AND sml.quantity<>0 AND loc IN (sml.location_id, sml.location_dest_id)
   UNION ALL
   SELECT m.location_id, m.location_dest_id, m.product_qty FROM stock_move m WHERE m.product_id=p AND m.state='done' AND m.date>='2026-03-30 17:00'
     AND loc IN (m.location_id, m.location_dest_id) AND NOT EXISTS (SELECT 1 FROM stock_move_line x WHERE x.move_id=m.id AND x.quantity<>0)) t),0) $f$;
\echo '== Initial before'
SELECT pg_temp.initial(pid,fg10) FROM c;
SQLEOF
)
WRITE=$(cat <<'SQLEOF'
DELETE FROM stock_valuation_layer WHERE id=303635 AND stock_move_id=371670;
DELETE FROM stock_move WHERE id=371670 AND reference='IMEX-REBASELINE-20260331';
INSERT INTO stock_quant (product_id, location_id, company_id, quantity, reserved_quantity, in_date, create_uid, write_uid, create_date, write_date)
 SELECT pid, fg10, 1, 1, 0, '2026-03-31 01:30:00', 1, 1, now() AT TIME ZONE 'UTC', now() AT TIME ZONE 'UTC' FROM c;
UPDATE stock_quant SET quantity=0, write_date=now() AT TIME ZONE 'UTC' WHERE id=28835;
UPDATE stock_valuation_layer SET remaining_qty=1, remaining_value=675.23 WHERE id=181324;
\echo '== Initial after (expect 0)'
SELECT pg_temp.initial(pid,fg10) FROM c;
DO $$ DECLARE w numeric; r numeric; qt numeric; i numeric;
BEGIN
 SELECT pg_temp.initial(pid,fg10) INTO i FROM c;
 SELECT coalesce(sum(quantity),0) INTO w FROM stock_valuation_layer WHERE product_id=(SELECT pid FROM c) AND warehouse_id=1 AND coalesce(accounting_date,create_date)>='2026-03-30 17:00';
 SELECT coalesce(sum(remaining_qty),0) INTO r FROM stock_valuation_layer WHERE product_id=(SELECT pid FROM c) AND warehouse_id=1;
 SELECT coalesce(sum(quantity),0) INTO qt FROM stock_quant WHERE product_id=(SELECT pid FROM c);
 IF i<>0 THEN RAISE EXCEPTION 'Initial % not 0', i; END IF;
 IF w<>1 OR r<>1 THEN RAISE EXCEPTION 'window SVL % / queue % should be 1', w, r; END IF;
 IF qt<>0 THEN RAISE EXCEPTION 'product total quant % should stay 0', qt; END IF;
 RAISE NOTICE 'post-check ok: Initial 0, window SVL qty 1 == queue 1 == FG10 quant 1, product total quant 0';
END $$;
SQLEOF
)
OUT=/tmp/ltl12010_undo_$(date +%Y%m%d_%H%M%S).out
if [ "$MODE" = check ]; then
  { printf 'BEGIN;\n%s\nROLLBACK;\n' "$BODY"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q" 2>&1 | tee "$OUT"; grep -q "ERROR:" "$OUT" && { echo ">>> CHECK FAILED" >&2; exit 1; }; echo "== check ok"; exit 0
fi
COMMIT_OR_ROLLBACK=$([ "$MODE" = apply ] && echo COMMIT || echo ROLLBACK)
STAMP=$(date +%Y%m%d_%H%M%S)
echo ">>> backup stock_quant/stock_move/stock_valuation_layer on mog-prod (~/db_backups/ltl12010_undo_${STAMP}.dump)"
ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_quant -t stock_move -t stock_valuation_layer MOG_LIVE -f ~/db_backups/ltl12010_undo_${STAMP}.dump && ls -l ~/db_backups/ltl12010_undo_${STAMP}.dump"
{ printf 'BEGIN;\n%s\n%s\n%s;\n' "$BODY" "$WRITE" "$COMMIT_OR_ROLLBACK"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q" 2>&1 | tee "$OUT"
if grep -q "ERROR:" "$OUT"; then echo ">>> FAILED (nothing committed): $(grep -m1 'ERROR:' "$OUT")" >&2; exit 1; fi
echo ">>> $MODE finished ($COMMIT_OR_ROLLBACK); output $OUT"
