from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase

from ..models.lazada_api import LazadaAPI


class TestLazadaPriceExport(TransactionCase):
    def setUp(self):
        super().setUp()
        self.config = self.env["lazada.config"].create({
            "name": "Test Seller Price",
            "region": "th",
            "app_key": "1000001",
            "app_secret": "testkey",
            "seller_id": "223",
            "access_token": "tok",
            "token_expires_at": "2999-01-01 00:00:00",
            "lazada_push_price": True,
        })
        self.product = self.env["product.product"].create({
            "name": "Lazada QA Price", "default_code": "LAZADA-QA-PRICE",
            "type": "product", "list_price": 100.0,
        })
        self.product.write({
            "lazada_item_id": "88",
            "lazada_sku_id": "1",
            "lazada_sync_price_out": True,
        })

    def test_push_price_calls_update_and_skips_unchanged(self):
        calls = []

        def _fake_update_price(self_api, token, price_list):
            calls.append(list(price_list))
            return {}

        with patch.object(LazadaAPI, "update_price", _fake_update_price):
            self.config._push_price_for_products(self.product)
            first = list(calls)
            # second run: pushed_price now equals lst_price -> skipped
            self.config._push_price_for_products(self.product)

        self.assertEqual(first, [[{
            "seller_sku": "LAZADA-QA-PRICE", "sku_id": "1", "item_id": "88", "price": 100.0,
        }]])
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.product.lazada_pushed_price, 100.0)
        self.assertTrue(self.product.lazada_price_push_date)

    def test_push_price_batches_variants_of_same_item(self):
        other = self.env["product.product"].create({
            "name": "Lazada QA Price 2", "default_code": "LAZADA-QA-PRICE-2",
            "type": "product", "list_price": 150.0,
        })
        other.write({
            "lazada_item_id": "88",
            "lazada_sku_id": "2",
            "lazada_sync_price_out": True,
        })
        calls = []

        def _fake_update_price(self_api, token, price_list):
            calls.append(list(price_list))
            return {}

        with patch.object(LazadaAPI, "update_price", _fake_update_price):
            pushed = self.config._push_price_for_products(self.product | other)

        self.assertEqual(pushed, 2)
        self.assertEqual(len(calls), 1)
        self.assertEqual(sorted(entry["sku_id"] for entry in calls[0]), ["1", "2"])

    def test_push_price_disabled_raises(self):
        self.config.lazada_push_price = False
        with self.assertRaises(UserError):
            self.config._push_price_for_products(self.product)
