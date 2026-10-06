from odoo.tests.common import TransactionCase


class TestStockCurrentProduct(TransactionCase):
    """Read-only checks of stock.current.product against stock.current.report."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Product = cls.env['stock.current.product']
        cls.Report = cls.env['stock.current.report']
        sample = cls.Report.search(
            [('warehouse_id', '!=', False), ('quantity', '>', 0)], limit=1)
        cls.product = sample.product_id
        cls.warehouse = sample.warehouse_id

    def setUp(self):
        super().setUp()
        if not self.product:
            self.skipTest('No stock data available')

    def _report_rows(self, **extra):
        domain = [('product_id', '=', self.product.id)]
        if 'warehouse' in extra:
            domain.append(('warehouse_id', '=', extra['warehouse'].id))
        return self.Report.search(domain)

    def test_all_view_one_row_per_product(self):
        rows = self.Product.search([('product_id', '=', self.product.id)])
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows.warehouse_id)

    def test_all_view_no_duplicate_products(self):
        data = self.Product.read_group([], ['product_id'], ['product_id'])
        self.assertTrue(all(g['product_id_count'] == 1 for g in data))

    def test_aggregate_equals_report_sum(self):
        total = self.Product.search([('product_id', '=', self.product.id)])
        rows = self._report_rows()
        self.assertAlmostEqual(total.quantity, sum(rows.mapped('quantity')))
        self.assertAlmostEqual(total.free_to_use, sum(rows.mapped('free_to_use')))
        self.assertAlmostEqual(total.incoming, sum(rows.mapped('incoming')))
        self.assertAlmostEqual(total.outgoing, sum(rows.mapped('outgoing')))

    def test_warehouse_filter(self):
        row = self.Product.search([
            ('product_id', '=', self.product.id),
            ('warehouse_id', '=', self.warehouse.id)])
        self.assertEqual(len(row), 1)
        rows = self._report_rows(warehouse=self.warehouse)
        self.assertAlmostEqual(row.quantity, sum(rows.mapped('quantity')))
        self.assertIn(row.main_location_id, rows.mapped('location_id'))

    def test_badge_and_vat_price(self):
        row = self.Product.search([('product_id', '=', self.product.id)])
        self.assertEqual(row.state_badge, 'in_stock' if row.free_to_use > 0 else 'active')
        self.assertAlmostEqual(
            row.price_with_vat, round(self.product.list_price * 1.07, 2), places=2)

    def test_panel_counts_distinct_products(self):
        res = self.Product.search_panel_select_range('warehouse_id', enable_counters=True)
        counts = {v['id']: v['__count'] for v in res['values']}
        expected = self.Product.search_count([('warehouse_id', '=', self.warehouse.id)])
        self.assertEqual(counts[self.warehouse.id], expected)
        distinct = len(set(self.Product.search(
            [('warehouse_id', '=', self.warehouse.id)]).mapped('product_id')))
        self.assertEqual(expected, distinct)
