#!/usr/bin/env bash
# PREVIEW ONLY of stock_fifo_by_warehouse_recal for FCA0006100 (product 1408) @ FG10/FG30/FG40/RM01/RM11 (wh 1,8,9,13,16) on MOG_LIVE.
# Why: FIFO queue sum(remaining_qty) FG10 61 vs 2, FG30 36 vs 57, FG40 5 vs 3, RM01 3 vs 2, RM11 1 vs 4 (SVL ledger/quant are right since the G2 fix).
# Runs the wizard's action_preview() (replay, no write to stock_valuation_layer) inside an odoo shell and
# ends with env.cr.rollback(), so the wizard + lines it creates are NOT kept. Nothing is applied.
# Run it yourself (classifier blocks assistant-run odoo shell on prod):
#     ! bash scripts/fifo_recal_preview_FCA0006100.sh [reordered]
# Arg `reordered` also sets include_reordered=True (only if the first run says the product was skipped
# because its queue was reordered by a backdating tool).
set -euo pipefail
REORD="False"; [ "${1:-}" = "reordered" ] && REORD="True"
PY=$(cat <<PYEOF
w = env['fifo.recalculation.wizard'].create({
    'warehouse_ids': [(6, 0, [1, 8, 9, 13, 16])], 'product_ids': [(6, 0, [1408])],
    'repair_remaining': True, 'fix_null_remaining': False, 'fix_negative_remaining': False,
    'fix_excess_remaining': False, 'report_value_residual': False,
    'dry_run': True, 'include_reordered': $REORD})
w.action_preview()
print('=====LOG=====')
print(w.log_text)
print('=====SUMMARY=====')
print('state', w.state, '| block_reason', w.block_reason, '| scanned', w.layers_scanned, '| changed', w.layers_changed, '| value_delta', w.value_delta, '| pairs_blocked', w.pairs_blocked)
for l in w.line_ids:
    print('LINE', l.product_id.default_code, l.warehouse_id.code, 'qty', l.qty_before, '->', l.qty_after, 'value', l.value_before, '->', l.value_after, 'layers', l.layer_change_count, 'reordered', l.reordered_layers, 'shortage', l.shortage_qty, 'skip', l.skip_reason)
env.cr.rollback()
print('=====ROLLED BACK (nothing kept)=====')
PYEOF
)
printf '%s\n' "$PY" | ssh mog-prod "cd /opt/instance1/odoo17 && source /opt/instance1/odoo17-venv/bin/activate && python3 odoo-bin shell -c /etc/instance1.conf -d MOG_LIVE --no-http --logfile=/dev/null 2>&1" | sed -n '/=====LOG=====/,$p'
