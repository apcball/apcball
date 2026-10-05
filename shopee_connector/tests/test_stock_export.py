import base64
import io

from odoo.tests import TransactionCase

try:
    import openpyxl
except ImportError:
    openpyxl = None


class TestShopeeStockExport(TransactionCase):
    def setUp(self):
        super().setUp()
        self.product = self.env["product.product"].create({
            "name": "Shopee QA Export", "default_code": "SHOPEE-QA-EXPORT", "type": "product",
        })
        self.product.write({
            "shopee_item_id": "9001",
            "shopee_model_id": False,
            "shopee_stock": 33,
            "shopee_pushed_stock": 0,
        })

    def _export(self):
        if not openpyxl:
            self.skipTest("openpyxl is not installed")
        return self.env["shopee.stock.export.wizard"].create({})

    def _rows(self, wizard):
        workbook = openpyxl.load_workbook(
            io.BytesIO(base64.b64decode(wizard.file_data))
        )
        return list(workbook.active.iter_rows(values_only=True))

    def test_export_contains_linked_products(self):
        wizard = self._export()
        self.assertGreaterEqual(wizard.product_count, 1)
        self.assertEqual(wizard.file_name, "shopee_stock_export.xlsx")

        rows = self._rows(wizard)
        self.assertEqual(rows[0][0], "SKU")
        self.assertEqual(rows[0][4], "Shopee Stock")
        matching = [
            row for row in rows[1:] if row[0] == self.product.default_code
        ]
        self.assertTrue(matching)
        self.assertEqual(matching[0][2], "9001")
        self.assertEqual(matching[0][4], 33)

    def test_export_file_round_trips_through_import(self):
        wizard = self._export()
        self.product.write({"shopee_stock": 0})
        self.product.invalidate_recordset()

        import_wizard = self.env["shopee.stock.import.wizard"].create({
            "file_name": wizard.file_name,
            "file_data": wizard.file_data,
        })
        import_wizard.action_import()
        self.product.invalidate_recordset()

        self.assertEqual(self.product.shopee_stock, 33)
