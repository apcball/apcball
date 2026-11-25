from odoo.tests.common import TransactionCase


class TestStockCurrentPerf(TransactionCase):
    """Invariants kept by the performance rewrite of the report views."""

    def test_report_ids_unique(self):
        self.env.cr.execute("""
            SELECT COUNT(*), COUNT(DISTINCT id) FROM stock_current_report
        """)
        total, distinct = self.env.cr.fetchone()
        self.assertEqual(total, distinct)

    def test_product_ids_deterministic(self):
        Product = self.env['stock.current.product']
        first = Product.search([], limit=20).ids
        second = Product.search([], limit=20).ids
        self.assertEqual(first, second)
        rows = Product.search([], limit=20)
        for rec in rows:
            self.assertEqual(rec.id, rec.product_id.id * 100000)

    def test_one_row_per_product_location(self):
        self.env.cr.execute("""
            SELECT 1 FROM stock_current_report
            WHERE location_id IS NOT NULL
            GROUP BY product_id, location_id HAVING COUNT(*) > 1 LIMIT 1
        """)
        self.assertFalse(self.env.cr.fetchone())

    def test_sidebar_query_count(self):
        with self.assertQueryCount(__system__=2):
            self.env['stock.current.report'].get_warehouses_with_locations()
