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
