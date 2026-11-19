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
