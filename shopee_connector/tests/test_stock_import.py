import base64
import io

from odoo.exceptions import UserError
from odoo.tests import TransactionCase

try:
    import openpyxl
except ImportError:
    openpyxl = None


class TestShopeeStockImport(TransactionCase):
    def setUp(self):
        super().setUp()
        self.product = self.env["product.product"].create({
            "name": "Shopee QA Import", "default_code": "SHOPEE-QA-IMPORT", "type": "product",
        })
        self.product.write({"shopee_stock": 4})

    def _import(self, content, filename="shopee_stock.csv"):
        wizard = self.env["shopee.stock.import.wizard"].create(
            {
                "file_name": filename,
                "file_data": base64.b64encode(content),
            }
        )
        wizard.action_import()

    def test_csv_updates_shopee_stock_only(self):
        on_hand = self.product.qty_available
        content = (
            "SKU,Available Stock\n%s,17\n" % self.product.default_code
        ).encode()

        self._import(content)
        self.product.invalidate_recordset()

        self.assertEqual(self.product.shopee_stock, 17)
        self.assertEqual(self.product.qty_available, on_hand)

    def test_unknown_sku_is_rejected_without_creating_products(self):
        product_count = self.env["product.product"].search_count([])
        content = b"SKU,Stock\nUNKNOWN-SHOPEE-SKU,3\n"

        with self.assertRaises(UserError):
            self._import(content)

        self.assertEqual(
            self.env["product.product"].search_count([]), product_count
        )

    def test_invalid_quantity_is_rejected(self):
        content = ("SKU,Stock\n%s,not-a-number\n" % self.product.default_code).encode()

        with self.assertRaises(UserError):
            self._import(content)

    def test_ambiguous_product_sku_is_rejected(self):
        self.env["product.product"].create({
            "name": "Duplicate QA SKU", "default_code": self.product.default_code,
        })
        with self.assertRaises(UserError):
            self._import(("SKU,Stock\n%s,99\n" % self.product.default_code).encode())
        self.assertEqual(self.product.shopee_stock, 4)

    def test_invalid_numbers_leave_stock_unchanged(self):
        for value in ("-1", "1.5", "NaN", "Infinity"):
            with self.subTest(value=value), self.assertRaises(UserError):
                self._import(("SKU,Stock\n%s,%s\n" % (self.product.default_code, value)).encode())
        self.assertEqual(self.product.shopee_stock, 4)

    def test_xlsx_updates_shopee_stock(self):
        if not openpyxl:
            self.skipTest("openpyxl is not installed")
        workbook = openpyxl.Workbook()
        worksheet = workbook.active
        worksheet.append(["Variation SKU", "Available Stock"])
        worksheet.append([self.product.default_code, 23])
        stream = io.BytesIO()
        workbook.save(stream)

        self._import(stream.getvalue(), "shopee_stock.xlsx")
        self.product.invalidate_recordset()

        self.assertEqual(self.product.shopee_stock, 23)
