#!/usr/bin/env bash
# 504110001 @RM02 on MOG_LIVE: buz_new_stock_card (stock.move.line based) ends at +50 while quant/SVL are 0.
# Cause: layer 305167 (pre-cutoff residue fix, SVL qty -50, value 0) has no stock move, so move lines keep the 50.
# Fix: one done stock.move + one move line RM02/Stock -> Inventory adjustment, qty 50, dated 2026-03-30 16:59:59.999999
# (cloned from the 03-30 count-adjust move 150915 / line 140727), inserted by SQL so quants are NOT touched and no SVL is created.
# Dry-run experiment 2026-11-11: line balance 50 -> 0, quant 0 unchanged, imex_inventory_report row identical.
# Modes: check | dry (backup, insert + post-check, ROLLBACK) | apply (COMMIT)
# Rollback: DELETE FROM stock_move_line WHERE reference='STOCKCARD-FIX-504110001'; DELETE FROM stock_move WHERE reference='STOCKCARD-FIX-504110001';
set -euo pipefail
MODE="${1:-check}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply" >&2; exit 2;; esac
REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'

BODY=$(cat <<'SQLEOF'
CREATE TEMP TABLE st AS SELECT
  (SELECT coalesce(sum(CASE WHEN dl.usage='internal' THEN ml.quantity ELSE 0 END)-sum(CASE WHEN sl.usage='internal' THEN ml.quantity ELSE 0 END),0)
     FROM stock_move_line ml JOIN stock_location sl ON sl.id=ml.location_id JOIN stock_location dl ON dl.id=ml.location_dest_id
     WHERE ml.product_id=11535 AND ml.state='done') line_bal,
  (SELECT coalesce(sum(q.quantity),0) FROM stock_quant q JOIN stock_location sl ON sl.id=q.location_id WHERE q.product_id=11535 AND sl.usage='internal') quant,
  (SELECT coalesce(sum(quantity),0) FROM stock_valuation_layer WHERE product_id=11535) svl_q,
  (SELECT count(*) FROM stock_move WHERE reference='STOCKCARD-FIX-504110001') done_n,
  (SELECT count(*) FROM stock_move WHERE id=150915 AND product_id=11535 AND state='done') tmpl_m,
  (SELECT count(*) FROM stock_move_line WHERE id=140727 AND move_id=150915) tmpl_l;
\echo '== preconditions'
SELECT * FROM st;
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM st WHERE line_bal=50 AND quant=0 AND svl_q=0 AND done_n=0 AND tmpl_m=1 AND tmpl_l=1) THEN
    RAISE EXCEPTION 'precondition failed';
  END IF;
END $$;
SQLEOF
)

WRITE=$(cat <<'SQLEOF'
CREATE TEMP TABLE m AS SELECT * FROM stock_move WHERE id=150915;
UPDATE m SET id=nextval(pg_get_serial_sequence('stock_move','id')), reference='STOCKCARD-FIX-504110001',
  name='Stock card correction 504110001 (SVL-only residue -50)', product_uom_qty=50, quantity=50,
  date=TIMESTAMP '2026-03-30 16:59:59.999999', create_date=now() AT TIME ZONE 'UTC', write_date=now() AT TIME ZONE 'UTC';
INSERT INTO stock_move SELECT * FROM m;
CREATE TEMP TABLE l AS SELECT * FROM stock_move_line WHERE id=140727;
UPDATE l SET id=nextval(pg_get_serial_sequence('stock_move_line','id')), move_id=(SELECT id FROM m), reference='STOCKCARD-FIX-504110001',
  quantity=50, date=TIMESTAMP '2026-03-30 16:59:59.999999', create_date=now() AT TIME ZONE 'UTC', write_date=now() AT TIME ZONE 'UTC';
INSERT INTO stock_move_line SELECT * FROM l;
\echo '== post-check'
SELECT (SELECT coalesce(sum(CASE WHEN dl.usage='internal' THEN ml.quantity ELSE 0 END)-sum(CASE WHEN sl.usage='internal' THEN ml.quantity ELSE 0 END),0)
          FROM stock_move_line ml JOIN stock_location sl ON sl.id=ml.location_id JOIN stock_location dl ON dl.id=ml.location_dest_id
          WHERE ml.product_id=11535 AND ml.state='done') line_bal_after,
       (SELECT coalesce(sum(q.quantity),0) FROM stock_quant q JOIN stock_location sl ON sl.id=q.location_id WHERE q.product_id=11535 AND sl.usage='internal') quant_after,
       (SELECT coalesce(sum(quantity),0) FROM stock_valuation_layer WHERE product_id=11535) svl_q_after;
DO $$
BEGIN
  IF (SELECT coalesce(sum(CASE WHEN dl.usage='internal' THEN ml.quantity ELSE 0 END)-sum(CASE WHEN sl.usage='internal' THEN ml.quantity ELSE 0 END),0)
        FROM stock_move_line ml JOIN stock_location sl ON sl.id=ml.location_id JOIN stock_location dl ON dl.id=ml.location_dest_id
        WHERE ml.product_id=11535 AND ml.state='done')<>0
     OR (SELECT coalesce(sum(q.quantity),0) FROM stock_quant q JOIN stock_location sl ON sl.id=q.location_id WHERE q.product_id=11535 AND sl.usage='internal')<>(SELECT quant FROM st)
     OR (SELECT count(*) FROM stock_move WHERE reference='STOCKCARD-FIX-504110001')<>1
     OR (SELECT count(*) FROM stock_move_line WHERE reference='STOCKCARD-FIX-504110001')<>1
     OR (SELECT count(*) FROM stock_valuation_layer WHERE stock_move_id=(SELECT id FROM m))<>0 THEN
    RAISE EXCEPTION 'post-check failed';
  END IF;
  RAISE NOTICE 'post-check ok: line balance 0, quant unchanged, 1 move + 1 line, no SVL';
END $$;
SQLEOF
)

if [ "$MODE" = check ]; then
  { printf 'BEGIN;\n%s\nROLLBACK;\n' "$BODY"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q"
  exit 0
fi
COMMIT_OR_ROLLBACK=$([ "$MODE" = apply ] && echo COMMIT || echo ROLLBACK)
STAMP=$(date +%Y%m%d_%H%M%S)
echo ">>> backup stock_move + stock_move_line (~/db_backups/sc504110001_${STAMP}.dump)"
ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_move -t stock_move_line MOG_LIVE -f ~/db_backups/sc504110001_${STAMP}.dump && ls -l ~/db_backups/sc504110001_${STAMP}.dump"
{ printf 'BEGIN;\n%s\n%s\n%s;\n' "$BODY" "$WRITE" "$COMMIT_OR_ROLLBACK"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q"
echo ">>> $MODE finished ($COMMIT_OR_ROLLBACK)"
