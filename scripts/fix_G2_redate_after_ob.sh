#!/usr/bin/env bash
# G2 option (ข): move the 14 G2 SVL layers (description 'Reverse FIFO Reset Flush (G2 ledger fix%') from
# 2026-03-31 00:00:00 to 2026-03-31 01:00:00 (create_date + accounting_date), i.e. AFTER the MOGEN_OB reseed pickings
# (00:55), so the SVL before the OB stays 0 (user rule 2026-11-05). Values, quantities, warehouses unchanged; remaining 0.
# Modes: check | dry (backup, update, post-checks, ROLLBACK) | apply (COMMIT)
# Rollback after apply: UPDATE stock_valuation_layer SET create_date='2026-03-31 00:00:00', accounting_date='2026-03-31 00:00:00'
#                         WHERE description LIKE 'Reverse FIFO Reset Flush (G2 ledger fix%';
set -euo pipefail
MODE="${1:-check}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply" >&2; exit 2;; esac
REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'
BODY=$(cat <<'SQLEOF'
CREATE TEMP TABLE g AS SELECT id, product_id, warehouse_id, quantity, value FROM stock_valuation_layer WHERE description LIKE 'Reverse FIFO Reset Flush (G2 ledger fix%';
CREATE TEMP TABLE before AS
SELECT g.product_id pid, g.warehouse_id wid,
 (SELECT round(sum(quantity),4) FROM stock_valuation_layer l WHERE l.product_id=g.product_id AND l.warehouse_id=g.warehouse_id) all_q,
 (SELECT round(sum(value)::numeric,2) FROM stock_valuation_layer l WHERE l.product_id=g.product_id AND l.warehouse_id=g.warehouse_id) all_v,
 (SELECT round(sum(quantity),4) FROM stock_valuation_layer l WHERE l.product_id=g.product_id AND l.warehouse_id=g.warehouse_id AND COALESCE(l.accounting_date,l.create_date)>='2026-03-30 17:00') win_q,
 (SELECT round(sum(quantity),4) FROM stock_valuation_layer l WHERE l.product_id=g.product_id AND l.warehouse_id=g.warehouse_id AND COALESCE(l.accounting_date,l.create_date)>='2026-03-30 17:00' AND COALESCE(l.accounting_date,l.create_date)<'2026-03-31 00:50') pre_ob_q
FROM (SELECT DISTINCT product_id, warehouse_id FROM g) g;
\echo '== preconditions (expect 14 layers all at 2026-03-31 00:00:00, remaining 0)'
SELECT count(*) layers, count(*) FILTER (WHERE l.accounting_date='2026-03-31 00:00:00' AND l.create_date='2026-03-31 00:00:00') at_0000, sum(abs(l.remaining_qty)) rq, round(sum(l.value),2) net FROM stock_valuation_layer l WHERE l.id IN (SELECT id FROM g);
DO $$ BEGIN
  IF (SELECT count(*) FROM g)<>14 OR (SELECT count(*) FROM stock_valuation_layer WHERE id IN (SELECT id FROM g) AND accounting_date='2026-03-31 00:00:00' AND create_date='2026-03-31 00:00:00')<>14 THEN RAISE EXCEPTION 'expected 14 G2 layers all at 2026-03-31 00:00:00'; END IF;
END $$;
\echo '== pre-OB window quantity per product/wh BEFORE (G2 layers inside it):'
SELECT pp.default_code, w.code, b.pre_ob_q FROM before b JOIN product_product pp ON pp.id=b.pid JOIN stock_warehouse w ON w.id=b.wid ORDER BY 1,2;
SQLEOF
)
WRITE=$(cat <<'SQLEOF'
UPDATE stock_valuation_layer SET create_date='2026-03-31 01:00:00', accounting_date='2026-03-31 01:00:00', write_date=now() AT TIME ZONE 'UTC' WHERE id IN (SELECT id FROM g);
\echo '== pre-OB window quantity per product/wh AFTER (expect 0 on every row)'
SELECT pp.default_code, w.code,
 (SELECT round(coalesce(sum(quantity),0),4) FROM stock_valuation_layer l WHERE l.product_id=b.pid AND l.warehouse_id=b.wid AND COALESCE(l.accounting_date,l.create_date)>='2026-03-30 17:00' AND COALESCE(l.accounting_date,l.create_date)<'2026-03-31 00:50') pre_ob_q_after
FROM before b JOIN product_product pp ON pp.id=b.pid JOIN stock_warehouse w ON w.id=b.wid ORDER BY 1,2;
DO $$
DECLARE bad int; pre int;
BEGIN
  SELECT count(*) INTO bad FROM before b WHERE
    (SELECT round(sum(quantity),4) FROM stock_valuation_layer l WHERE l.product_id=b.pid AND l.warehouse_id=b.wid) IS DISTINCT FROM b.all_q
    OR (SELECT round(sum(value)::numeric,2) FROM stock_valuation_layer l WHERE l.product_id=b.pid AND l.warehouse_id=b.wid) IS DISTINCT FROM b.all_v
    OR (SELECT round(sum(quantity),4) FROM stock_valuation_layer l WHERE l.product_id=b.pid AND l.warehouse_id=b.wid AND COALESCE(l.accounting_date,l.create_date)>='2026-03-30 17:00') IS DISTINCT FROM b.win_q;
  SELECT count(*) INTO pre FROM before b WHERE coalesce((SELECT sum(quantity) FROM stock_valuation_layer l WHERE l.product_id=b.pid AND l.warehouse_id=b.wid AND COALESCE(l.accounting_date,l.create_date)>='2026-03-30 17:00' AND COALESCE(l.accounting_date,l.create_date)<'2026-03-31 00:50'),0)<>0;
  IF bad<>0 THEN RAISE EXCEPTION 'all-time/window totals changed on % rows', bad; END IF;
  IF (SELECT count(*) FROM stock_valuation_layer WHERE id IN (SELECT id FROM g) AND accounting_date='2026-03-31 01:00:00' AND create_date='2026-03-31 01:00:00')<>14 THEN RAISE EXCEPTION 'update count wrong'; END IF;
  RAISE NOTICE 'post-check ok: 14 layers moved to 01:00, totals unchanged; rows with non-zero pre-OB quantity after: %', pre;
END $$;
SQLEOF
)
if [ "$MODE" = check ]; then
  { printf 'BEGIN;\n%s\nROLLBACK;\n' "$BODY"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q"; echo "== check ok"; exit 0
fi
COMMIT_OR_ROLLBACK=$([ "$MODE" = apply ] && echo COMMIT || echo ROLLBACK)
STAMP=$(date +%Y%m%d_%H%M%S)
echo ">>> backup stock_valuation_layer on mog-prod (~/db_backups/svl_G2redate_${STAMP}.dump)"
ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_valuation_layer MOG_LIVE -f ~/db_backups/svl_G2redate_${STAMP}.dump && ls -l ~/db_backups/svl_G2redate_${STAMP}.dump"
{ printf 'BEGIN;\n%s\n%s\n%s;\n' "$BODY" "$WRITE" "$COMMIT_OR_ROLLBACK"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q"
echo ">>> $MODE finished ($COMMIT_OR_ROLLBACK)"
