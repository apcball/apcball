from datetime import date, datetime, timedelta

import pytz

from odoo import Command, fields
from odoo.tests.common import TransactionCase

from odoo.addons.buz_production_planning.engine import scheduler
from odoo.addons.buz_production_planning.engine.mrp_netting import PlanData
from odoo.addons.buz_production_planning.models.res_config_settings import get_plan_config

MONDAY = date(2026, 11, 16)   # first bucket start used by all tests


class PlanCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Product = cls.env['product.product']
        cls.fg = cls._product('FG')
        cls.semi = cls._product('SEMI')
        cls.rm = cls._product('RM')

    @classmethod
    def _product(cls, name):
        return cls.Product.create({'name': 'TEST-%s' % name, 'detailed_type': 'product'})

    @classmethod
    def _bom(cls, product, lines, bom_type='normal', qty=1.0):
        return cls.env['mrp.bom'].create({
            'product_tmpl_id': product.product_tmpl_id.id,
            'product_id': product.id,
            'product_qty': qty,
            'type': bom_type,
            'bom_line_ids': [Command.create({'product_id': p.id, 'product_qty': q}) for p, q in lines],
        })

    @classmethod
    def _contact_vals(cls):
        # buz_partner_required_fields (installed on DEV/prod) demands a full contact.
        thailand = cls.env.ref('base.th')
        return {
            'street': '1 Test Rd', 'street2': 'Test Sub-district', 'city': 'Bangkok',
            'state_id': cls.env['res.country.state'].search(
                [('country_id', '=', thailand.id)], limit=1).id,
            'zip': '10110', 'country_id': thailand.id, 'phone': '021234567',
            'email': 'test-vendor@example.com',
        }

    @classmethod
    def _vendor(cls, name):
        return cls.env['res.partner'].create({'name': name, **cls._contact_vals()})

    def data(self, products, n=4, **kw):
        """PlanData without touching stock: callers pass plain dicts."""
        kw.setdefault('cfg', {'lead_make_days': 3.0, 'lead_buy_days': 7.0})
        return PlanData(self.env, MONDAY, n, kw.pop('today', MONDAY), products, **kw)

    @staticmethod
    def bk(mapping=None, n=4):
        """bk({1: 30}) -> [0, 30, 0, 0]"""
        out = [0.0] * n
        for i, q in (mapping or {}).items():
            out[i] = float(q)
        return out


def local(text):
    """'2026-11-16 08:00' in Asia/Bangkok -> naive UTC datetime."""
    tz = pytz.timezone('Asia/Bangkok')
    return tz.localize(datetime.strptime(text, '%Y-%m-%d %H:%M')).astimezone(pytz.utc).replace(tzinfo=None)


