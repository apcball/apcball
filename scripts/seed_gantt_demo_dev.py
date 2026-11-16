"""Seed demo data for the buz_production_planning Gantt. DEV ONLY.

Usage (from the repo root):
    ssh dev "docker exec -i odoo odoo shell -d MOG_DEV --no-http" < scripts/seed_gantt_demo_dev.py
Everything is named TEST-GANTT / lives in warehouse TGW. Remove with
scripts/cleanup_gantt_demo_dev.py.
"""
import random
from datetime import timedelta

from odoo import Command, fields
from odoo.addons.buz_production_planning.engine import scheduler
from odoo.addons.buz_production_planning.models.res_config_settings import get_plan_config

assert env.cr.dbname == 'MOG_DEV', "DEV only"
random.seed(7)
cal = env['resource.calendar'].search([], limit=1)
wh = env['stock.warehouse'].search([('code', '=', 'TGW')]) or env['stock.warehouse'].create(
    {'name': 'TEST-GANTT WH', 'code': 'TGW'})
pt = wh.manu_type_id
codes = ['PD1-91', 'PD1-92', 'PD1-93', 'PD2-91', 'PD2-92', 'PD2-93', 'PD2-94', 'PD2-95']
wcs = env['mrp.workcenter']
for code in codes:
    wcs |= env['mrp.workcenter'].create({
        'name': 'TEST-GANTT %s' % code, 'code': code, 'resource_calendar_id': cal.id, 'time_efficiency': 100})
now = fields.Datetime.now()
mos = env['mrp.production']
for i in range(40):
    product = env['product.product'].create({'name': 'TEST-GANTT-%02d' % i, 'detailed_type': 'product'})
    ops = random.sample(list(wcs), random.choice([2, 3]))
    bom = env['mrp.bom'].create({
        'product_tmpl_id': product.product_tmpl_id.id, 'product_id': product.id, 'product_qty': 1.0,
        'type': 'normal',
        'operation_ids': [Command.create({
            'name': 'Step %d %s' % (n + 1, wc.code), 'workcenter_id': wc.id, 'time_mode': 'manual',
            'time_cycle_manual': random.choice([30, 45, 60, 90, 120, 180]), 'sequence': 10 * (n + 1)})
            for n, wc in enumerate(ops)],
    })
    mo = env['mrp.production'].create({
        'product_id': product.id, 'product_qty': random.choice([1, 2, 3, 5]), 'bom_id': bom.id,
        'picking_type_id': pt.id, 'origin': 'GANTT-DEMO',
        'date_deadline': now + timedelta(days=random.choice([1, 2, 3, 4, 6, 8, 12, 15])),
    })
    mo.action_confirm()
    mos |= mo
running = mos[0].workorder_ids[:1]
running.write({'state': 'progress'})
run = env['buz.plan.run'].create({
    'state': 'computed', 'picking_type_ids': [Command.set(pt.ids)], 'warehouse_ids': [Command.set(wh.ids)]})
stats = scheduler.run_schedule(run, get_plan_config(env))
env.cr.commit()
print("SEEDED", run.name, run.id, stats)
