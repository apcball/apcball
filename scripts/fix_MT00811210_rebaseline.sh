#!/usr/bin/env bash
# Re-apply the FIFO-report re-baseline for MT00811210 (product 3882, MT81) @ FG10 (wh 1) on MOG_LIVE.
#
# Today FG10: quant 65 == all-time SVL 65 / 103,350.00, but the report window (acct >= 2026-03-30 17:00 UTC,
# what stock_fifo_valuation_report sums) is 85 / 135,150.00 (over-flush by the 2026-03-30 "Product Quantity
# Updated" -93 layer 115786, reseeded only 21 after the cut-off). The old fix (SVL 265525 / move 332730) was removed.
#
# Adds, like the other 10 IMEX-REBASELINE products (clone of MA662B101's move 332738 / SVL 265529):
#   * one stock_move  ref IMEX-REBASELINE-20260331, state done, FG10/Stock -> Inventory adjustment, qty 20,
#     date 2026-03-31 07:00, NO move line (imex / stock card unaffected; the move only tags the layer)
#   * one SVL layer   FG10 qty -20 / value -31,800.00 @1,590, remaining 0, accounting_date 2026-03-31 00:00
# Tagging the layer with that reference makes the negative-balance guard (commit 1b955289, live) skip it,
# so deliveries at FG10 are not blocked by the all-time ledger (45) being below quant (65).
# Effect: report window 85/135,150.00 -> 65/103,350.00 (== quant, == all-time before the layer).
# Report value drops 31,800.00 -> accounting must approve. Quant, FIFO queue, journal entries untouched.
#
# Modes (first arg): check (read-only) | dry (backup, insert + post-checks, ROLLBACK) | apply (COMMIT).
# Rollback after apply: DELETE FROM stock_valuation_layer WHERE description LIKE 'Re-baseline adjustment 2026-03-31%MT00811210%'
#                       ; DELETE FROM stock_move WHERE reference='IMEX-REBASELINE-20260331' AND product_id=3882;
set -euo pipefail
MODE="${1:-check}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply" >&2; exit 2;; esac

REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'

read -r -d '' PRE <<'SQLEOF' || true
\echo '== FG10 MT00811210 (expect all-time 65 / 103350.00, window 85 / 135150.00, quant 65, queue 65, 0 rebaseline moves)'
SELECT sum(quantity) all_q, round(sum(value),2) all_v,
  sum(quantity) FILTER (WHERE COALESCE(accounting_date,create_date)>='2026-03-30 17:00') win_q,
  round(sum(value) FILTER (WHERE COALESCE(accounting_date,create_date)>='2026-03-30 17:00'),2) win_v,
  sum(remaining_qty) queue,
  (SELECT sum(q.quantity) FROM stock_quant q JOIN stock_location sl ON sl.id=q.location_id WHERE q.product_id=3882 AND sl.warehouse_id=1 AND sl.usage IN ('internal','transit')) quant,
  (SELECT count(*) FROM stock_move WHERE product_id=3882 AND reference LIKE 'IMEX-REBASELINE%') rebase_moves
FROM stock_valuation_layer WHERE product_id=3882 AND warehouse_id=1;
SQLEOF

if [ "$MODE" = check ]; then
  printf '%s\n' "$PRE" | ssh mog-prod "$REMOTE_ENV; PGOPTIONS='-c default_transaction_read_only=on' psql -h localhost -U odoo MOG_LIVE -q"
  echo "== proposed (not written): stock_move IMEX-REBASELINE-20260331 qty 20 + SVL FG10 -20 / -31800.00 acct 2026-03-31 00:00"
  exit 0
fi

