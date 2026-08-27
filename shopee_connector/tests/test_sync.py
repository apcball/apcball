from unittest.mock import patch

from odoo.tests import TransactionCase

from ..models.shopee_api import ShopeeAPI


class TestShopeeSync(TransactionCase):
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
            "shopee_item_id": False,
            "shopee_model_id": False,
        })
        self.sku = self.product.default_code

        self.config = self.env["shopee.config"].create({
            "name": "Test Shop",
            "environment": "sandbox",
            "partner_id": "1000001",
            "partner_key": "testkey",
            "shop_id": "222",
            "access_token": "tok",
            "token_expires_at": "2999-01-01 00:00:00",
        })

    # ------------------------------------------------------------------
    def test_sync_stock_model_level(self):
        item_list = {"response": {"item": [{"item_id": 55}], "has_next_page": False}}
        base_info = {"response": {"item_list": [
            {"item_id": 55, "has_model": True, "item_sku": ""}
        ]}}
        model_list = {"response": {"model": [
            {
                "model_id": 900,
                "model_sku": self.sku,
                "stock_info_v2": {"summary_info": {"total_available_stock": 7}},
            }
        ]}}
        with patch.object(ShopeeAPI, "get_item_list", return_value=item_list), \
             patch.object(ShopeeAPI, "get_item_base_info", return_value=base_info), \
             patch.object(ShopeeAPI, "get_model_list", return_value=model_list):
            updated = self.config.action_sync_stock()

        self.assertEqual(updated, 1)
        self.assertEqual(self.product.shopee_item_id, "55")
        self.assertEqual(self.product.shopee_model_id, "900")
        self.assertEqual(self.product.shopee_stock, 7)

    def test_create_from_shopee_draft_order(self):
        customer = self.env["res.partner"].search(
            [("customer_rank", ">", 0)], limit=1
        ) or self.env["res.partner"].search([], limit=1)
        order = self.env["sale.order"].create_from_shopee({
            "order_sn": "TEST-SN-001",
            "order_status": "READY_TO_SHIP",
            "buyer_username": "unittest_buyer",
            "recipient_address": {
                "name": "Rec Name", "phone": "0800000000",
                "full_address": "1 Road", "city": "BKK",
                "state": "BKK", "zipcode": "10000", "region": "TH",
            },
            "item_list": [{
                "item_name": "Widget",
                "model_sku": self.sku,
                "model_quantity_purchased": 3,
                "model_discounted_price": 12.5,
            }],
        }, partner=customer)
        self.assertTrue(order.is_shopee_order)
        self.assertEqual(order.partner_id, customer)
        self.assertEqual(order.client_order_ref, "unittest_buyer")
        self.assertEqual(order.state, "draft")
        self.assertEqual(order.shopee_order_sn, "TEST-SN-001")
        self.assertEqual(len(order.order_line), 1)
        self.assertEqual(order.order_line.product_uom_qty, 3)
        self.assertEqual(order.order_line.price_unit, 12.5)
        self.assertEqual(order.order_line.product_id, self.product)

    def test_push_stock_calls_update_and_skips_unchanged(self):
        self.config.write({"shopee_push_stock": True})
        self.product.write({
            "shopee_item_id": "55",
            "shopee_model_id": "900",
            "shopee_sync_stock_out": True,
            "shopee_pushed_stock": 0,
            "shopee_stock_push_date": False,
        })
        calls = []

        def _fake_update(self_api, token, item_id, model_id, qty):
            calls.append((item_id, model_id, qty))
            return {"response": {}}

        with patch.object(ShopeeAPI, "update_stock", _fake_update):
            self.config._push_stock_for_products(self.product)
            first = list(calls)
            # second run: pushed_stock now equals free_qty -> skipped
            self.config._push_stock_for_products(self.product)

        self.assertEqual(len(first), 1)
        self.assertEqual(first[0][0], 55)
        self.assertEqual(first[0][1], 900)
        self.assertEqual(len(calls), 1)
        self.assertTrue(self.product.shopee_stock_push_date)
