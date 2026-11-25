from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestTaxStockReport(TransactionCase):
    def test_ledger_and_lots_tie(self):
        svl = self.env['stock.valuation.layer'].search(
            [('product_id.default_code', '!=', False)], limit=1)
        if not svl:
            self.skipTest('no valuation layers')
        prod = svl.product_id
        wiz = self.env['buz.po.lot.wizard'].create({
            'date_from': '2000-01-01', 'date_to': '2099-12-31',
            'product_ids': [(6, 0, prod.ids)], 'hide_zero': False})
        rows = wiz._compute_rows()
        total = [r for r in rows if r['line_type'] == 'total'][0]
        lots_q = sum(r['bal_qty'] for r in rows if r['line_type'] == 'lot')
        self.assertAlmostEqual(lots_q, total['bal_qty'], places=3)
        svl_all = self.env['stock.valuation.layer'].search(
            [('product_id', '=', prod.id), ('company_id', '=', wiz.company_id.id)])
        self.assertAlmostEqual(total['bal_qty'], sum(svl_all.mapped('quantity')), places=3)
        self.assertAlmostEqual(
            total['bal_value'], sum(r['bal_value'] for r in rows if r['line_type'] in ('lot', 'adjust')), places=1)

    def test_no_product_filter_lists_balance_products(self):
        wiz = self.env['buz.po.lot.wizard'].create({
            'date_from': '2000-01-01', 'date_to': '2099-12-31', 'hide_zero': True})
        from itertools import islice
        # must not raise without product/prefix; stream a sample (full set is big)
        rows = [r for chunk in islice(wiz._iter_rows(), 200) for r in chunk]
        if not rows:
            self.skipTest('no valuation layers')
        totals = [r for r in rows if r['line_type'] == 'total']
        for t in totals:
            self.assertTrue(t['bal_qty'] or t['bal_value'] or t['in_qty'] or t['out_qty'])
        models = [r['model_code'] for r in rows if r['line_type'] == 'opening']
        self.assertEqual(models, sorted(models))

    def test_lot_rows_tie_after_every_movement(self):
        """Lot rows under each movement sum to that movement's balance; the
        totals row closes the product and ties to the ending lots."""
        svl = self.env['stock.valuation.layer'].search(
            [('product_id.default_code', '!=', False), ('warehouse_id', '!=', False)], limit=1)
        if not svl:
            self.skipTest('no valuation layers')
        wiz = self.env['buz.po.lot.wizard'].create({
            'date_from': '2000-01-01', 'date_to': '2099-12-31',
            'product_ids': [(6, 0, svl.product_id.ids)], 'hide_zero': False,
            'show_lots_each_row': True})
        rows = wiz._compute_rows()
        last = None
        lots_q = 0.0
        for r in rows:
            if r['line_type'] in ('opening', 'move'):
                if last is not None and last['bal_qty'] >= 0:
                    self.assertAlmostEqual(lots_q, last['bal_qty'], places=3)
                last, lots_q = r, 0.0
            elif r['line_type'] == 'lotbal':
                lots_q += r['bal_qty']
        self.assertEqual(rows[-1]['line_type'] in ('total', 'adjust'), True)
        wiz.show_lots_each_row = False
        self.assertFalse([r for r in wiz._compute_rows() if r['line_type'] == 'lotbal'])

    def test_refresh_and_xlsx_rows(self):
        svl = self.env['stock.valuation.layer'].search(
            [('product_id.default_code', '!=', False), ('warehouse_id', '!=', False)], limit=1)
        if not svl:
            self.skipTest('no valuation layers')
        wiz = self.env['buz.po.lot.wizard'].create({
            'date_from': '2000-01-01', 'date_to': '2099-12-31',
            'product_ids': [(6, 0, svl.product_id.ids)], 'hide_zero': False})
        wiz._refresh()
        n = len(wiz.line_ids)
        wiz._refresh()  # re-run must replace, not append
        self.assertEqual(len(wiz.line_ids), n)
        self.assertTrue(n)

    def test_transit_excluded_by_default(self):
        transit = self.env['stock.warehouse'].with_context(active_test=False).search(
            [('lot_stock_id.usage', '=', 'transit')])
        if not transit:
            self.skipTest('no transit warehouse')
        wiz = self.env['buz.po.lot.wizard'].create({
            'date_from': '2000-01-01', 'date_to': '2099-12-31'})
        self.assertFalse(set(transit.ids) & wiz._report_wh_ids())
        wiz.include_transit = True
        self.assertEqual(wiz._report_wh_ids(), set())
        wiz.warehouse_ids = transit
        self.assertEqual(wiz._report_wh_ids(), set(transit.ids))

    def test_landed_cost_follows_its_parent_layer(self):
        from collections import namedtuple
        from datetime import datetime
        L = namedtuple('L', 'id quantity value parent_id')
        parent = (datetime(2026, 10, 22, 9), 10, L(10, 2, 100.0, None))
        lc = (datetime(2026, 10, 22, 0), 20, L(20, 0, 5.0, 10))   # dated before parent
        lc_late = (datetime(2026, 10, 28), 30, L(30, 0, 7.0, 10))  # dated after parent
        other = (datetime(2026, 10, 22, 12), 11, L(11, -1, -50.0, None))
        out = self.env['buz.po.lot.wizard']._landed_after_parent([lc, other, parent, lc_late])
        self.assertEqual([t[1] for t in out], [10, 20, 11, 30])
        self.assertEqual(out[1][0], lc[0])  # own date kept

    def test_landed_cost_grouped_per_parent_and_day(self):
        from collections import namedtuple
        from datetime import datetime
        import pytz
        L = namedtuple('L', 'id quantity value parent_id wh_id doc')
        d = datetime(2026, 10, 21, 18)   # 22/10 01:00 Bangkok
        a = (d, 20, L(20, 0, 5.0, 10, 1, 'bill a'))
        b = (d, 21, L(21, 0, 7.5, 10, 1, 'bill b'))
        c = (datetime(2026, 10, 28, 3), 22, L(22, 0, 3.0, 10, 1, 'bill c'))  # other day
        rcv = (d, 10, L(10, 2, 100.0, None, 1, 'RCV'))
        lcdoc = {20: 'RM01/1', 21: 'RM01/1', 22: 'RM01/1'}
        out = self.env['buz.po.lot.wizard']._group_landed(
            [rcv, a, b, c], lcdoc, pytz.timezone('Asia/Bangkok'))
        self.assertEqual([t[1] for t in out], [10, 20, 22])
        self.assertAlmostEqual(out[1][2].value, 12.5)
        self.assertIn('2 รายการ', out[1][2].doc)
        self.assertIn('RM01/1', out[1][2].doc)
        self.assertEqual(out[2][2].doc, 'bill c')  # single layer keeps its own bill

    def _synthetic_rows(self, layers):
        from datetime import datetime
        from odoo.addons.buz_stock_po_lot_report.wizard.po_lot_wizard import Layer
        prod = self.env['product.product'].search([], limit=1)
        wiz = self.env['buz.po.lot.wizard'].create({
            'date_from': '2026-01-01', 'date_to': '2026-12-31', 'hide_zero': False})
        items = [(datetime(2026, 10, 1 + i), lid, Layer(lid, prod.id, 1, q, v, doc, None, False,
                                                       None, None, None))
                 for i, (lid, q, v, doc) in enumerate(layers)]
        start, end = wiz._utc_bounds()
        return wiz._product_rows(prod, items, start, datetime.min, end)

    def test_outgoing_row_shows_lot_it_was_cut_from(self):
        rows = self._synthetic_rows([(1, 2, 200.0, 'LOT-A'), (2, -1, -100.0, 'SO1')])
        sale = [r for r in rows if r['line_type'] == 'move' and r.get('out_qty')][0]
        self.assertIn('(ล็อต LOT-A)', sale['doc_ref'])
        receipt = [r for r in rows if r['line_type'] == 'move' and r.get('in_qty')][0]
        self.assertNotIn('ล็อต', receipt['doc_ref'])

    def test_same_origin_lot_is_one_row_with_weighted_cost(self):
        rows = self._synthetic_rows([(1, 7, 7 * 10.0, 'LOT-B'), (2, 3, 3 * 20.0, 'LOT-B')])
        lots = [r for r in rows if r['line_type'] == 'lot']
        self.assertEqual(len(lots), 1)
        self.assertAlmostEqual(lots[0]['bal_qty'], 10)
        self.assertAlmostEqual(lots[0]['bal_cost'], 13.0)
        self.assertAlmostEqual(lots[0]['bal_value'], 130.0)
        snaps = [r for r in rows if r['line_type'] == 'lotbal']
        self.assertEqual(len(snaps), 2)  # one lot row after each of the 2 movements
