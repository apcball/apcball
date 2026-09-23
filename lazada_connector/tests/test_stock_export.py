import base64
import io

from odoo.tests import TransactionCase

try:
    import openpyxl
except ImportError:
    openpyxl = None


class TestLazadaStockExport(TransactionCase):
    def setUp(self):
        super().setUp()
        # Reuse an existing variant - creating product.product fails on
        # MOG_DEV (orphaned columns). Mutations are rolled back with the
        # transaction.
        self.product = self.env["product.product"].search(
            [("default_code", "!=", False)], limit=1
        )
        if not self.product:
            self.skipTest("No product with an internal reference available")
        self.product.write({
            "lazada_item_id": "9001",
            "lazada_sku_id": False,
            "lazada_stock": 33,
            "lazada_pushed_stock": 0,
        })

    def _export(self):
        if not openpyxl:
            self.skipTest("openpyxl is not installed")
        return self.env["lazada.stock.export.wizard"].create({})

    def _rows(self, wizard):
        workbook = openpyxl.load_workbook(
            io.BytesIO(base64.b64decode(wizard.file_data))
        )
        return list(workbook.active.iter_rows(values_only=True))

    def test_export_contains_linked_products(self):
        wizard = self._export()
        self.assertGreaterEqual(wizard.product_count, 1)
        self.assertEqual(wizard.file_name, "lazada_stock_export.xlsx")

        rows = self._rows(wizard)
        self.assertEqual(rows[0][0], "SKU")
        self.assertEqual(rows[0][4], "Lazada Stock")
        matching = [
            row for row in rows[1:] if row[0] == self.product.default_code
        ]
        self.assertTrue(matching)
        self.assertEqual(matching[0][2], "9001")
        self.assertEqual(matching[0][4], 33)

    def test_export_file_round_trips_through_import(self):
        wizard = self._export()
        self.product.write({"lazada_stock": 0})
        self.product.invalidate_recordset()

        import_wizard = self.env["lazada.stock.import.wizard"].create({
            "file_name": wizard.file_name,
            "file_data": wizard.file_data,
        })
        import_wizard.action_import()
        self.product.invalidate_recordset()

        self.assertEqual(self.product.lazada_stock, 33)
