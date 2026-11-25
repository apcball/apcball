#!/usr/bin/env bash
# Frees just enough RESERVED stock at the source location of the 7 mirror pairs that fix_quant_shift_pairs.sh skipped ("source reserved").
# For each (product, source location, qty to move) it unreserves the SMALLEST set of open moves (not done/cancel/draft, not picked) whose
# reservations cover the shortage: the smallest single move >= shortage, else the largest moves first. Uses the ORM (stock.move._do_unreserve),
# so the pickings / MOs go back to "waiting/confirmed" and can be re-assigned afterwards (Check Availability / auto assign).
# Run it yourself (classifier blocks assistant-run odoo shell on prod):
#     ! bash scripts/unreserve_for_quantshift.sh            # PLAN ONLY: prints what it would unreserve, then rolls back
#     ! bash scripts/unreserve_for_quantshift.sh apply      # really unreserves (commits)
# After apply run:  bash scripts/fix_quant_shift_pairs.sh dry 301010008,406010069,409110001,409250055,FCA0006100,FCA0045100,FU0033FC1560
set -euo pipefail
MODE="${1:-plan}"
case "$MODE" in plan|apply) ;; *) echo "usage: $0 [plan|apply]" >&2; exit 2;; esac
COMMIT="False"; [ "$MODE" = apply ] && COMMIT="True"
PY=$(cat <<PYEOF
targets = [('301010008', 92, 40.0), ('406010069', 92, 200.0), ('409110001', 92, 4.0), ('409250055', 92, 160.0),
           ('FCA0006100', 8, 1.0), ('FCA0045100', 8, 1.0), ('FU0033FC1560', 8, 1.0)]
commit = $COMMIT
for code, loc, n in targets:
    prod = env['product.product'].search([('default_code', '=', code)], limit=1)
    quant = env['stock.quant'].search([('product_id', '=', prod.id), ('location_id', '=', loc)])
    free = sum(quant.mapped('quantity')) - sum(quant.mapped('reserved_quantity'))
    need = n - free
    print('==', code, 'loc', loc, 'quantity', sum(quant.mapped('quantity')), 'reserved', sum(quant.mapped('reserved_quantity')), 'free', free, 'move', n, 'need to free', need)
    if need <= 0:
        print('   nothing to unreserve'); continue
    lines = env['stock.move.line'].search([('product_id', '=', prod.id), ('location_id', '=', loc), ('state', 'not in', ('done', 'cancel', 'draft')), ('quantity', '>', 0), ('picked', '=', False)])
    by_move = {}
    for l in lines:
        by_move.setdefault(l.move_id.id, 0.0)
        by_move[l.move_id.id] += l.quantity
    cands = sorted(by_move.items(), key=lambda kv: kv[1])
    chosen = [kv for kv in cands if kv[1] >= need][:1]
    if not chosen:
        chosen, acc = [], 0.0
        for kv in sorted(cands, key=lambda kv: -kv[1]):
            chosen.append(kv); acc += kv[1]
            if acc >= need: break
    moves = env['stock.move'].browse([m for m, q in chosen])
    for m in moves:
        print('   unreserve', m.reference or m.picking_id.name or m.raw_material_production_id.name, 'state', m.state, 'reserved', by_move[m.id])
    if sum(q for m, q in chosen) < need:
        print('   !! reservations (not picked) cover only', sum(q for m, q in chosen), '< need', need, '(some lines are picked / other states)')
    moves._do_unreserve()
    quant.invalidate_recordset()
    print('   after: quantity', sum(quant.mapped('quantity')), 'reserved', sum(quant.mapped('reserved_quantity')))
if commit:
    env.cr.commit(); print('=====COMMITTED=====')
else:
    env.cr.rollback(); print('=====PLAN ONLY, ROLLED BACK=====')
PYEOF
)
printf '%s\n' "$PY" | ssh mog-prod "cd /opt/instance1/odoo17 && source /opt/instance1/odoo17-venv/bin/activate && python3 odoo-bin shell -c /etc/instance1.conf -d MOG_LIVE --no-http --logfile=/dev/null 2>&1" | grep -v "^profiling"
