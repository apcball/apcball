from datetime import datetime, timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase

from ..models.lazada_api import LazadaAPI, LazadaAPIError


class TestLazadaSync(TransactionCase):
    def setUp(self):
        super().setUp()
        finance = patch.object(LazadaAPI, "get_finance_transactions", return_value=[])
        finance.start()
        self.addCleanup(finance.stop)
        self.product = self.env["product.product"].create({
            "name": "Lazada QA Widget", "default_code": "LAZADA-QA-SYNC", "type": "product",
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

    def _order_api(self, status="pending"):
        """Patch the order endpoints with one item of ``self.sku``."""
        def _get_order(self_api, token, order_id):
            return {"order_id": str(order_id), "statuses": [status],
                    "customer_first_name": "QA", "customer_last_name": "Buyer"}

        items = [{"sku": self.sku, "name": "Widget", "item_price": 10}]
        return (patch.object(LazadaAPI, "get_order", _get_order),
                patch.object(LazadaAPI, "get_order_items", return_value=items))

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
        mapping = self.env["lazada.product.mapping"].search([
            ("lazada_config_id", "=", self.config.id),
            ("seller_sku", "=", self.sku),
        ])
        self.assertEqual(mapping.product_id, self.product)
        self.assertEqual(mapping.lazada_stock, 7)
        self.assertTrue(mapping.last_stock_sync)
        self.assertEqual(self.config.last_stock_sync_unmapped, 0)

    def test_sync_stock_prefers_available_quantity(self):
        products = {"products": [{
            "item_id": 55,
            "skus": [{
                "SellerSku": self.sku, "SkuId": 900,
                "quantity": 10, "Available": 4,
            }],
        }]}
        with patch.object(LazadaAPI, "get_products", return_value=products):
            self.config.action_sync_stock()
        self.assertEqual(self.product.lazada_stock, 4)

    def test_find_product_by_sku_ignores_case_and_whitespace(self):
        self.product.default_code = "Lazada-Variant-%s" % self.product.id
        product = self.env["lazada.product.mapping"].find_product_by_sku(
            "  lazada-variant-%s  " % self.product.id
        )
        self.assertEqual(product, self.product)

    def test_sync_stock_creates_pending_mapping_for_unknown_sku(self):
        products = {"products": [{
            "item_id": 55,
            "attributes": {"name": "Test item"},
            "skus": [{
                "SellerSku": "UNKNOWN-LAZADA-SKU-%s" % self.product.id,
                "SkuId": 901, "Available": 7,
                "saleProp": {"color_family": "Blue"},
            }],
        }]}
        with patch.object(LazadaAPI, "get_products", return_value=products):
            updated = self.config.action_sync_stock()

        mapping = self.env["lazada.product.mapping"].search([
            ("lazada_config_id", "=", self.config.id),
            ("lazada_item_id", "=", "55"),
            ("lazada_sku_id", "=", "901"),
        ])
        self.assertEqual(updated, 0)
        self.assertEqual(self.config.last_stock_sync_unmapped, 1)
        self.assertFalse(mapping.product_id)
        self.assertEqual(mapping.lazada_item_name, "Test item")
        self.assertEqual(mapping.lazada_sku_name, "Blue")
        self.assertEqual(mapping.lazada_stock, 7)

    def test_sync_orders_window_continues_from_previous_end(self):
        calls = []

        def _fake_orders(self_api, token, created_after, created_before=None,
                         offset=0, limit=50):
            calls.append((created_after, created_before))
            return {"orders": []}

        self.config.last_order_sync = datetime(2026, 1, 1, 0, 0, 0)
        with patch.object(LazadaAPI, "get_orders", _fake_orders):
            self.config.action_sync_orders()
            self.config.action_sync_orders()

        self.assertEqual(calls[0][0], datetime(2026, 1, 1, 0, 0, 0))
        self.assertEqual(calls[-1][0], calls[-2][1])
        self.assertEqual(self.config.last_order_sync, calls[-1][1])

    def test_create_from_lazada_draft_order(self):
        self.config.lazada_price_vat_rate = 0  # keep Lazada's price as-is here
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
                "city": "BKK", "region": "BKK", "post_code": "10000",
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
        self.assertEqual(so.client_order_ref, "TEST-ORDER-001")
        self.assertEqual(so.state, "draft")
        self.assertEqual(so.lazada_order_id, "TEST-ORDER-001")
        self.assertEqual(so.lazada_order_status, "pending")
        self.assertEqual(len(so.order_line), 1)
        self.assertEqual(so.order_line.product_uom_qty, 3)
        self.assertEqual(so.order_line.price_unit, 12.5)
        self.assertEqual(so.order_line.product_id, self.product)

    def test_import_orders_from_backfills_in_windows(self):
        get_order, get_items = self._order_api("shipped")
        with get_order, get_items:
            existing = self.env["sale.order"].create_from_lazada(
                "BACKFILL-EXISTING", config=self.config)
        self.config.import_orders_from = fields.Datetime.now() - timedelta(days=20)
        windows = []

        def _fake_orders(self_api, token, created_after, created_before=None,
                         offset=0, limit=50):
            windows.append((created_after, created_before))
            ids = ["BACKFILL-EXISTING", "BACKFILL-NEW"] if len(windows) == 1 else []
            return {"orders": [{"order_id": order_id} for order_id in ids]}

        get_order, get_items = self._order_api("shipped")
        with patch.object(LazadaAPI, "get_orders", _fake_orders), get_order, get_items:
            created = self.config.action_sync_orders()

        self.assertEqual(created, 1)
        self.assertEqual(len(windows), 2)
        for created_after, created_before in windows:
            self.assertLessEqual(created_before - created_after, timedelta(days=15))
        self.assertEqual(windows[0][1], windows[1][0])
        self.assertFalse(self.config.import_orders_from)
        self.assertEqual(self.env["sale.order"].search_count([
            ("lazada_order_id", "=", "BACKFILL-EXISTING"),
        ]), 1)
        self.assertTrue(existing.exists())

    def test_order_sync_wizard_imports_and_syncs(self):
        wizard = self.env["lazada.order.sync.wizard"].create({
            "config_id": self.config.id,
            "import_orders_from": fields.Datetime.now() - timedelta(days=3),
        })

        def _fake_orders(self_api, token, created_after, created_before=None,
                         offset=0, limit=50):
            return {"orders": [{"order_id": "WIZ-1"}]}

        get_order, get_items = self._order_api("shipped")
        with patch.object(LazadaAPI, "get_orders", _fake_orders), get_order, get_items:
            wizard.action_import_orders()

        self.assertEqual(wizard.state, "done")
        self.assertIn("1 new order(s)", wizard.result_message)
        self.assertFalse(self.config.import_orders_from)  # cleared by the sync
        order = self.env["sale.order"].search([("lazada_order_id", "=", "WIZ-1")])
        self.assertEqual(len(order), 1)

        wizard.state = "draft"
        get_order, get_items = self._order_api("delivered")
        with get_order, get_items:
            wizard.action_sync_status()
        self.assertIn("1 order(s)", wizard.result_message)
        self.assertEqual(order.lazada_order_status, "delivered")

    # ------------------------------------------------------------------
    # Stock push
    # ------------------------------------------------------------------
    def _capture_pushes(self, callback):
        calls = []

        def _fake_batch(self_api, token, stock_list):
            calls.extend(row["quantity"] for row in stock_list)
            return {}

        with patch.object(LazadaAPI, "update_stock_batch", _fake_batch):
            callback()
        return calls

    def _refill_setup(self, lazada_stock, refill_below, sync_out=True):
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.config.company_id.id)], limit=1
        )
        if not warehouse:
            self.skipTest("No warehouse available")
        self.config.write({"lazada_push_stock": True, "lazada_warehouse_id": warehouse.id})
        self.product.write({"lazada_sync_stock_out": sync_out})
        mapping = self.env["lazada.product.mapping"].upsert(
            self.config, self.sku, self.product,
            item_id="77", sku_id="701", lazada_stock=lazada_stock,
        )
        mapping.refill_below = refill_below
        return mapping, warehouse

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

        def _fake_batch(self_api, token, stock_list):
            calls.append(list(stock_list))
            return {}

        with patch.object(LazadaAPI, "update_stock_batch", _fake_batch):
            self.config._push_stock_for_products(self.product)
            first = list(calls)
            # second run: pushed qty equals free_qty and Lazada stock -> skipped
            self.config._push_stock_for_products(self.product)

        self.assertEqual(len(first), 1)
        row = first[0][0]
        self.assertEqual(
            (row["seller_sku"], row["sku_id"], row["item_id"]),
            (self.sku, "900", "55"),
        )
        self.assertEqual(len(calls), 1)
        self.assertTrue(self.product.lazada_stock_push_date)

    def test_push_stock_batches_variants_of_same_item(self):
        self.config.write({"lazada_push_stock": True})
        other = self.env["product.product"].create({
            "name": "Lazada QA Widget 2", "default_code": "LAZADA-QA-SYNC-2",
            "type": "product",
        })
        for product, sku_id in ((self.product, "900"), (other, "901")):
            product.write({"lazada_item_id": "55", "lazada_sku_id": sku_id,
                           "lazada_sync_stock_out": True})
        calls = []

        def _fake_batch(self_api, token, stock_list):
            calls.append(list(stock_list))
            return {}

        with patch.object(LazadaAPI, "update_stock_batch", _fake_batch):
            pushed = self.config._push_stock_for_products(self.product | other)

        self.assertEqual(pushed, 2)
        self.assertEqual(len(calls), 1)
        self.assertEqual(sorted(row["sku_id"] for row in calls[0]), ["900", "901"])

    def test_push_again_when_lazada_stock_drifts(self):
        self.config.write({"lazada_push_stock": True})
        self.product.write({
            "lazada_item_id": "55", "lazada_sku_id": "900",
            "lazada_sync_stock_out": True,
        })
        calls = self._capture_pushes(lambda: self.config._push_stock_for_products(self.product))
        # Lazada sold some units: the pull reports a different number.
        self.product.lazada_stock = self.product.lazada_pushed_stock + 3
        calls += self._capture_pushes(lambda: self.config._push_stock_for_products(self.product))
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0], calls[1])

    def test_stock_location_must_belong_to_warehouse(self):
        warehouses = self.env["stock.warehouse"].search(
            [("company_id", "=", self.config.company_id.id)], limit=2
        )
        if len(warehouses) < 2:
            warehouses |= self.env["stock.warehouse"].create({
                "name": "Lazada QA Second Warehouse", "code": "LQ2",
                "company_id": self.config.company_id.id,
            })
        with self.assertRaises(ValidationError):
            self.config.write({
                "lazada_warehouse_id": warehouses[0].id,
                "lazada_stock_location_id": warehouses[1].lot_stock_id.id,
            })

    def test_push_stock_uses_selected_location(self):
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.config.company_id.id)], limit=1
        )
        if not warehouse:
            self.skipTest("No warehouse available")
        location = warehouse.lot_stock_id
        self.config.write({
            "lazada_push_stock": True,
            "lazada_warehouse_id": warehouse.id,
            "lazada_stock_location_id": location.id,
        })
        self.product.write({
            "lazada_item_id": "55", "lazada_sku_id": "900",
            "lazada_sync_stock_out": True,
        })
        calls = self._capture_pushes(lambda: self.config._push_stock_for_products(self.product))
        expected = int(max(self.product.with_context(location=location.id).free_qty, 0))
        self.assertEqual(calls, [expected])

    def test_refill_threshold_skips_until_lazada_runs_low(self):
        mapping, warehouse = self._refill_setup(lazada_stock=15, refill_below=10)
        calls = self._capture_pushes(
            lambda: self.config._push_stock_for_products(self.product))
        self.assertEqual(calls, [])

        mapping.lazada_stock = 5
        calls = self._capture_pushes(
            lambda: self.config._push_stock_for_products(self.product))
        expected = int(max(
            self.product.with_context(warehouse=warehouse.id).free_qty, 0))
        self.assertEqual(calls, [expected])
        self.assertEqual(mapping.odoo_available_stock, expected)

    def test_mapping_button_forces_push(self):
        mapping, _warehouse = self._refill_setup(
            lazada_stock=500, refill_below=10, sync_out=False)
        calls = self._capture_pushes(mapping.action_push_odoo_stock)
        self.assertEqual(calls, [mapping.odoo_available_stock])
        self.assertEqual(mapping.last_pushed_stock, mapping.odoo_available_stock)

    def test_manual_odoo_available_stock_is_pushed(self):
        mapping, _warehouse = self._refill_setup(lazada_stock=500, refill_below=0)
        real = mapping.odoo_free_qty
        mapping.odoo_available_stock = real + 25
        self.assertTrue(mapping.use_stock_override)
        calls = self._capture_pushes(mapping.action_push_odoo_stock)
        self.assertEqual(calls, [real + 25])

        mapping.action_reset_stock_override()
        self.assertEqual(mapping.odoo_available_stock, real)
        calls = self._capture_pushes(mapping.action_push_odoo_stock)
        self.assertEqual(calls, [real])

    def test_editing_lazada_stock_does_not_push(self):
        mapping, _warehouse = self._refill_setup(lazada_stock=500, refill_below=0)
        calls = self._capture_pushes(lambda: mapping.write({"lazada_stock": 7}))
        self.assertEqual(calls, [])
        self.assertEqual(mapping.lazada_stock, 7)

    def test_partial_stock_failure_preserves_success_and_retry_is_not_duplicated(self):
        mapping, _warehouse = self._refill_setup(lazada_stock=500, refill_below=0)
        other = self.env["product.product"].create({
            "name": "QA failed stock", "default_code": "QA-FAILED-STOCK",
            "type": "product", "lazada_sync_stock_out": True,
        })
        failed = self.env["lazada.product.mapping"].upsert(
            self.config, "QA-FAILED-STOCK", other, item_id="88", sku_id="881",
            lazada_stock=500,
        )

        def _fake_batch(self_api, token, stock_list):
            if any(row["item_id"] == "88" for row in stock_list):
                raise LazadaAPIError("temporary", "Try later")
            return {}

        with patch.object(LazadaAPI, "update_stock_batch", _fake_batch):
            self.assertEqual(self.config._push_stock_for_products(), 1)
            queue = self.env["lazada.retry.queue"].search([("lazada_config_id", "=", self.config.id)])
            self.assertEqual(len(queue), 1)
            queue._run_one()
        self.assertTrue(mapping.last_stock_push)
        self.assertFalse(failed.last_stock_push)
        self.assertEqual(queue.state, "pending")
        self.assertEqual(self.env["lazada.retry.queue"].search_count([
            ("lazada_config_id", "=", self.config.id),
        ]), 1)
