#!/usr/bin/env bash
# Preview-only FIFO recal (stock_fifo_by_warehouse_recal wizard) for ACS0021100 @ NC (wh 9) on MOG_LIVE.
# Nothing is committed: env.cr.rollback() at the end (wizard record is transient and also rolled back).
# Usage: recal_preview_ACS0021100_NC.sh [reordered]   # 'reordered' -> include_reordered=True
set -euo pipefail
REORD=$([ "${1:-}" = reordered ] && echo True || echo False)
ssh mog-prod "cd /opt/instance1/odoo17 && source /opt/instance1/odoo17-venv/bin/activate && python3 odoo-bin shell -c /etc/instance1.conf -d MOG_LIVE --no-http 2>&1 << 'PYEOF'
pid = env['product.product'].search([('default_code','=','ACS0021100')]).id
w = env['fifo.recalculation.wizard'].create({
  'warehouse_ids': [(6,0,[9])], 'product_ids': [(6,0,[pid])],
  'repair_remaining': True, 'fix_null_remaining': False, 'fix_negative_remaining': False,
  'fix_excess_remaining': False, 'report_value_residual': True,
  'dry_run': True, 'include_reordered': $REORD,
})
print('MODULE_VERSION', env['ir.module.module'].search([('name','=','stock_fifo_by_warehouse_recal')]).latest_version)
w.action_preview()
print('=====LOG'); print(w.log_text)
print('=====STATE', w.state, 'block:', w.block_reason, 'scanned', w.layers_scanned, 'changed', w.layers_changed, 'value_delta', w.value_delta, 'blocked_pairs', w.pairs_blocked, 'cogs_mismatch', w.cogs_mismatch_count, w.cogs_mismatch_value, 'residual', w.residual_pair_count, w.residual_value)
for l in w.line_ids:
    print('LINE', l.product_id.default_code, l.warehouse_id.name, 'qty', l.qty_before, '->', l.qty_after, 'val', l.value_before, '->', l.value_after, 'fix', l.layer_change_count, 'short', l.shortage_qty, 'reordered', l.reordered_layers, 'skip', l.skip_reason)
for c in w.backup_id: print('BACKUP', c)
env.cr.rollback()
print('ROLLED BACK')
PYEOF
"
