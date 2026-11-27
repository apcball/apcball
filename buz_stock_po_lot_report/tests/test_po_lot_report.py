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
        L = namedtuple('L', 'id quantity value parent_id wh_id doc lcs', defaults=((),))
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

    def test_back_dated_receipt_pays_back_earlier_shortfall(self):
        """Issued before the receipt is dated: warehouse ends at 0, so no lot is shown."""
        rows = self._synthetic_rows([(1, -3, -300.0, 'SO1'), (2, 3, 300.0, 'LOT-A')])
        total = [r for r in rows if r['line_type'] == 'total'][0]
        self.assertAlmostEqual(total['bal_qty'], 0.0)
        self.assertFalse([r for r in rows if r['line_type'] == 'lot' and r['bal_qty']])
        # partial: 5 in, 3 already issued -> 2 left in that lot
        rows = self._synthetic_rows([(1, -3, -300.0, 'SO1'), (2, 5, 500.0, 'LOT-B')])
        lots = [r for r in rows if r['line_type'] == 'lot']
        self.assertEqual([round(r['bal_qty'], 4) for r in lots if r['bal_qty']], [2.0])

    def test_transferred_lot_shows_day_it_entered_the_warehouse(self):
        from datetime import date, datetime
        from odoo.addons.buz_stock_po_lot_report.wizard.po_lot_wizard import Layer
        prod = self.env['product.product'].search([], limit=1)
        wiz = self.env['buz.po.lot.wizard'].create({
            'date_from': '2026-01-01', 'date_to': '2026-12-31', 'hide_zero': False})
        h = 3  # 10:00 Bangkok, same local day
        items = [
            (datetime(2026, 10, 1, h), 1, Layer(1, prod.id, 1, 5, 500.0, 'LOT-A', None, False, None, None, None)),
            (datetime(2026, 10, 10, h), 2, Layer(2, prod.id, 1, -2, -200.0, 'TR1', 9, True, 1, 2, None)),
            (datetime(2026, 10, 10, h), 3, Layer(3, prod.id, 2, 2, 200.0, 'TR1', 9, True, 1, 2, None)),
        ]
        start, end = wiz._utc_bounds()
        rows = wiz._product_rows(prod, items, start, datetime.min, end)
        lots = {r['warehouse_id']: r for r in rows if r['line_type'] == 'lot' and r['bal_qty']}
        self.assertEqual(lots[1]['wh_date'], date(2026, 10, 1))
        self.assertEqual(lots[2]['wh_date'], date(2026, 10, 10))   # arrived by transfer
        self.assertEqual(lots[2]['date'], date(2026, 10, 10))      # date of the queue document
        self.assertIn('(ล็อต LOT-A)', lots[2]['doc_ref'])          # origin still traceable

    def test_receipt_row_shows_all_in_unit_cost(self):
        from datetime import datetime
        from odoo.addons.buz_stock_po_lot_report.wizard.po_lot_wizard import Layer
        prod = self.env['product.product'].search([], limit=1)
        wiz = self.env['buz.po.lot.wizard'].create({
            'date_from': '2026-01-01', 'date_to': '2026-12-31', 'hide_zero': False})
        items = [
            (datetime(2026, 10, 1, 3), 1, Layer(1, prod.id, 1, 10, 1000.0, 'LOT-A', None, False, None, None, None)),
            (datetime(2026, 10, 5, 3), 2, Layer(2, prod.id, 1, 0, 50.0, 'BR9 (ลงล็อต LOT-A)', None, False,
                                                None, None, 1, (('BR9', 50.0),), True)),
        ]
        start, end = wiz._utc_bounds()
        rows = wiz._product_rows(prod, items, start, datetime.min, end)
        rec = [r for r in rows if r['line_type'] == 'move' and r.get('in_qty') == 10][0]
        self.assertAlmostEqual(rec['in_cost'], 100.0)
        self.assertAlmostEqual(rec['in_allin'], 105.0)

    def test_same_origin_lot_is_one_row_with_weighted_cost(self):
        rows = self._synthetic_rows([(1, 7, 7 * 10.0, 'LOT-B'), (2, 3, 3 * 20.0, 'LOT-B')])
        lots = [r for r in rows if r['line_type'] == 'lot']
        self.assertEqual(len(lots), 1)
        self.assertAlmostEqual(lots[0]['bal_qty'], 10)
        self.assertAlmostEqual(lots[0]['bal_cost'], 13.0)
        self.assertAlmostEqual(lots[0]['bal_value'], 130.0)
        snaps = [r for r in rows if r['line_type'] == 'lotbal']
        self.assertEqual(len(snaps), 2)  # one lot row after each of the 2 movements

    def test_xlsx_movement_shows_document_and_lot_separately(self):
        from odoo.addons.buz_stock_po_lot_report.report.po_lot_xlsx import move_cells
        self.assertEqual(move_cells('FG10/INT/26/10/00162 (ล็อต RM01/2610047) · คลังสินค้าสำเร็จรูป 1'),
                         ('FG10/INT/26/10/00162', 'RM01/2610047'))
        self.assertEqual(move_cells('BR26100194 ค่าเฟรท (ลงล็อต RM01/2610047) · คลัง'),
                         ('BR26100194 ค่าเฟรท', 'RM01/2610047'))
        self.assertEqual(move_cells('RM01/2610047 · คลังสินค้าสำเร็จรูป 1'), ('RM01/2610047', ''))

    def test_xlsx_splits_lot_from_document(self):
        from odoo.addons.buz_stock_po_lot_report.report.po_lot_xlsx import split_lot
        self.assertEqual(split_lot('RM01260900083 (ล็อต RM-NI/IN2609003)'),
                         ('RM-NI/IN2609003', 'RM01260900083'))
        self.assertEqual(split_lot('BR1 ค่าเช่า (ลงล็อต RM01/2610047)'),
                         ('RM01/2610047', 'BR1 ค่าเช่า'))
        self.assertEqual(split_lot('RM-NI/IN2609003'), ('RM-NI/IN2609003', ''))

    def test_group_landed_keeps_each_bill(self):
        """Value-only layers merged into one movement row still remember
        their own landed-cost bill and value."""
        import pytz
        from datetime import datetime
        from odoo.addons.buz_stock_po_lot_report.wizard.po_lot_wizard import BuzPoLotWizard, Layer
        d = datetime(2026, 5, 1, 3, 0)

        def lc(i, ref, val):
            return (d, i, Layer(i, 1, 1, 0.0, val, 'x', None, False, None, None, 10, ((ref, val),)))

        out = BuzPoLotWizard._group_landed(
            [lc(1, 'BR1', 10.0), lc(2, 'BR2', 5.0), lc(3, 'BR1', 2.0)],
            {1: 'R', 2: 'R', 3: 'R'}, pytz.timezone('Asia/Bangkok'))
        # one row per landed-cost document (like the FIFO valuation report)
        self.assertEqual(len(out), 2)
        br1, br2 = out[0][2], out[1][2]
        self.assertAlmostEqual(br1.value, 12.0)
        self.assertEqual(dict(br1.lcs), {'BR1': 12.0})
        self.assertIn('(x2)', br1.doc)
        self.assertAlmostEqual(br2.value, 5.0)
        self.assertNotIn('(x', br2.doc)


    # ------------------------------------------- ending lots = warehouse queue
    def _two_wh_rows(self, layers, trace=None):
        """layers: (day, id, wh index, qty, value, doc, transfer move id or None).
        Returns (wizard, rows, [wh1 id, wh2 id])."""
        from datetime import datetime
        from odoo.addons.buz_stock_po_lot_report.wizard.po_lot_wizard import Layer
        whs = [self.env['stock.warehouse'].create({'name': 'QWH%d' % i, 'code': 'QW%d' % i}).id
               for i in (1, 2)]
        prod = self.env['product.product'].create({'name': 'queue', 'default_code': 'QUEUE000'})
        wiz = self.env['buz.po.lot.wizard'].create({
            'date_from': '2026-01-01', 'date_to': '2026-12-31', 'hide_zero': False})
        items = []
        for day, lid, wh, qty, value, doc, mid in layers:
            items.append((datetime(2026, 10, day, 3), lid, Layer(
                lid, prod.id, whs[wh - 1], qty, value, doc, mid, bool(mid),
                whs[0] if mid else None, whs[1] if mid else None, None)))
        start, end = wiz._utc_bounds()
        rows = wiz._product_rows(prod, items, start, datetime.min, end, trace=trace)
        return wiz, rows, whs

    @staticmethod
    def _ending(rows, wh):
        return [r for r in rows if r['line_type'] == 'lot' and r.get('warehouse_id') == wh]

    @staticmethod
    def _doc(row):
        return row['doc_ref'].split(' · ')[0]

    def test_ending_lot_shows_warehouse_queue_document(self):
        _w, rows, (a, b) = self._two_wh_rows([
            (1, 1, 1, 5, 500.0, 'LOT-A', None),
            (10, 2, 1, -2, -200.0, 'TR1', 9),
            (10, 3, 2, 2, 200.0, 'TR1', 9)])
        self.assertEqual([self._doc(r) for r in self._ending(rows, b)], ['TR1 (ล็อต LOT-A)'])
        # received directly: the queue document is the origin, nothing to add
        self.assertEqual([self._doc(r) for r in self._ending(rows, a)], ['LOT-A'])
        snaps = [r for r in rows if r['line_type'] == 'lotbal' and r['warehouse_id'] == b]
        self.assertEqual(self._doc(snaps[-1]), 'TR1 (ล็อต LOT-A)')

    def test_each_transfer_is_its_own_queue_row(self):
        _w, rows, (_a, b) = self._two_wh_rows([
            (1, 1, 1, 5, 500.0, 'LOT-A', None),
            (10, 2, 1, -2, -200.0, 'TR1', 9), (10, 3, 2, 2, 200.0, 'TR1', 9),
            (12, 4, 1, -1, -100.0, 'TR2', 11), (12, 5, 2, 1, 100.0, 'TR2', 11)])
        self.assertEqual([(self._doc(r), r['bal_qty']) for r in self._ending(rows, b)],
                         [('TR1 (ล็อต LOT-A)', 2), ('TR2 (ล็อต LOT-A)', 1)])

    def test_transfer_with_several_origins_is_one_queue_row(self):
        _w, rows, (a, b) = self._two_wh_rows([
            (1, 1, 1, 1, 100.0, 'LOT-A', None),
            (2, 2, 1, 1, 100.0, 'LOT-B', None),
            (3, 3, 1, 2, 100.0, 'LOT-C', None),
            (10, 4, 1, -3, -300.0, 'TR1', 9), (10, 5, 2, 3, 330.0, 'TR1', 9)])
        lot, = self._ending(rows, b)
        self.assertEqual(self._doc(lot), 'TR1 (ล็อต LOT-A, LOT-B, LOT-C)')  # all origins
        self.assertAlmostEqual(lot['bal_qty'], 3)
        self.assertAlmostEqual(lot['bal_value'], 330.0)
        # consumption order unchanged: oldest document first
        self.assertEqual([(self._doc(r), r['bal_qty']) for r in self._ending(rows, a)],
                         [('LOT-C', 1)])

    def test_trace_still_keyed_by_origin_lot(self):
        """buz_new_stock_card reads trace[...] and expects the origin document."""
        trace = {'out': {}, 'in': {}, 'layers': [], 'opening': [], 'ending': [], 'bal': {},
                 'open_bal': {}}
        _w, _rows, (_a, b) = self._two_wh_rows([
            (1, 1, 1, 5, 500.0, 'LOT-A', None),
            (10, 2, 1, -2, -200.0, 'TR1', 9), (10, 3, 2, 2, 200.0, 'TR1', 9)], trace=trace)
        ending = [lot for _d, wh, lot in trace['ending'] if wh == b]
        self.assertEqual([(lot[0], len(lot)) for lot in ending], [('LOT-A', 5)])

    def test_xlsx_ending_lot_has_origin_in_its_own_column(self):
        import io
        import re
        import zipfile
        import xlsxwriter
        wiz, rows, _whs = self._two_wh_rows([
            (1, 1, 1, 5, 500.0, 'LOT-A', None),
            (10, 2, 1, -2, -200.0, 'TR1', 9), (10, 3, 2, 2, 200.0, 'TR1', 9)])
        wiz._insert_lines(rows)
        buf = io.BytesIO()
        book = xlsxwriter.Workbook(buf, {'constant_memory': True})
        self.env['report.buz_stock_po_lot_report.po_lot_xlsx'].generate_xlsx_report(book, {}, wiz)
        book.close()
        xml = zipfile.ZipFile(buf).read('xl/worksheets/sheet1.xml').decode()
        cells = {m.group(1): m.group(2) for m in re.finditer(
            r'<c r="([A-Z]+\d+)"[^>]*t="inlineStr"[^>]*><is><t[^>]*>([^<]*)</t>', xml)}
        title = next(k for k, v in cells.items() if v == 'สินค้าปลายงวด')
        after = {k: v for k, v in cells.items()
                 if int(re.sub('[A-Z]', '', k)) > int(title[1:])}
        row = next(k[1:] for k, v in after.items() if k[0] == 'B' and v == 'TR1')
        self.assertEqual(after.get('M' + row), 'LOT-A')

    def test_xlsx_origin_with_brackets_is_split(self):
        from odoo.addons.buz_stock_po_lot_report.report.po_lot_xlsx import move_cells
        self.assertEqual(move_cells('TR1 (ล็อต Opening (2025), LOT-B) · คลัง'),
                         ('TR1', 'Opening (2025), LOT-B'))