class SchedulingCommon(PlanCommon):
    """Calendar, workcenters, own warehouse/picking type and a plan limited to it."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.calendar = cls.env['resource.calendar'].create({
            'name': 'TEST 8-12 13-17 Mon-Fri', 'tz': 'Asia/Bangkok',
            'attendance_ids': [Command.create({
                'name': '%s %s' % (day, period), 'dayofweek': str(day),
                'hour_from': h_from, 'hour_to': h_to, 'day_period': period})
                for day in range(5)
                for period, h_from, h_to in (('morning', 8, 12), ('afternoon', 13, 17))],
        })
        cls.wc1 = cls._workcenter('TEST-WC1')
        cls.wc2 = cls._workcenter('TEST-WC2')
# Own warehouse + manufacturing type: the plan only sees test MOs, never real workorders.
        warehouse = cls.env['stock.warehouse'].create({'name': 'TEST SCHED WH', 'code': 'TSW'})
        cls.picking_type = warehouse.manu_type_id
        cls.cfg = get_plan_config(cls.env)
        cls.run_ = cls.env['buz.plan.run'].create({
            'state': 'computed', 'picking_type_ids': [Command.set(cls.picking_type.ids)]})
        cls.now = local('2026-11-16 08:00')      # Monday

    @classmethod
    def _workcenter(cls, name):
        return cls.env['mrp.workcenter'].create({
            'name': name, 'resource_calendar_id': cls.calendar.id, 'time_efficiency': 100})

    @classmethod
    def _mo(cls, name, ops, deadline=None, qty=1.0):
        """Confirmed MO whose BoM has one operation per (workcenter, minutes)."""
        product = cls._product(name)
        bom = cls.env['mrp.bom'].create({
            'product_tmpl_id': product.product_tmpl_id.id, 'product_id': product.id,
            'product_qty': 1.0, 'type': 'normal',
            'operation_ids': [Command.create({
                'name': 'op %s' % i, 'workcenter_id': wc.id, 'time_mode': 'manual',
                'time_cycle_manual': minutes, 'sequence': 10 * (i + 1)})
                for i, (wc, minutes) in enumerate(ops)],
        })
        vals = {'product_id': product.id, 'product_qty': qty, 'bom_id': bom.id,
                'picking_type_id': cls.picking_type.id}
        if deadline:
            vals['date_deadline'] = deadline
        mo = cls.env['mrp.production'].create(vals)
        mo.action_confirm()
        return mo

    def _schedule(self, now=None):
        return scheduler.run_schedule(self.run_, self.cfg, now or self.now)

    def _line(self, mo, index=0):
        return self.run_.schedule_line_ids.filtered(lambda l: l.production_id == mo).sorted(
            'sequence')[index]

    def _lines(self, *mos):
        return self.run_.schedule_line_ids.filtered(lambda l: l.production_id in sum(mos, mos[0].browse()))



class BlanketCommon(PlanCommon):
    """Plan, warehouse, vendors and helpers for blanket order tests."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.company = env.company
        cls.bo_type = env['purchase.requisition.type'].search(
            [('quantity_copy', '=', 'none')], limit=1) or env['purchase.requisition.type'].create({
                'name': 'TEST Blanket Order', 'quantity_copy': 'none', 'exclusive': 'multiple'})
        cls.warehouse = env['stock.warehouse'].create({'name': 'TEST BO WH', 'code': 'TBW'})
        cls.other_wh = env['stock.warehouse'].create({'name': 'TEST BO OTHER WH', 'code': 'TBO'})
        cls.vendor_a = cls._vendor('TEST BO Vendor A')
        cls.vendor_b = cls._vendor('TEST BO Vendor B')
        cls.p1, cls.p2, cls.p3, cls.p4 = (cls._product('BO%s' % i) for i in range(1, 5))
        cls.run_ = env['buz.plan.run'].create({
            'date_from': MONDAY, 'horizon_weeks': 4, 'state': 'computed',
            'warehouse_ids': [Command.set(cls.warehouse.ids)]})
        cls.analytic_plan = env['account.analytic.plan'].create({'name': 'TEST BO plan'})
        cls.analytic = env['account.analytic.account'].create(
            {'name': 'TEST BO account', 'plan_id': cls.analytic_plan.id})
        cls.dist = {str(cls.analytic.id): 100.0}

    # -- helpers --------------------------------------------------------
    def _sugg(self, product, qty=5.0, vendor=None, day=7, **kw):
        vals = {
            'run_id': self.run_.id, 'product_id': product.id, 'action': 'buy', 'qty': qty,
            'uom_id': product.uom_id.id, 'date_need': MONDAY + timedelta(days=day),
            'date_release': MONDAY + timedelta(days=day - 3), 'state': 'approved',
            'vendor_id': (vendor or self.vendor_a).id,
        }
        vals.update(kw)
        return self.env['buz.plan.suggestion'].create(vals)

    def _wizard(self, suggestions, buy_document='bo', run=None):
        run = run or self.run_
        return self.env['buz.plan.create.documents.wizard'].create({
            'run_id': run.id, 'buy_document': buy_document,
            'suggestion_ids': [Command.set(suggestions.ids)]})

    def _hand_bo(self, vendor, product, price=0.0, qty=10.0, **kw):
        vals = {
            'vendor_id': vendor.id, 'type_id': self.bo_type.id,
            'picking_type_id': self.warehouse.in_type_id.id,
            'line_ids': [Command.create({
                'product_id': product.id, 'product_qty': qty, 'price_unit': price,
                'product_uom_id': product.uom_id.id, **kw.pop('line', {})})],
        }
        vals.update(kw)
        return self.env['purchase.requisition'].create(vals)

    def _po(self, vendor, product, price, qty=1.0, state='purchase', requisition=None):
        return self.env['purchase.order'].create({
            'partner_id': vendor.id, 'state': state,
            'requisition_id': requisition.id if requisition else False,
            'picking_type_id': self.warehouse.in_type_id.id,
            'order_line': [Command.create({
                'product_id': product.id, 'name': product.name, 'product_qty': qty,
                'product_uom': product.uom_id.id, 'price_unit': price,
                'date_planned': fields.Datetime.now()})],
        })
