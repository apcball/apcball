from datetime import date, timedelta
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import tagged

from odoo.addons.buz_production_planning.engine.mrp_netting import (
    MAX_DEPTH, bucket_index, forecast_window, round_up_qty, solve)

from .common import MONDAY, PlanCommon


@tagged('post_install', '-at_install')
class TestNettingHelpers(PlanCommon):

    def test_round_up_qty(self):
        self.assertEqual(round_up_qty(0), 0.0)
        self.assertEqual(round_up_qty(20, min_batch=50), 50)
        self.assertEqual(round_up_qty(20, multiple=12), 24)
        self.assertEqual(round_up_qty(20, min_batch=30, multiple=12), 36)
        self.assertEqual(round_up_qty(24, multiple=12), 24)
        self.assertEqual(round_up_qty(0.0833, rounding=1.0), 1.0, "fractions round up to the UoM")
        self.assertEqual(round_up_qty(2.0, rounding=1.0), 2.0)

    def test_bucket_index(self):
        self.assertEqual(bucket_index(MONDAY, MONDAY, 4), 0)
        self.assertEqual(bucket_index(MONDAY + timedelta(days=6), MONDAY, 4), 0)
        self.assertEqual(bucket_index(MONDAY + timedelta(days=7), MONDAY, 4), 1)
        self.assertEqual(bucket_index(MONDAY - timedelta(days=60), MONDAY, 4), 0, "overdue → first bucket")
        self.assertIsNone(bucket_index(MONDAY + timedelta(days=28), MONDAY, 4), "beyond horizon")

    def test_forecast_window_respects_cutoff(self):
        cutoff = date(2026, 4, 1)
        start, end = forecast_window(date(2026, 4, 29), 12, cutoff)
        self.assertEqual(start, cutoff, "never earlier than the cut-off")
        self.assertEqual(end, date(2026, 4, 29))
        start, _end = forecast_window(date(2026, 11, 16), 12, cutoff)
        self.assertEqual(start, date(2026, 11, 16) - timedelta(weeks=12))


