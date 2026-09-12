"""Disposable browser fixtures; execute with Odoo shell, never import on install."""
import os
if env.cr.dbname != 'MOG_IT_TEST':
    raise RuntimeError('Browser fixtures require disposable MOG_IT_TEST')
if env['buz.it.config'].search_count([]):
    raise RuntimeError('Fixtures require a fresh database without IT configuration')
password = os.environ['IT_TEST_PASSWORD']
from odoo import fields
env.user.groups_id = [fields.Command.link(env.ref('buz_it_stock_mobile.group_it_manager').id)]
env['res.users'].browse(2).write({'password': password, 'groups_id': [fields.Command.link(env.ref('buz_it_stock_mobile.group_it_manager').id)]})
warehouse = env['stock.warehouse'].search([('company_id', '=', env.company.id)], limit=1)
config = env['buz.it.config'].create({'warehouse_id': warehouse.id, 'location_id': warehouse.lot_stock_id.id})
config.action_prepare_locations()
config.accounting_reviewed = True
department = env['hr.department'].create({'name': 'IT Department', 'company_id': env.company.id})
location = env['hr.work.location'].create({'name': 'สำนักงานใหญ่', 'company_id': env.company.id, 'address_id': env.company.partner_id.id})
env['hr.employee'].create({'name': 'Somchai Jaidee', 'department_id': department.id, 'work_location_id': location.id, 'company_id': env.company.id})
for name, category, qty, tracking in [('Logitech K120', 'keyboard', 18, 'none'), ('Logitech M100', 'mouse', 25, 'none'), ('HDMI Cable 2m', 'cable', 34, 'lot'), ('Monitor 24 inch', 'monitor', 6, 'serial'), ('USB-C Hub', 'adapter', 12, 'none'), ('Network Cable Cat6', 'cable', 40, 'none')]:
    product = env['product.product'].create({'name': name, 'detailed_type': 'product', 'it_issue_enabled': True, 'it_category_id': env.ref('buz_it_stock_mobile.category_' + category).id, 'tracking': tracking, 'standard_price': 450})
    if tracking == 'serial':
        for i in range(qty):
            lot = env['stock.lot'].create({'name': 'MON-%03d' % i, 'product_id': product.id, 'company_id': env.company.id})
            env['stock.quant']._update_available_quantity(product, config.location_id, 1, lot_id=lot)
    elif tracking == 'lot':
        lot = env['stock.lot'].create({'name': 'HDMI-2026-A', 'product_id': product.id, 'company_id': env.company.id})
        env['stock.quant']._update_available_quantity(product, config.location_id, qty, lot_id=lot)
    else:
        env['stock.quant']._update_available_quantity(product, config.location_id, qty)
env.cr.commit()
print('PREVIEW_FIXTURES_READY')