COMMIT_OR_ROLLBACK=$([ "$MODE" = apply ] && echo COMMIT || echo ROLLBACK)
STAMP=$(date +%Y%m%d_%H%M%S)
echo ">>> backup stock_valuation_layer + stock_move on mog-prod (~/db_backups/mt81_rebase_${STAMP}.dump)"
ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_valuation_layer -t stock_move MOG_LIVE -f ~/db_backups/mt81_rebase_${STAMP}.dump && ls -l ~/db_backups/mt81_rebase_${STAMP}.dump"

ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q" <<SQL
BEGIN;
$PRE
DO \$\$
DECLARE aq numeric; av numeric; wq numeric; wv numeric; qq numeric; rm int; qu numeric;
BEGIN
  SELECT sum(quantity), round(sum(value),2),
         sum(quantity) FILTER (WHERE COALESCE(accounting_date,create_date)>='2026-03-30 17:00'),
         round(sum(value) FILTER (WHERE COALESCE(accounting_date,create_date)>='2026-03-30 17:00'),2), sum(remaining_qty)
    INTO aq, av, wq, wv, qu FROM stock_valuation_layer WHERE product_id=3882 AND warehouse_id=1;
  SELECT sum(q.quantity) INTO qq FROM stock_quant q JOIN stock_location sl ON sl.id=q.location_id WHERE q.product_id=3882 AND sl.warehouse_id=1 AND sl.usage IN ('internal','transit');
  SELECT count(*) INTO rm FROM stock_move WHERE product_id=3882 AND reference LIKE 'IMEX-REBASELINE%';
  IF aq<>65 OR av<>103350.00 OR wq<>85 OR wv<>135150.00 OR qq<>65 OR qu<>65 OR rm<>0 THEN
    RAISE EXCEPTION 'precondition failed: all %/% window %/% quant % queue % rebase moves %', aq, av, wq, wv, qq, qu, rm;
  END IF;
END \$\$;

CREATE TEMP TABLE m AS SELECT * FROM stock_move WHERE id=332738;
UPDATE m SET id = nextval(pg_get_serial_sequence('stock_move','id')), product_id = 3882,
  name = 'MT00811210 re-baseline adj (report only) -20 @2026-03-31; re-applied 2026-11-05; pairs one SVL; no move line',
  product_qty = 20, product_uom_qty = 20, quantity = 20, weight = coalesce((SELECT weight FROM product_product WHERE id=3882),0) * 20,
  backdate_remark = 'rebaseline re-apply 2026-11-05', create_date = now() AT TIME ZONE 'UTC', write_date = now() AT TIME ZONE 'UTC';
INSERT INTO stock_move SELECT * FROM m;

CREATE TEMP TABLE l AS SELECT * FROM stock_valuation_layer WHERE id=265529;
UPDATE l SET id = nextval(pg_get_serial_sequence('stock_valuation_layer','id')), product_id = 3882,
  categ_id = (SELECT t.categ_id FROM product_product p JOIN product_template t ON t.id=p.product_tmpl_id WHERE p.id=3882),
  stock_move_id = (SELECT id FROM m), description = 'Re-baseline adjustment 2026-03-31 - MT00811210 pre-cutoff FIFO-reset residue -20 (re-applied 2026-11-05)',
  quantity = -20, unit_cost = 1590, value = -31800.00, remaining_qty = 0, remaining_value = 0,
  create_date = now() AT TIME ZONE 'UTC', write_date = now() AT TIME ZONE 'UTC';
INSERT INTO stock_valuation_layer SELECT * FROM l;

DO \$\$
DECLARE aq numeric; wq numeric; wv numeric; gq numeric; qu numeric; nm int; nl int;
BEGIN
  SELECT sum(quantity), sum(quantity) FILTER (WHERE COALESCE(accounting_date,create_date)>='2026-03-30 17:00'),
         round(sum(value) FILTER (WHERE COALESCE(accounting_date,create_date)>='2026-03-30 17:00'),2), sum(remaining_qty)
    INTO aq, wq, wv, qu FROM stock_valuation_layer WHERE product_id=3882 AND warehouse_id=1;
  SELECT COALESCE(SUM(svl.quantity),0) INTO gq FROM stock_valuation_layer svl LEFT JOIN stock_move sm ON sm.id=svl.stock_move_id
    WHERE svl.product_id=3882 AND svl.warehouse_id=1 AND COALESCE(sm.reference,'') NOT LIKE 'IMEX-REBASELINE%';
  SELECT count(*) INTO nm FROM stock_move WHERE product_id=3882 AND reference='IMEX-REBASELINE-20260331';
  SELECT count(*) INTO nl FROM stock_valuation_layer WHERE product_id=3882 AND description LIKE 'Re-baseline adjustment 2026-03-31 - MT00811210%';
  IF wq<>65 OR wv<>103350.00 OR aq<>45 OR gq<>65 OR qu<>65 OR nm<>1 OR nl<>1 THEN
    RAISE EXCEPTION 'post-check failed: window %/% all-time % guard-sum % queue % moves % layers %', wq, wv, aq, gq, qu, nm, nl;
  END IF;
  RAISE NOTICE 'post-check ok: window % / % (== quant 65), all-time %, guard sum % (== quant), queue %', wq, wv, aq, gq, qu;
END \$\$;
$COMMIT_OR_ROLLBACK;
SQL
echo ">>> $MODE finished ($COMMIT_OR_ROLLBACK)"