@tagged('post_install', '-at_install')
class TestNetting(PlanCommon):

    def _solve(self, products, **kw):
        return solve(self.data(products, **kw))

    def test_onhand_enough_no_suggestion(self):
        data = dict(delivery={self.fg.id: self.bk({1: 30})}, onhand={self.fg.id: 30})
        res = self._solve(self.fg, **data)
        self.assertFalse(res.suggestions)

    def test_shortage_qty_and_dates(self):
        res = self._solve(self.fg, delivery={self.fg.id: self.bk({1: 30})}, onhand={self.fg.id: 10})
        self.assertEqual(len(res.suggestions), 1)
        s = res.suggestions[0]
        self.assertEqual(s['qty'], 20)
        self.assertEqual(s['date_need'], MONDAY + timedelta(days=7))
        self.assertEqual(s['shortage_qty'], 20)
        self.assertEqual(s['onhand_qty'], 10)

    def test_min_batch_and_multiple(self):
        params = {self.fg.id: {'min_batch_qty': 30, 'batch_multiple': 12}}
        res = self._solve(self.fg, params=params, delivery={self.fg.id: self.bk({1: 20})})
        self.assertEqual(res.suggestions[0]['qty'], 36)

    def test_safety_stock(self):
        params = {self.fg.id: {'safety_stock': 15}}
        res = self._solve(self.fg, params=params, onhand={self.fg.id: 10})
        self.assertEqual(len(res.suggestions), 1)
        self.assertEqual(res.suggestions[0]['qty'], 5)
        self.assertEqual(res.suggestions[0]['date_need'], MONDAY)

    def test_scheduled_receipt_reduces_need(self):
        res = self._solve(
            self.fg, delivery={self.fg.id: self.bk({1: 30})}, receipts={self.fg.id: self.bk({0: 30})})
        self.assertFalse(res.suggestions)
        res = self._solve(
            self.fg, delivery={self.fg.id: self.bk({1: 30})}, receipts={self.fg.id: self.bk({0: 10})})
        self.assertEqual(res.suggestions[0]['qty'], 20)

    def test_projection_carries_over_buckets(self):
        """A suggestion is added back to the projection: no repeat shortage."""
        res = self._solve(self.fg, delivery={self.fg.id: self.bk({0: 10, 1: 5})}, onhand={self.fg.id: 0})
        self.assertEqual([s['qty'] for s in res.suggestions], [10, 5])

    def test_late_release_moves_to_today(self):
        params = {self.fg.id: {'lead_make_days': 14, 'supply_method': 'buy', 'lead_buy_days': 14}}
        res = self._solve(self.fg, params=params, delivery={self.fg.id: self.bk({1: 5})})
        s = res.suggestions[0]
        self.assertEqual(s['date_release'], MONDAY)
        self.assertTrue(s['is_late'])
        params = {self.fg.id: {'supply_method': 'buy', 'lead_buy_days': 2}}
        res = self._solve(self.fg, params=params, delivery={self.fg.id: self.bk({2: 5})})
        s = res.suggestions[0]
        self.assertEqual(s['date_release'], MONDAY + timedelta(days=14 - 2))
        self.assertFalse(s['is_late'])

    def test_forecast_is_max_not_sum(self):
        res = self._solve(
            self.fg, n=1, delivery={self.fg.id: self.bk({0: 30}, 1)}, forecast_avg={self.fg.id: 50.0})
        self.assertEqual(res.suggestions[0]['qty'], 50, "forecast absorbs the open orders")
        by_source = {d['source']: d['qty'] for d in res.demand}
        self.assertEqual(by_source, {'delivery': 30, 'forecast': 20})

    def test_forecast_below_delivery_adds_nothing(self):
        res = self._solve(
            self.fg, n=1, delivery={self.fg.id: self.bk({0: 80}, 1)}, forecast_avg={self.fg.id: 50.0})
        self.assertEqual(res.suggestions[0]['qty'], 80)

    def test_manual_forecast_wins(self):
        res = self._solve(
            self.fg, n=1, forecast_avg={self.fg.id: 50.0}, manual={(self.fg.id, 0): 5.0})
        self.assertEqual(res.suggestions[0]['qty'], 5)

    def test_manual_forecast_is_max_with_delivery(self):
        """A manual forecast replaces the average: it also absorbs open orders, never adds to them."""
        res = self._solve(
            self.fg, n=1, delivery={self.fg.id: self.bk({0: 30}, 1)}, manual={(self.fg.id, 0): 50.0})
        self.assertEqual(res.suggestions[0]['qty'], 50)
        res = self._solve(
            self.fg, n=1, delivery={self.fg.id: self.bk({0: 80}, 1)}, manual={(self.fg.id, 0): 50.0})
        self.assertEqual(res.suggestions[0]['qty'], 80)

    def test_vendor_found_below_minimum_order_qty(self):
        """A shortage under the vendor's minimum quantity still names that vendor."""
        vendor = self._vendor('TEST MOQ Vendor')
        self.env['product.supplierinfo'].create({
            'partner_id': vendor.id, 'product_tmpl_id': self.rm.product_tmpl_id.id,
            'min_qty': 100, 'delay': 10})
        res = self._solve(self.rm, delivery={self.rm.id: self.bk({3: 5})})
        s = res.suggestions[0]
        self.assertEqual((s['action'], s['vendor_id']), ('buy', vendor.id))
        self.assertEqual(s['date_release'], MONDAY + timedelta(days=21 - 10), "vendor delay used")
        self.assertFalse(res.warnings)

    def test_vendor_delay_of_one_day_falls_back_to_default(self):
        """Master data delay 0/1 is placeholder data on prod: use the Settings default."""
        vendor = self._vendor('TEST Delay Vendor')
        self.env['product.supplierinfo'].create({
            'partner_id': vendor.id, 'product_tmpl_id': self.rm.product_tmpl_id.id, 'delay': 1})
        res = self._solve(self.rm, delivery={self.rm.id: self.bk({2: 5})})
        self.assertEqual(res.suggestions[0]['date_release'], MONDAY + timedelta(days=14 - 7))

    def test_no_forecast_when_method_none(self):
        params = {self.fg.id: {'forecast_method': 'none'}}
        res = self._solve(self.fg, n=1, params=params, forecast_avg={self.fg.id: 50.0})
        self.assertFalse(res.suggestions)

    def test_two_level_bom_with_pegging(self):
        fg_bom = self._bom(self.fg, [(self.semi, 2)])
        semi_bom = self._bom(self.semi, [(self.rm, 3)])
        res = self._solve(
            self.fg | self.semi | self.rm, boms={self.fg.id: fg_bom, self.semi.id: semi_bom},
            delivery={self.fg.id: self.bk({1: 10})})
        by_product = {s['product_id']: s for s in res.suggestions}
        self.assertEqual(set(by_product), {self.fg.id, self.semi.id, self.rm.id})
        fg_s, semi_s, rm_s = (by_product[p.id] for p in (self.fg, self.semi, self.rm))
        self.assertEqual((fg_s['action'], fg_s['qty'], fg_s['level']), ('make', 10, 0))
        self.assertEqual((semi_s['action'], semi_s['qty'], semi_s['level']), ('make', 20, 1))
        self.assertEqual((rm_s['action'], rm_s['qty'], rm_s['level']), ('buy', 60, 2))
        self.assertEqual(semi_s['parent_key'], fg_s['key'])
        self.assertEqual(rm_s['parent_key'], semi_s['key'])
        self.assertFalse(fg_s['parent_key'])
        order = [s['product_id'] for s in res.suggestions]
        self.assertLess(order.index(self.fg.id), order.index(self.semi.id), "parents first")

    def test_component_needed_at_two_levels_is_netted_once(self):
        """RM used by FG directly and through SEMI sits at the deepest level."""
        fg_bom = self._bom(self.fg, [(self.semi, 1), (self.rm, 1)])
        semi_bom = self._bom(self.semi, [(self.rm, 1)])
        res = self._solve(
            self.fg | self.semi | self.rm, boms={self.fg.id: fg_bom, self.semi.id: semi_bom},
            delivery={self.fg.id: self.bk({1: 10})})
        rm = [s for s in res.suggestions if s['product_id'] == self.rm.id]
        self.assertEqual(len(rm), 1)
        self.assertEqual(rm[0]['qty'], 20)
        self.assertEqual(rm[0]['level'], 2)

    def test_phantom_is_exploded_through(self):
        fg_bom = self._bom(self.fg, [(self.semi, 2)])
        phantom = self._bom(self.semi, [(self.rm, 3)], bom_type='phantom')
        self.assertTrue(phantom)
        res = self._solve(
            self.fg | self.rm, boms={self.fg.id: fg_bom}, delivery={self.fg.id: self.bk({1: 10})})
        rm = [s for s in res.suggestions if s['product_id'] == self.rm.id]
        self.assertEqual(rm[0]['qty'], 60)
        self.assertNotIn(self.semi.id, [s['product_id'] for s in res.suggestions])

    def test_bom_loop_raises(self):
        """Odoo refuses to create a BoM cycle, so feed the guard a looping graph."""
        fg_bom = self._bom(self.fg, [(self.semi, 1)])
        semi_bom = self._bom(self.semi, [(self.rm, 1)])
        looping = {self.fg.id: {self.semi.id}, self.semi.id: {self.fg.id}}
        with patch('odoo.addons.buz_production_planning.engine.mrp_netting._children',
                   return_value=looping):
            with self.assertRaises(UserError) as cm:
                self._solve(
                    self.fg | self.semi, boms={self.fg.id: fg_bom, self.semi.id: semi_bom},
                    delivery={self.fg.id: self.bk({1: 10})})
        self.assertIn('TEST-FG', str(cm.exception))
        self.assertIn('TEST-SEMI', str(cm.exception))

    def test_bom_too_deep_raises(self):
        chain = [self._product('L%s' % i) for i in range(MAX_DEPTH + 2)]
        graph = {a.id: {b.id} for a, b in zip(chain, chain[1:])}
        recordset = chain[0]
        for p in chain[1:]:
            recordset |= p
        with patch('odoo.addons.buz_production_planning.engine.mrp_netting._children',
                   return_value=graph):
            with self.assertRaises(UserError):
                self._solve(recordset, delivery={chain[0].id: self.bk({1: 1})})

    def test_auto_make_buy(self):
        bom = self._bom(self.fg, [(self.rm, 1)])
        delivery = {self.fg.id: self.bk({1: 5}), self.rm.id: self.bk({1: 5})}
        res = self._solve(self.fg | self.rm, boms={self.fg.id: bom}, delivery=delivery)
        actions = {s['product_id']: s['action'] for s in res.suggestions}
        self.assertEqual(actions[self.fg.id], 'make')
        self.assertEqual(actions[self.rm.id], 'buy')

    def test_supply_method_override(self):
        bom = self._bom(self.fg, [(self.rm, 1)])
        params = {self.fg.id: {'supply_method': 'buy'}}
        res = self._solve(
            self.fg, boms={self.fg.id: bom}, params=params, delivery={self.fg.id: self.bk({1: 5})})
        self.assertEqual(res.suggestions[0]['action'], 'buy')
        self.assertFalse(res.suggestions[0]['bom_id'])

    def test_make_without_bom_warns_and_skips(self):
        params = {self.fg.id: {'supply_method': 'make'}}
        res = self._solve(self.fg, params=params, delivery={self.fg.id: self.bk({1: 5})})
        self.assertFalse(res.suggestions)
        self.assertTrue(res.warnings)

    def test_kept_suggestion_counts_as_receipt_and_explodes(self):
        bom = self._bom(self.fg, [(self.rm, 2)])
        kept = [{
            'id': 99, 'product_id': self.fg.id, 'action': 'make', 'qty': 20,
            'date_need': MONDAY + timedelta(days=7), 'date_release': MONDAY + timedelta(days=4)}]
        res = self._solve(
            self.fg | self.rm, boms={self.fg.id: bom}, kept=kept,
            delivery={self.fg.id: self.bk({1: 20})})
        self.assertEqual([s['product_id'] for s in res.suggestions], [self.rm.id])
        self.assertEqual(res.suggestions[0]['qty'], 40)
        self.assertEqual(res.suggestions[0]['parent_key'], ('db', 99))

    def test_production_line_falls_back_to_latest_mo(self):
        bom = self._bom(self.fg, [(self.rm, 1)])
        pts = self.env['stock.picking.type'].search([('code', '=', 'mrp_operation')], limit=2)
        res = self._solve(self.fg, boms={self.fg.id: bom}, delivery={self.fg.id: self.bk({1: 5})},
                          last_lines={self.fg.id: pts[0].id})
        self.assertEqual(res.suggestions[0]['picking_type_id'], pts[0].id)
        params = {self.fg.id: {'picking_type_id': pts[-1].id}}
        res = self._solve(self.fg, boms={self.fg.id: bom}, params=params,
                          delivery={self.fg.id: self.bk({1: 5})}, last_lines={self.fg.id: pts[0].id})
        self.assertEqual(res.suggestions[0]['picking_type_id'], pts[-1].id, "parameter wins")

    def test_picking_type_filter(self):
        bom = self._bom(self.fg, [(self.rm, 1)])
        pt_a = self.env['stock.picking.type'].search([('code', '=', 'mrp_operation')], limit=2)
        params = {self.fg.id: {'picking_type_id': pt_a[0].id}}
        res = self._solve(
            self.fg, boms={self.fg.id: bom}, params=params, delivery={self.fg.id: self.bk({1: 5})},
            allowed_picking_type_ids=[pt_a[-1].id + 1000])
        self.assertFalse(res.suggestions, "line not in the plan's selection")
        self.assertTrue(any('TEST-FG' in w for w in res.warnings), "the planner is told why")
        res = self._solve(
            self.fg, boms={self.fg.id: bom}, params=params, delivery={self.fg.id: self.bk({1: 5})},
            allowed_picking_type_ids=[pt_a[0].id])
        self.assertEqual(len(res.suggestions), 1)
