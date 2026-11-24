#!/usr/bin/env bash
# Reverse unbuild UB/2611004 (user request 2026-11-10): component moves 372654/5/6 go back to Production, finished product 372653 returns to RM01/QC.
# Unreserves BG-RT261100005 (move 340701) first (FG10 MO00002A0S10000 reserved 1.0 vs on hand 0.5).
# NOTE: buz_stock_freeze locks RM01/Stock until 2026-11-10 16:00 (stock count) - run only after the lock ends. Backup taken 2026-11-10: ~/db_backups/ub2611004_reverse_20261110_102151.dump (mog-prod).
# Modes: dry (execute, report, ROLLBACK) | apply (COMMIT). Take a pg_dump backup before apply (see header of the stamp file / ~/db_backups/ub2611004_reverse_*.dump).
set -euo pipefail
MODE="${1:-dry}"
case "$MODE" in dry|apply) ;; *) echo "usage: $0 dry|apply" >&2; exit 2;; esac
ssh mog-prod "cd /opt/instance1/odoo17 && source /opt/instance1/odoo17-venv/bin/activate && python3 odoo-bin shell -c /etc/instance1.conf -d MOG_LIVE --no-http 2>&1 << 'PYEOF' | grep -E '^(>|ERR)'
MODE = '$MODE'
env = env(context=dict(env.context, skip_warehouse_consistency_check=True))
M = env['stock.move']
try:
    ub = env['mrp.unbuild'].search([('name','=','UB/2611004')])
    assert len(ub)==1 and ub.state=='done'
    assert not M.search([('reference','like','UB/2611004 REV%')]), 'already reversed'
    orig = M.browse([372653,372654,372655,372656])
    assert all(m.reference=='UB/2611004' and m.state=='done' for m in orig)
    # 1. unreserve BG-RT261100005
    bg = env['stock.move.line'].browse(340701).move_id
    assert bg.reference=='BG-RT261100005', bg.reference
    print('> BG move', bg.reference, bg.state, 'reserved before', bg.move_line_ids.mapped('quantity'))
    bg._do_unreserve()
    print('> BG after', bg.state, bg.move_line_ids.mapped('quantity'))
    # 2. reverse moves
    new = M
    for m in orig:
        n = M.create({'name':'UB/2611004 REV', 'reference':'UB/2611004 REV', 'product_id':m.product_id.id,
            'product_uom':m.product_uom.id, 'product_uom_qty':m.product_uom_qty,
            'location_id':m.location_dest_id.id, 'location_dest_id':m.location_id.id,
            'company_id':m.company_id.id, 'origin':'UB/2611004 reverse'})
        n._action_confirm()
        n._action_assign()
        for l in n.move_line_ids: l.quantity = n.product_uom_qty
        n.picked = True
        new |= n
    print('> created', new.ids, [(x.product_id.default_code, x.state, x.location_id.complete_name, x.location_dest_id.complete_name, x.quantity) for x in new])
    new._action_done()
    for x in new:
        print('> done', x.id, x.state, x.product_id.default_code, [(s.id,s.quantity,s.value,s.remaining_qty) for s in x.stock_valuation_layer_ids])
    for o,x in zip(orig,new):
        ov = round(sum(o.stock_valuation_layer_ids.mapped('value')),2)
        svls = x.stock_valuation_layer_ids
        assert len(svls)==1, (x.id, len(svls))
        if abs(round(svls.value,2)+ov)>0.004:
            q = svls.quantity
            env.cr.execute('UPDATE stock_valuation_layer SET value=%s, unit_cost=%s WHERE id=%s', (-ov, (-ov/q) if q else 0, svls.id))
            svls.invalidate_recordset()
            print('> adjusted svl', svls.id, 'to', -ov)
    for o,x in zip(orig,new):
        print('> compare', o.product_id.default_code, 'orig value', sum(o.stock_valuation_layer_ids.mapped('value')), 'rev value', sum(x.stock_valuation_layer_ids.mapped('value')))
    for pid,loc in ((3791,'RM01/QC'),(7116,'FG10/Stock'),(6169,'RM01/Stock'),(4703,'RM01/Stock')):
        qs = env['stock.quant'].search([('product_id','=',pid),('location_id.complete_name','=',loc)])
        print('> quant', pid, loc, sum(qs.mapped('quantity')), sum(qs.mapped('reserved_quantity')))
    if MODE=='apply':
        env.cr.commit(); print('> COMMITTED')
    else:
        env.cr.rollback(); print('> ROLLED BACK (dry)')
except Exception as e:
    env.cr.rollback(); print('ERR', repr(e))
PYEOF
"
