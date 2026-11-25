"""Remove the data created by seed_gantt_demo_dev.py. DEV ONLY."""
assert env.cr.dbname == 'MOG_DEV', "DEV only"
wh = env['stock.warehouse'].search([('code', '=', 'TGW')])
runs = env['buz.plan.run'].search([('picking_type_ids', 'in', wh.manu_type_id.ids)])
runs.unlink()
mos = env['mrp.production'].search([('picking_type_id', '=', wh.manu_type_id.id)])
for mo in mos:
    if mo.state not in ('cancel', 'draft'):
        mo.workorder_ids.write({'state': 'cancel'})
        mo.action_cancel()
mos.unlink()
products = env['product.product'].search([('name', '=like', 'TEST-GANTT-%')])
env['mrp.bom'].search([('product_id', 'in', products.ids)]).unlink()
products.unlink()
env['mrp.workcenter'].search([('name', '=like', 'TEST-GANTT %')]).unlink()
env.cr.commit()
print("CLEANED")
