#!/usr/bin/env bash
# MO010S101 (product 5448) @FG10/Stock: physical count 21 (user 2026-11-10) == documents; quant 20 -> 21.
# Initial -1 in imex came from the 03-30 reset adjustment (-57) over-wiping by 1. Same method as fix_quant_to_docs.sh, extended to the RM01 half:
#   * stock_quant 85516 (loc 8) 20 -> 21
#   * withdraw our 4 correction layers: FG10 302250 (+1/+353.32 flush ledger fix) + 303644 (-2/-712.32 groupF), RM01 302251 (-1/-350.91) + 303645 (+1/+361.17 groupF)
#   * delete the zero-qty groupF tag moves 371679/371680 (and their lines, if any)
#   * one qty-only (value 0) layer per warehouse dated 2026-03-30 16:59:59.999999 cancelling the pre-cutoff residue => SVL all-time == window == quant
# Modes: check (plan in a transaction, ROLLBACK) | dry (backup + same, ROLLBACK) | apply (backup + COMMIT)
set -euo pipefail
MODE="${1:-check}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply" >&2; exit 2;; esac
REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'
BODY=$(cat <<'SQLEOF'
CREATE TEMP TABLE bef AS SELECT
 (SELECT count(*) FROM stock_valuation_layer WHERE product_id<>5448) other_svl,
 (SELECT round(sum(quantity),4) FROM stock_quant WHERE product_id<>5448) other_q,
 (SELECT round(sum(value)::numeric,2) FROM stock_valuation_layer WHERE product_id=5448) val_before,
 (SELECT quantity FROM stock_quant WHERE id=85516) q_before;
CREATE FUNCTION pg_temp.initial(p int, loc int) RETURNS numeric LANGUAGE sql AS $f$
 SELECT coalesce((SELECT sum(quantity) FROM stock_quant WHERE product_id=p AND location_id=loc),0) - coalesce((
  SELECT sum(CASE WHEN ldst=loc THEN q ELSE 0 END)-sum(CASE WHEN lsrc=loc THEN q ELSE 0 END) FROM (
   SELECT sml.location_id lsrc, sml.location_dest_id ldst, sml.quantity_product_uom q FROM stock_move m JOIN stock_move_line sml ON sml.move_id=m.id
     WHERE m.product_id=p AND m.state='done' AND m.date>='2026-03-30 17:00' AND sml.quantity<>0 AND loc IN (sml.location_id, sml.location_dest_id)
   UNION ALL
   SELECT m.location_id, m.location_dest_id, m.product_qty FROM stock_move m WHERE m.product_id=p AND m.state='done' AND m.date>='2026-03-30 17:00'
     AND loc IN (m.location_id, m.location_dest_id) AND NOT EXISTS (SELECT 1 FROM stock_move_line x WHERE x.move_id=m.id AND x.quantity<>0)) t),0) $f$;
DO $$
DECLARE fg int; rm int; pq numeric; i numeric; n int;
BEGIN
  SELECT id INTO fg FROM stock_warehouse WHERE code='FG10'; SELECT id INTO rm FROM stock_warehouse WHERE code='RM01';
  IF (SELECT default_code FROM product_product WHERE id=5448)<>'MO010S101' THEN RAISE EXCEPTION 'product'; END IF;
  IF NOT EXISTS (SELECT 1 FROM stock_quant WHERE id=85516 AND product_id=5448 AND location_id=8 AND quantity=20 AND reserved_quantity=0) THEN RAISE EXCEPTION 'quant 85516 not 20/unreserved'; END IF;
  IF (SELECT count(*) FROM stock_quant WHERE product_id=5448 AND location_id=8)<>1 THEN RAISE EXCEPTION 'several quants'; END IF;
  IF pg_temp.initial(5448,8)<>-1 THEN RAISE EXCEPTION 'Initial is % not -1', pg_temp.initial(5448,8); END IF;
  SELECT count(*) INTO n FROM stock_valuation_layer WHERE (id,warehouse_id,quantity,round(value,2)) IN ((302250,fg,1,353.32),(303644,fg,-2,-712.32),(302251,rm,-1,-350.91),(303645,rm,1,361.17));
  IF n<>4 THEN RAISE EXCEPTION 'expected 4 layers, found %', n; END IF;
  IF EXISTS (SELECT 1 FROM stock_valuation_layer WHERE stock_move_id IN (371679,371680) AND id NOT IN (303644,303645)) THEN RAISE EXCEPTION 'tag moves have other layers'; END IF;
  IF EXISTS (SELECT 1 FROM stock_move WHERE id IN (371679,371680) AND (reference<>'IMEX-REBASELINE-20260331' OR quantity<>0 OR product_id<>5448)) THEN RAISE EXCEPTION 'tag moves not as expected'; END IF;
  -- write
  UPDATE stock_quant SET quantity=21, write_date=now() AT TIME ZONE 'UTC' WHERE id=85516;
  DELETE FROM stock_valuation_layer WHERE id IN (302250,303644,302251,303645);
  DELETE FROM stock_move_line WHERE move_id IN (371679,371680);
  DELETE FROM stock_move WHERE id IN (371679,371680);
  -- pre-cutoff residue per warehouse (qty only, value 0)
  FOR i IN SELECT unnest(ARRAY[fg,rm]) LOOP
    SELECT coalesce(sum(quantity),0) INTO pq FROM stock_valuation_layer WHERE product_id=5448 AND warehouse_id=i::int AND COALESCE(accounting_date,create_date)<'2026-03-30 17:00';
    RAISE NOTICE 'warehouse % pre-cutoff residue %', i, pq;
    IF abs(pq)>0.0001 THEN
      INSERT INTO stock_valuation_layer (company_id, product_id, description, quantity, unit_cost, value, remaining_qty, remaining_value, warehouse_id, current_warehouse_id, create_uid, write_uid, create_date, write_date, accounting_date)
      VALUES (1, 5448, 'Reverse FIFO Reset Flush (pre-cutoff residue fix) - MO010S101 WH '||(SELECT code FROM stock_warehouse WHERE id=i::int), -pq, 0, 0, 0, 0, i::int, i::int, 2, 2, TIMESTAMP '2026-03-30 16:59:59.999999', now() AT TIME ZONE 'UTC', TIMESTAMP '2026-03-30 16:59:59.999999');
    END IF;
  END LOOP;
  -- post-checks
  IF abs(pg_temp.initial(5448,8))>0.0001 THEN RAISE EXCEPTION 'Initial not zero after change'; END IF;
  FOR i IN SELECT unnest(ARRAY[fg,rm]) LOOP
    IF abs((SELECT sum(quantity) FROM stock_valuation_layer WHERE product_id=5448 AND warehouse_id=i::int)
         - (SELECT coalesce(sum(q.quantity),0) FROM stock_quant q JOIN stock_location l ON l.id=q.location_id WHERE q.product_id=5448 AND l.warehouse_id=i::int AND l.usage IN ('internal','transit')))>0.0001
    OR abs((SELECT sum(quantity) FROM stock_valuation_layer WHERE product_id=5448 AND warehouse_id=i::int AND COALESCE(accounting_date,create_date)>='2026-03-30 17:00')
         - (SELECT coalesce(sum(q.quantity),0) FROM stock_quant q JOIN stock_location l ON l.id=q.location_id WHERE q.product_id=5448 AND l.warehouse_id=i::int AND l.usage IN ('internal','transit')))>0.0001
    THEN RAISE EXCEPTION 'SVL all-time/window != quant at warehouse %', i; END IF;
  END LOOP;
  IF (SELECT other_svl FROM bef)<>(SELECT count(*) FROM stock_valuation_layer WHERE product_id<>5448)
  OR (SELECT other_q FROM bef) IS DISTINCT FROM (SELECT round(sum(quantity),4) FROM stock_quant WHERE product_id<>5448) THEN RAISE EXCEPTION 'other products touched'; END IF;
END $$;
\echo '== after: per warehouse quant / SVL all-time / SVL window, and value change'
SELECT w.code, (SELECT coalesce(sum(q.quantity),0) FROM stock_quant q JOIN stock_location l ON l.id=q.location_id WHERE q.product_id=5448 AND l.warehouse_id=w.id AND l.usage IN ('internal','transit')) quant,
  sum(v.quantity) svl_all, sum(v.quantity) FILTER (WHERE COALESCE(v.accounting_date,v.create_date)>='2026-03-30 17:00') svl_win, round(sum(v.value)::numeric,2) val_all
FROM stock_valuation_layer v JOIN stock_warehouse w ON w.id=v.warehouse_id WHERE v.product_id=5448 AND w.code IN ('FG10','RM01') GROUP BY w.id, w.code ORDER BY 1;
SELECT (SELECT q_before FROM bef) quant_loc8_before, (SELECT quantity FROM stock_quant WHERE id=85516) quant_loc8_after,
  (SELECT val_before FROM bef) svl_value_before, round(sum(value)::numeric,2) svl_value_after, round(sum(value)::numeric,2)-(SELECT val_before FROM bef) value_change FROM stock_valuation_layer WHERE product_id=5448;
SQLEOF
)
if [ "$MODE" = check ]; then
  { printf 'BEGIN;\n%s\nROLLBACK;\n' "$BODY"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q"; echo "== check = executed inside a transaction and rolled back"; exit 0
fi
COMMIT_OR_ROLLBACK=$([ "$MODE" = apply ] && echo COMMIT || echo ROLLBACK)
STAMP=$(date +%Y%m%d_%H%M%S)
echo ">>> backup stock_quant + stock_valuation_layer + stock_move + stock_move_line on mog-prod (~/db_backups/quant_docs_MO010S101_${STAMP}.dump)"
ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_quant -t stock_valuation_layer -t stock_move -t stock_move_line MOG_LIVE -f ~/db_backups/quant_docs_MO010S101_${STAMP}.dump && ls -l ~/db_backups/quant_docs_MO010S101_${STAMP}.dump"
{ printf 'BEGIN;\n%s\n%s;\n' "$BODY" "$COMMIT_OR_ROLLBACK"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q"
echo ">>> $MODE finished ($COMMIT_OR_ROLLBACK)"
