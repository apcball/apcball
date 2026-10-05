from unittest.mock import patch

from odoo.tests import TransactionCase

from ..models.shopee_api import ShopeeAPI


class TestShopeePriceExport(TransactionCase):
    def setUp(self):
        super().setUp()
        self.config = self.env["shopee.config"].create({
            "name": "Test Shop Price",
            "environment": "sandbox",
            "partner_id": "1000001",
            "partner_key": "testkey",
            "shop_id": "223",
            "access_token": "tok",
            "token_expires_at": "2999-01-01 00:00:00",
            "shopee_push_price": True,
        })
        self.product = self.env["product.product"].create({
            "name": "Shopee QA Price", "default_code": "SHOPEE-QA-PRICE",
            "type": "product", "list_price": 100.0,
        })
        self.product.write({
            "shopee_item_id": "88",
            "shopee_model_id": "1",
            "shopee_sync_price_out": True,
        })

    def test_push_price_calls_update_and_skips_unchanged(self):
        calls = []

        def _fake_update_price(self_api, token, item_id, price_list):
            calls.append((item_id, list(price_list)))
            return {"response": {}}

        with patch.object(ShopeeAPI, "update_price", _fake_update_price):
            self.config._push_price_for_products(self.product)
            first = list(calls)
            # second run: pushed_price now equals lst_price -> skipped
            self.config._push_price_for_products(self.product)

        self.assertEqual(len(first), 1)
        self.assertEqual(first[0][0], 88)
        self.assertEqual(first[0][1], [{"model_id": 1, "original_price": 100.0}])
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.product.shopee_pushed_price, 100.0)
        self.assertTrue(self.product.shopee_price_push_date)

    def test_push_price_batches_variants_of_same_item(self):
        other = self.env["product.product"].create({
            "name": "Shopee QA Price 2", "default_code": "SHOPEE-QA-PRICE-2",
            "type": "product", "list_price": 150.0,
        })
        other.write({
            "shopee_item_id": "88",
            "shopee_model_id": "2",
            "shopee_sync_price_out": True,
        })
        calls = []

        def _fake_update_price(self_api, token, item_id, price_list):
            calls.append((item_id, list(price_list)))
            return {"response": {}}

        with patch.object(ShopeeAPI, "update_price", _fake_update_price):
            pushed = self.config._push_price_for_products(self.product | other)

        self.assertEqual(pushed, 2)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], 88)
        self.assertEqual(
            sorted(entry["model_id"] for entry in calls[0][1]), [1, 2]
        )

    def test_push_price_disabled_raises(self):
        self.config.shopee_push_price = False
        with self.assertRaises(Exception):
            self.config._push_price_for_products(self.product)
