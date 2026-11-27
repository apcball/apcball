"""The report reflects what the system really holds, for accounting to review:
entry date of back-dated movements, the system FIFO queue next to the
document-date replay, and one check row per product x warehouse that differs."""
import io
import re
import zipfile
from datetime import datetime, timedelta

import xlsxwriter

from odoo import fields
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.buz_stock_po_lot_report.wizard.po_lot_wizard import Layer


def _day(day, hour=3):
    return datetime(2026, 10, day, hour)  # 10:00 Bangkok


@tagged('post_install', '-at_install')
class TestSystemCompare(TransactionCase):
    def setUp(self):
        super().setUp()
        self.env.user.tz = 'Asia/Bangkok'
        self.wh = self.env['stock.warehouse'].create({'name': 'CMPWH', 'code': 'CMP1'})
        self.prod = self.env['product.product'].create(
            {'name': 'compare', 'default_code': 'CMPPROD000'})
        self.wiz = self.env['buz.po.lot.wizard'].create({
            'date_from': '2026-01-01', 'date_to': '2099-12-31', 'hide_zero': False,
            'product_ids': [(6, 0, self.prod.ids)], 'warehouse_ids': [(6, 0, self.wh.ids)]})

    def _layer(self, lid, day, qty, value, doc, created=None, parent=None):
        return (_day(day), lid, Layer(lid, self.prod.id, self.wh.id, qty, value, doc, None, False,
                                      None, None, parent, created=created or _day(day)))

    def _sys(self, lid, day, qty, value, doc):
        from odoo.addons.buz_stock_po_lot_report.wizard.po_lot_wizard import SysLayer
        return SysLayer(lid, self.wh.id, doc, _day(day), qty, value)

    def _run(self, items, system=None, wiz=None):
        wiz = wiz or self.wiz
        checks = []
        start, end = wiz._utc_bounds()
        rows = wiz._product_rows(self.prod, items, start, datetime.min, end,
                                 system=system, checks=checks)
        return rows, checks

    # ------------------------------------------------------ back-dated movements
    def test_movement_row_flags_back_dated_entry(self):
        rows, _c = self._run([
            self._layer(1, 1, 5, 500.0, 'LATE', created=_day(20)),
            self._layer(2, 2, 1, 100.0, 'ONTIME')])
        moves = {r['doc_ref'].split(' · ')[0]: r for r in rows if r['line_type'] == 'move'}
        self.assertEqual(moves['LATE']['rec_date'], _day(20).date())
        self.assertTrue(moves['LATE']['backdated'])
        self.assertEqual(moves['ONTIME']['rec_date'], _day(2).date())
        self.assertFalse(moves['ONTIME']['backdated'])

    # ------------------------------------------------------ system queue
    def test_ending_lots_show_system_queue_and_difference(self):
        rows, _c = self._run(
            [self._layer(1, 1, 5, 500.0, 'RCV-A'), self._layer(2, 2, 1, 100.0, 'RCV-B'),
             self._layer(3, 3, -5, -500.0, 'SO1')],
            system=[self._sys(1, 1, 1, 100.0, 'RCV-A'), self._sys(2, 2, 1, 100.0, 'RCV-B')])
        lots = {r['doc_ref'].split(' · ')[0]: r for r in rows if r['line_type'] == 'lot'}
        # replay used RCV-A up, the system still holds 1 of it: still listed
        self.assertEqual((lots['RCV-A']['bal_qty'], lots['RCV-A']['sys_qty'],
                          lots['RCV-A']['diff_qty']), (0.0, 1.0, 1.0))
        self.assertAlmostEqual(lots['RCV-A']['diff_value'], 100.0)
        self.assertEqual((lots['RCV-B']['bal_qty'], lots['RCV-B']['sys_qty'],
                          lots['RCV-B']['diff_qty']), (1, 1.0, 0.0))
        self.assertTrue(all(r['has_sys'] for r in lots.values()))
        total = [r for r in rows if r['line_type'] == 'total'][0]
        self.assertEqual((total['sys_qty'], total['diff_qty']), (2.0, 1.0))

    def test_system_columns_do_not_change_the_ledger(self):
        items = [self._layer(1, 1, 5, 500.0, 'RCV-A'), self._layer(3, 3, -2, -200.0, 'SO1')]
        keys = ('line_type', 'date', 'doc_ref', 'in_qty', 'in_value', 'out_qty', 'out_value',
                'bal_qty', 'bal_value')

        def ledger(rows):
            return [tuple(r.get(k) for k in keys) for r in rows if r['line_type'] != 'lot']

        plain, _c = self._run(items)
        compared, _c = self._run(items, system=[self._sys(9, 1, 7, 70.0, 'OTHER')])
        self.assertEqual(ledger(plain), ledger(compared))
        self.assertFalse([r for r in plain if r.get('has_sys')])

    def test_system_queue_only_for_a_report_up_to_today(self):
        today = fields.Date.context_today(self.wiz)
        self.wiz.date_to = today
        self.assertTrue(self.wiz._show_system())
        self.wiz.date_to = today - timedelta(days=1)
        self.assertFalse(self.wiz._show_system())

    # ------------------------------------------------------ check list
    def test_consistent_product_has_no_check_row(self):
        _r, checks = self._run([self._layer(1, 1, 5, 500.0, 'RCV-A')],
                               system=[self._sys(1, 1, 5, 500.0, 'RCV-A')])
        self.assertEqual(checks, [])

    def test_check_row_lists_the_differences_and_causes(self):
        _r, checks = self._run(
            [self._layer(1, 2, -3, -300.0, 'SO1'),
             self._layer(2, 5, 5, 500.0, 'RCV-A', created=_day(20))],
            system=[self._sys(2, 5, 4, 400.0, 'RCV-A')])
        check, = checks
        self.assertEqual(check['warehouse_id'], self.wh.id)
        self.assertEqual((check['ledger_qty'], check['sys_qty'], check['lot_qty']), (2, 4, 2))
        self.assertAlmostEqual(check['diff_sys_qty'], 2)
        self.assertAlmostEqual(check['diff_sys_value'], 200.0)
        self.assertEqual(check['backdated_count'], 1)
        self.assertAlmostEqual(check['short_qty'], 3)
        for cause in ('คิวระบบไม่ตรงบัญชี', 'จ่ายก่อนรับ', 'รายการย้อนหลัง'):
            self.assertIn(cause, check['note'])

    def test_landed_cost_of_a_used_up_lot_is_reported(self):
        _r, checks = self._run(
            [self._layer(1, 1, 1, 100.0, 'RCV-A'), self._layer(2, 2, 1, 100.0, 'RCV-B'),
             self._layer(3, 3, -1, -100.0, 'SO1'),
             self._layer(4, 4, 0, 30.0, 'BR1', parent=1)],
            system=[self._sys(2, 2, 1, 100.0, 'RCV-B')])
        check, = checks
        self.assertAlmostEqual(check['lc_moved_value'], 30.0)
        self.assertIn('landed cost', check['note'])

    def test_check_row_names_value_left_on_zero_quantity(self):
        _r, checks = self._run([self._layer(1, 1, 1, 100.0, 'RCV-A'),
                                self._layer(2, 2, -1, -60.0, 'SO1')], system=[])
        self.assertIn('ยอดบัญชีจำนวน 0 แต่มีมูลค่า', checks[0]['note'])
        self.assertNotIn('ยอดบัญชีติดลบ', checks[0]['note'])

    def test_check_row_names_negative_ledger(self):
        _r, checks = self._run([self._layer(1, 1, -2, -200.0, 'SO1')], system=[])
        self.assertIn('ยอดบัญชีติดลบ', checks[0]['note'])
        self.assertNotIn('ยอดบัญชีจำนวน 0', checks[0]['note'])

    def test_zero_ledger_with_system_stock_is_checked_but_not_listed(self):
        self.wiz.hide_zero = True
        rows, checks = self._run(
            [self._layer(1, 1, 1, 100.0, 'RCV-A'), self._layer(2, 2, -1, -100.0, 'SO1')],
            system=[self._sys(1, 1, 1, 100.0, 'RCV-A')])
        self.assertEqual(rows, [])  # report body unchanged: zero stock stays hidden
        self.assertEqual([c['sys_qty'] for c in checks], [1])

    # ------------------------------------------------------ database + xlsx
    def _svl(self, qty, value, remaining, doc):
        svl = self.env['stock.valuation.layer'].create({
            'product_id': self.prod.id, 'company_id': self.env.company.id,
            'quantity': qty, 'value': value, 'unit_cost': value / qty,
            'remaining_qty': remaining, 'remaining_value': remaining * value / qty,
            'description': doc})
        self.env.flush_all()
        self.env.cr.execute(
            'UPDATE stock_valuation_layer SET warehouse_id = %s, remaining_qty = %s, '
            'remaining_value = %s WHERE id = %s',
            (self.wh.id, remaining, remaining * value / qty, svl.id))
        self.env.invalidate_all()
        return svl

    def test_refresh_reads_system_queue_and_writes_check_sheet(self):
        svl = self._svl(5, 500.0, 3, 'DBDOC')
        start, end = self.wiz._utc_bounds()
        layer = self.wiz._fetch_layers(self.prod.ids, datetime.min, end)[self.prod.id][0][2]
        self.assertEqual(layer.created.date(), svl.create_date.date())
        queue = self.wiz._fetch_system_queue(self.prod.ids)[self.prod.id]
        self.assertEqual([(q.doc, q.qty, q.value) for q in queue], [('DBDOC', 3.0, 300.0)])

        self.wiz.cutoff_date = '2000-01-01'
        self.wiz._refresh()
        self.wiz._refresh()  # re-run replaces
        check = self.env['buz.po.lot.check'].search([('wizard_id', '=', self.wiz.id)])
        self.assertEqual((check.ledger_qty, check.sys_qty, check.diff_sys_qty), (5, 3, -2))

        buf = io.BytesIO()
        book = xlsxwriter.Workbook(buf, {'constant_memory': True})
        self.env['report.buz_stock_po_lot_report.po_lot_xlsx'].generate_xlsx_report(
            book, {}, self.wiz)
        self.assertEqual([s.name for s in book.worksheets()], ['Stock', 'ให้บัญชีตรวจ'])
        book.close()
        xml = zipfile.ZipFile(buf).read('xl/worksheets/sheet2.xml').decode()
        self.assertIn('CMPPROD000', xml)
        self.assertIn('คิวระบบไม่ตรงบัญชี', xml)
        main = zipfile.ZipFile(buf).read('xl/worksheets/sheet1.xml').decode()
        for head in ('วันที่บันทึกในระบบ', 'จำนวนตามระบบ', 'ผลต่างมูลค่า'):
            self.assertTrue(re.search('>%s<' % head, main), head)
        # the difference columns mean two things: say so on the sheet
        self.assertIn('แถวรวม = ระบบ − บัญชี', main)

    def test_product_with_only_system_stock_is_processed(self):
        self._svl(1, 100.0, 1, 'IN')
        self._svl(1, 100.0, 0, 'IN2')
        self.env.cr.execute(
            'UPDATE stock_valuation_layer SET quantity = -1, value = -100 '
            'WHERE product_id = %s AND description = %s', (self.prod.id, 'IN2'))
        self.env.invalidate_all()
        self.wiz.write({'product_ids': [(5,)], 'cutoff_date': '2000-01-01', 'hide_zero': True})
        _start, end = self.wiz._utc_bounds()
        self.assertIn(self.prod.id, self.wiz._balance_product_ids(end))
        self.wiz._refresh()  # nothing to list, but a check row: no "No data" error
        self.assertFalse(self.wiz.line_ids)
        self.assertTrue(self.env['buz.po.lot.check'].search([('wizard_id', '=', self.wiz.id)]))
