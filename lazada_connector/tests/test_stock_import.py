import base64
import io

from odoo.exceptions import UserError
from odoo.tests import TransactionCase

try:
    import openpyxl
except ImportError:
    openpyxl = None


class TestLazadaStockImport(TransactionCase):
    def setUp(self):
        super().setUp()
        self.product = self.env["product.product"].search(
            [("default_code", "!=", False)], limit=1
        )
        if not self.product:
            self.skipTest("No product with an internal reference available")
        self.product.write({"lazada_stock": 4})

    def _import(self, content, filename="lazada_stock.csv"):
        wizard = self.env["lazada.stock.import.wizard"].create(
            {
                "file_name": filename,
                "file_data": base64.b64encode(content),
            }
        )
        wizard.action_import()

    def test_csv_updates_lazada_stock_only(self):
        on_hand = self.product.qty_available
        content = (
            "SKU,Available Stock\n%s,17\n" % self.product.default_code
        ).encode()

        self._import(content)
        self.product.invalidate_recordset()

        self.assertEqual(self.product.lazada_stock, 17)
        self.assertEqual(self.product.qty_available, on_hand)

    def test_unknown_sku_is_rejected_without_creating_products(self):
        product_count = self.env["product.product"].search_count([])
        content = b"SKU,Stock\nUNKNOWN-LAZADA-SKU,3\n"

        with self.assertRaises(UserError):
            self._import(content)

        self.assertEqual(
            self.env["product.product"].search_count([]), product_count
        )

    def test_invalid_quantity_is_rejected(self):
        content = ("SKU,Stock\n%s,not-a-number\n" % self.product.default_code).encode()

        with self.assertRaises(UserError):
            self._import(content)

    def test_xlsx_updates_lazada_stock(self):
        if not openpyxl:
            self.skipTest("openpyxl is not installed")
        workbook = openpyxl.Workbook()
        worksheet = workbook.active
        worksheet.append(["Variation SKU", "Available Stock"])
        worksheet.append([self.product.default_code, 23])
        stream = io.BytesIO()
        workbook.save(stream)

        self._import(stream.getvalue(), "lazada_stock.xlsx")
        self.product.invalidate_recordset()

        self.assertEqual(self.product.lazada_stock, 23)
