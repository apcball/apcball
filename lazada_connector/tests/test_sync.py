from unittest.mock import patch

from odoo.tests import TransactionCase

from ..models.lazada_api import LazadaAPI


class TestLazadaSync(TransactionCase):
    def setUp(self):
        super().setUp()
        # Reuse an existing variant - creating product.product fails on MOG_DEV
        # (orphaned columns). Mutations are rolled back with the transaction.
        self.product = self.env["product.product"].search(
            [("default_code", "!=", False)], limit=1
        )
        if not self.product:
            self.skipTest("No product with an internal reference available")
        self.product.write({
            "lazada_item_id": False,
            "lazada_sku_id": False,
        })
        self.sku = self.product.default_code

        self.config = self.env["lazada.config"].create({
            "name": "Test Seller",
            "environment": "production",
            "region": "th",
            "app_key": "1000001",
            "app_secret": "testkey",
            "seller_id": "222",
            "access_token": "tok",
            "token_expires_at": "2999-01-01 00:00:00",
        })

    # ------------------------------------------------------------------
    def test_sync_stock_model_level(self):
        products = {"products": [{
            "item_id": 55,
            "skus": [{
                "SellerSku": self.sku,
                "SkuId": 900,
                "quantity": "7",
            }],
        }]}
        with patch.object(LazadaAPI, "get_products", return_value=products):
            updated = self.config.action_sync_stock()

        self.assertEqual(updated, 1)
        self.assertEqual(self.product.lazada_item_id, "55")
        self.assertEqual(self.product.lazada_sku_id, "900")
        self.assertEqual(self.product.lazada_stock, 7)

    def test_create_from_lazada_draft_order(self):
        customer = self.env["res.partner"].search(
            [("customer_rank", ">", 0)], limit=1
        ) or self.env["res.partner"].search([], limit=1)
        order = {
            "order_id": "TEST-ORDER-001",
            "statuses": ["pending"],
            "customer_first_name": "unittest",
            "customer_last_name": "buyer",
            "address_shipping": {
                "first_name": "Rec", "last_name": "Name",
                "phone": "0800000000", "address1": "1 Road",
                "city": "BKK", "region": "BKK", "postcode": "10000",
                "country": "TH",
            },
        }
        items = [{
            "sku": self.sku,
            "name": "Widget",
            "quantity": 3,
            "item_price": 12.5,
        }]
        with patch.object(LazadaAPI, "get_order", return_value=order), \
             patch.object(LazadaAPI, "get_order_items", return_value=items):
            so = self.env["sale.order"].create_from_lazada(
                "TEST-ORDER-001", partner=customer, config=self.config
            )

        self.assertTrue(so.is_lazada_order)
        self.assertEqual(so.partner_id, customer)
        self.assertEqual(so.client_order_ref, "unittest buyer")
        self.assertEqual(so.state, "draft")
        self.assertEqual(so.lazada_order_id, "TEST-ORDER-001")
        self.assertEqual(so.lazada_order_status, "pending")
        self.assertEqual(len(so.order_line), 1)
        self.assertEqual(so.order_line.product_uom_qty, 3)
        self.assertEqual(so.order_line.price_unit, 12.5)
        self.assertEqual(so.order_line.product_id, self.product)

    def test_push_stock_calls_update_and_skips_unchanged(self):
        self.config.write({"lazada_push_stock": True})
        self.product.write({
            "lazada_item_id": "55",
            "lazada_sku_id": "900",
            "lazada_sync_stock_out": True,
            "lazada_pushed_stock": 0,
            "lazada_stock_push_date": False,
        })
        calls = []

        def _fake_update(self_api, token, seller_sku, sku_id, qty):
            calls.append((seller_sku, sku_id, qty))
            return {}

        with patch.object(LazadaAPI, "update_stock", _fake_update):
            self.config._push_stock_for_products(self.product)
            first = list(calls)
            # second run: pushed_stock now equals free_qty -> skipped
            self.config._push_stock_for_products(self.product)

        self.assertEqual(len(first), 1)
        self.assertEqual(first[0][0], self.sku)
        self.assertEqual(first[0][1], "900")
        self.assertEqual(len(calls), 1)
        self.assertTrue(self.product.lazada_stock_push_date)
