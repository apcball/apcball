import base64
import io

import openpyxl

from odoo.tests import TransactionCase


class TestShopeeMappingImport(TransactionCase):
    def setUp(self):
        super().setUp()
        self.config = self.env["shopee.config"].search([], limit=1) or self.env[
            "shopee.config"].create({"name": "Test Shop"})
        Product = self.env["product.product"]
        self.p1 = Product.create({"name": "MI 1", "default_code": "MI-REF-1"})
        self.p2 = Product.create({"name": "MI 2", "default_code": "MI-REF-2"})
        self.Mapping = self.env["shopee.product.mapping"]

    def _run(self, rows, dry_run=False):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Shopee Config", "Shopee Model ID", "Shopee SKU", "Shopee Item ID",
                   "Shopee Item Name", "Internal Reference", "Shopee Available Stock",
                   "Refill When Shopee Stock Below", "Active"])
        for r in rows:
            ws.append(r)
        buf = io.BytesIO()
        wb.save(buf)
        wiz = self.env["shopee.product.mapping.import.wizard"].create({
            "shopee_config_id": self.config.id, "file_name": "m.xlsx",
            "file_data": base64.b64encode(buf.getvalue()), "dry_run": dry_run,
        })
        wiz.action_import()
        return wiz

    def _map(self, **dom):
        return self.Mapping.with_context(active_test=False).search(
            [("shopee_config_id", "=", self.config.id)] + [(k, "=", v) for k, v in dom.items()])

    def test_create_item_and_model_rows_strip_ref(self):
        self._run([
            ["x", None, "S1", 9001, "Item", "\nMI-REF-1", 5, 10, True],
            ["x", 777, "S2", 9002, "Item2", "MI-REF-2", 5, 10, True],
        ])
        self.assertEqual(self._map(shopee_sku="S1").product_id, self.p1)
        m = self._map(shopee_sku="S2")
        self.assertEqual((m.product_id, m.shopee_model_id, m.shopee_item_id), (self.p2, "777", "9002"))

    def test_updates_existing_unmapped_and_sku_fallback(self):
        a = self.Mapping.create({"shopee_config_id": self.config.id, "shopee_item_id": "9100", "shopee_sku": "A"})
        b = self.Mapping.create({"shopee_config_id": self.config.id, "shopee_sku": "B"})
        self._run([["x", None, "A", 9100, "n", "MI-REF-1", 0, 10, True],
                   ["x", None, "B", None, "n", "MI-REF-2", 0, 10, True]])
        self.assertEqual(a.product_id, self.p1)
        self.assertEqual(b.product_id, self.p2)

    def test_missing_product_skipped_and_reported(self):
        wiz = self._run([["x", None, "S3", 9003, "n", "NOPE-REF", 0, 10, True]])
        self.assertFalse(self._map(shopee_sku="S3"))
        self.assertIn("NOPE-REF", wiz.result)

    def test_conflict_not_overwritten(self):
        m = self.Mapping.create({"shopee_config_id": self.config.id, "shopee_sku": "C",
                                 "shopee_item_id": "9200", "product_id": self.p1.id})
        wiz = self._run([["x", None, "C", 9200, "n", "MI-REF-2", 0, 10, True]])
        self.assertEqual(m.product_id, self.p1)
        self.assertIn("already mapped", wiz.result)

    def test_dry_run_writes_nothing(self):
        wiz = self._run([["x", None, "D", 9300, "n", "MI-REF-1", 0, 10, True]], dry_run=True)
        self.assertFalse(self._map(shopee_sku="D"))
        self.assertIn("DRY RUN", wiz.result)
