#!/usr/bin/env bash
# imex builds its legs from stock_move and falls back to the move HEADER locations when a move has no move line, so the
# tagged IMEX-REBASELINE moves created for group F (36) and group D (4) showed as fake In/Out rows and shifted Initial
# (user rule 2026-11-05/06: Initial/opening must come from MOGEN_OB only). Option 1: set product_qty / product_uom_qty /
# quantity of these 40 moves to 0. The tag (reference IMEX-REBASELINE-20260331 -> negative-balance guard skip) and the SVL
# layers (quantity/value) are NOT touched. Original original-10 and MT81 moves are left as they are.
# Modes: check | dry (backup, update, post-checks, ROLLBACK) | apply (COMMIT)
# Reverse after apply (restores the move qty from its layer):
#   UPDATE stock_move m SET product_qty=abs(l.quantity), product_uom_qty=abs(l.quantity), quantity=abs(l.quantity)
#     FROM stock_valuation_layer l WHERE l.stock_move_id=m.id AND (m.name LIKE 'groupF re-baseline%' OR m.name LIKE 'groupD re-baseline%');
set -euo pipefail
MODE="${1:-check}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply" >&2; exit 2;; esac
REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'
BODY=$(cat <<'SQLEOF'
\echo '== preconditions (expect 40 moves: 36 groupF + 4 groupD, each linked to exactly one layer, qty = abs(layer qty) > 0, reference IMEX-REBASELINE-20260331, no move lines)'
SELECT count(*) moves, count(*) FILTER (WHERE m.name LIKE 'groupF%') f, count(*) FILTER (WHERE m.name LIKE 'groupD%') d,
  count(*) FILTER (WHERE m.product_qty=abs(l.quantity) AND m.product_qty>0) qty_ok,
  count(*) FILTER (WHERE m.reference='IMEX-REBASELINE-20260331') ref_ok,
  count(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM stock_move_line x WHERE x.move_id=m.id)) no_lines
FROM stock_move m JOIN stock_valuation_layer l ON l.stock_move_id=m.id WHERE m.name LIKE 'groupF re-baseline%' OR m.name LIKE 'groupD re-baseline%';
DO $$ BEGIN
  IF (SELECT count(*) FROM stock_move m JOIN stock_valuation_layer l ON l.stock_move_id=m.id WHERE (m.name LIKE 'groupF re-baseline%' OR m.name LIKE 'groupD re-baseline%')
        AND m.product_qty=abs(l.quantity) AND m.product_qty>0 AND m.reference='IMEX-REBASELINE-20260331'
        AND NOT EXISTS (SELECT 1 FROM stock_move_line x WHERE x.move_id=m.id))<>40 THEN RAISE EXCEPTION 'expected 40 untouched tagged moves'; END IF;
END $$;
SQLEOF
)
WRITE=$(cat <<'SQLEOF'
CREATE TEMP TABLE svl_before AS SELECT count(*) c, round(sum(quantity),4) q, round(sum(value)::numeric,2) v FROM stock_valuation_layer WHERE description LIKE 'Re-baseline adjustment 2026-03-31 - group%';
UPDATE stock_move SET product_qty=0, product_uom_qty=0, quantity=0, write_date=now() AT TIME ZONE 'UTC' WHERE name LIKE 'groupF re-baseline%' OR name LIKE 'groupD re-baseline%';
DO $$ DECLARE n int; c2 int; q2 numeric; v2 numeric;
BEGIN
  SELECT count(*) INTO n FROM stock_move WHERE (name LIKE 'groupF re-baseline%' OR name LIKE 'groupD re-baseline%') AND product_qty=0 AND product_uom_qty=0 AND quantity=0 AND reference='IMEX-REBASELINE-20260331' AND state='done';
  SELECT count(*), round(sum(quantity),4), round(sum(value)::numeric,2) INTO c2, q2, v2 FROM stock_valuation_layer WHERE description LIKE 'Re-baseline adjustment 2026-03-31 - group%';
  IF n<>40 OR c2<>(SELECT c FROM svl_before) OR q2 IS DISTINCT FROM (SELECT q FROM svl_before) OR v2 IS DISTINCT FROM (SELECT v FROM svl_before) THEN RAISE EXCEPTION 'post-check failed: zeroed %, svl % / % / %', n, c2, q2, v2; END IF;
  RAISE NOTICE 'post-check ok: 40 moves zeroed, tag kept, SVL layers unchanged (% layers)', c2;
END $$;
SQLEOF
)
if [ "$MODE" = check ]; then
  { printf 'BEGIN;\n%s\nROLLBACK;\n' "$BODY"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q"; echo "== check ok"; exit 0
fi
COMMIT_OR_ROLLBACK=$([ "$MODE" = apply ] && echo COMMIT || echo ROLLBACK)
STAMP=$(date +%Y%m%d_%H%M%S)
echo ">>> backup stock_move on mog-prod (~/db_backups/imex_zero_${STAMP}.dump)"
ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_move MOG_LIVE -f ~/db_backups/imex_zero_${STAMP}.dump && ls -l ~/db_backups/imex_zero_${STAMP}.dump"
{ printf 'BEGIN;\n%s\n%s\n%s;\n' "$BODY" "$WRITE" "$COMMIT_OR_ROLLBACK"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q"
echo ">>> $MODE finished ($COMMIT_OR_ROLLBACK)"
