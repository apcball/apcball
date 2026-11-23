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
        rows = wiz._compute_rows()  # must not raise without product/prefix
        if not rows:
            self.skipTest('no valuation layers')
        totals = [r for r in rows if r['line_type'] == 'total']
        for t in totals:
            self.assertTrue(t['bal_qty'] or t['bal_value'] or t['in_qty'] or t['out_qty'])
        models = [r['model_code'] for r in rows if r['line_type'] == 'opening']
        self.assertEqual(models, sorted(models))

    def test_transfer_in_traced_to_origin_receipt(self):
        """Transfer-in layers show the origin receipt doc, not the transfer."""
        Svl = self.env['stock.valuation.layer']
        wiz = self.env['buz.po.lot.wizard'].create({
            'date_from': '2000-01-01', 'date_to': '2099-12-31', 'hide_zero': False})
        start_utc, end_utc = wiz._utc_bounds()
        cutoff = self.env['ir.config_parameter'].sudo().get_param(
            'stock_fifo_valuation_report.cutoff_date')
        from datetime import datetime
        from odoo import fields
        cutoff_utc = wiz._bangkok_start_utc(fields.Date.to_date(cutoff)) if cutoff else datetime.min
        cand = Svl.search([('quantity', '>', 0), ('warehouse_id', '!=', False),
                           ('description', 'like', 'Transfer IN%')], limit=20)
        for sv in cand:
            layers = wiz._fetch_layers([sv.product_id.id], cutoff_utc, end_utc).get(sv.product_id.id, [])
            items = [t for t in layers if t[1] == sv.id]
            if not items:
                continue
            labels = wiz._origin_labels(items, layers, end_utc)
            if sv.id in labels:
                self.assertTrue(labels[sv.id][0])
                return
        self.skipTest('no traceable transfer-in layer')

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
