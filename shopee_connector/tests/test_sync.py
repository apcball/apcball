from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase

from ..models.shopee_api import ShopeeAPI, ShopeeAPIError


class TestShopeeSync(TransactionCase):
    def setUp(self):
        super().setUp()
        escrow = patch.object(ShopeeAPI, "get_escrow_detail", return_value={"response": {}})
        escrow.start()
        self.addCleanup(escrow.stop)
        self.product = self.env["product.product"].create({
            "name": "Shopee QA Widget", "default_code": "SHOPEE-QA-SYNC", "type": "product",
        })
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
        mapping = self.env["shopee.product.mapping"].search([
            ("shopee_config_id", "=", self.config.id),
            ("shopee_sku", "=", self.sku),
        ])
        self.assertEqual(mapping.product_id, self.product)
        self.assertEqual(mapping.shopee_stock, 7)
        self.assertTrue(mapping.last_stock_sync)

    def test_find_product_by_sku_ignores_case_and_whitespace(self):
        self.product.default_code = "Shopee-Variant-%s" % self.product.id
        product = self.env["shopee.product.mapping"].find_product_by_sku(
            "  shopee-variant-%s  " % self.product.id
        )
        self.assertEqual(product, self.product)

    def test_sync_stock_creates_pending_mapping_without_variant_sku(self):
        item_list = {"response": {"item": [{"item_id": 55}], "has_next_page": False}}
        base_info = {"response": {"item_list": [
            {"item_id": 55, "item_name": "Test item", "has_model": True}
        ]}}
        model_list = {"response": {"model": [{
            "model_id": 900, "model_name": "Blue", "model_sku": "",
            "stock_info_v2": {"summary_info": {"total_available_stock": 7}},
        }]}}
        with patch.object(ShopeeAPI, "get_item_list", return_value=item_list), \
             patch.object(ShopeeAPI, "get_item_base_info", return_value=base_info), \
             patch.object(ShopeeAPI, "get_model_list", return_value=model_list):
            updated = self.config.action_sync_stock()

        mapping = self.env["shopee.product.mapping"].search([
            ("shopee_config_id", "=", self.config.id),
            ("shopee_item_id", "=", "55"),
            ("shopee_model_id", "=", "900"),
        ])
        self.assertEqual(updated, 0)
        self.assertEqual(self.config.last_stock_sync_unmapped, 1)
        self.assertFalse(mapping.product_id)
        self.assertEqual(mapping.shopee_item_name, "Test item")
        self.assertEqual(mapping.shopee_model_name, "Blue")
        self.assertEqual(mapping.shopee_stock, 7)

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
        self.assertEqual(order.client_order_ref, "TEST-SN-001")
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

        def _fake_update(self_api, token, item_id, model_id, qty,
                         location_id=None):
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

    # ------------------------------------------------------------------
    def _sgz_payloads(self, model_sku=""):
        item_list = {"response": {"item": [{"item_id": 55}], "has_next_page": False}}
        base_info = {"response": {"item_list": [
            {"item_id": 55, "item_name": "Test item", "has_model": True}
        ]}}
        model_list = {"response": {"model": [{
            "model_id": 12828758, "model_name": "blue", "model_sku": model_sku,
            "stock_info_v2": {
                "summary_info": {"total_available_stock": 55},
                "seller_stock": [{"location_id": "SGZ", "stock": 55}],
            },
        }]}}
        return item_list, base_info, model_list

    def _run_sync(self, payloads):
        item_list, base_info, model_list = payloads
        with patch.object(ShopeeAPI, "get_item_list", return_value=item_list), \
             patch.object(ShopeeAPI, "get_item_base_info", return_value=base_info), \
             patch.object(ShopeeAPI, "get_model_list", return_value=model_list):
            return self.config.action_sync_stock()

    def test_manual_mapping_without_sku_links_and_pushes_location(self):
        """SKU-less variant mapped by hand: pull links it, push sends SGZ."""
        self._run_sync(self._sgz_payloads())
        mapping = self.env["shopee.product.mapping"].search([
            ("shopee_config_id", "=", self.config.id),
            ("shopee_model_id", "=", "12828758"),
        ])
        self.assertEqual(mapping.shopee_location_id, "SGZ")
        mapping.product_id = self.product

        updated = self._run_sync(self._sgz_payloads())
        self.assertEqual(updated, 1)
        self.assertEqual(self.config.last_stock_sync_unmapped, 0)
        self.assertEqual(self.product.shopee_stock, 55)

        self.config.write({"shopee_push_stock": True})
        bodies = []

        def _fake_post(self_api, path, access_token, body=None, is_public=False):
            bodies.append(body)
            return {"response": {}}

        with patch.object(ShopeeAPI, "_post", _fake_post):
            self.config._push_stock_for_products(self.product)

        self.assertEqual(len(bodies), 1)
        entry = bodies[0]["stock_list"][0]
        self.assertEqual(entry["model_id"], 12828758)
        self.assertEqual(entry["seller_stock"][0]["location_id"], "SGZ")

    def test_upsert_reuses_sku_only_mapping(self):
        """A hand-made SKU-only mapping must not break the pull."""
        Mapping = self.env["shopee.product.mapping"]
        manual = Mapping.create({
            "shopee_config_id": self.config.id,
            "shopee_sku": "MANUAL-SKU-X",
            "product_id": self.product.id,
        })
        self._run_sync(self._sgz_payloads(model_sku="MANUAL-SKU-X"))
        mappings = Mapping.search([
            ("shopee_config_id", "=", self.config.id),
            ("shopee_sku", "=", "MANUAL-SKU-X"),
        ])
        self.assertEqual(mappings, manual)
        self.assertEqual(manual.shopee_item_id, "55")
        self.assertEqual(manual.shopee_model_id, "12828758")
        self.assertEqual(self.product.shopee_stock, 55)

    def test_push_again_when_shopee_stock_drifts(self):
        self.config.write({"shopee_push_stock": True})
        self.product.write({
            "shopee_item_id": "55",
            "shopee_model_id": "900",
            "shopee_sync_stock_out": True,
        })
        calls = []

        def _fake_update(self_api, token, item_id, model_id, qty,
                         location_id=None):
            calls.append(qty)
            return {"response": {}}

        with patch.object(ShopeeAPI, "update_stock", _fake_update):
            self.config._push_stock_for_products(self.product)
            # Shopee sold some units: the pull reports a different number.
            self.product.shopee_stock = self.product.shopee_pushed_stock + 3
            self.config._push_stock_for_products(self.product)

        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0], calls[1])

    def test_stock_location_must_belong_to_warehouse(self):
        warehouses = self.env["stock.warehouse"].search(
            [("company_id", "=", self.config.company_id.id)], limit=2
        )
        if len(warehouses) < 2:
            warehouses |= self.env["stock.warehouse"].create({
                "name": "Shopee QA Second Warehouse", "code": "SQ2",
                "company_id": self.config.company_id.id,
            })
        with self.assertRaises(ValidationError):
            self.config.write({
                "shopee_warehouse_id": warehouses[0].id,
                "shopee_stock_location_id": warehouses[1].lot_stock_id.id,
            })

    def test_push_stock_uses_selected_location(self):
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.config.company_id.id)], limit=1
        )
        if not warehouse:
            self.skipTest("No warehouse available")
        location = warehouse.lot_stock_id
        self.config.write({
            "shopee_push_stock": True,
            "shopee_warehouse_id": warehouse.id,
            "shopee_stock_location_id": location.id,
        })
        self.product.write({
            "shopee_item_id": "55",
            "shopee_model_id": "900",
            "shopee_sync_stock_out": True,
            "shopee_stock_push_date": False,
        })
        calls = []

        def _fake_update(self_api, token, item_id, model_id, qty,
                         location_id=None):
            calls.append(qty)
            return {"response": {}}

        with patch.object(ShopeeAPI, "update_stock", _fake_update):
            self.config._push_stock_for_products(self.product)

        expected = int(max(
            self.product.with_context(location=location.id).free_qty, 0
        ))
        self.assertEqual(calls, [expected])

    # ------------------------------------------------------------------
    def test_masked_buyer_gets_no_company_data(self):
        company_partner = self.config.company_id.partner_id
        company_partner.with_context(skip_partner_required_fields=True).write({
            "street": "1 Company Rd", "city": "Bang Rak", "zip": "10500",
            "phone": "021234567", "email": "contact@example.com",
        })
        partner = self.env["res.partner"].find_or_create_shopee_buyer(
            self.config,
            {
                "order_sn": "MASKED-1",
                "buyer_user_id": 991,
                "buyer_username": "naokibee",
                "recipient_address": {
                    "name": "*****", "phone": "******78", "full_address": "****",
                    "city": "****", "zipcode": "****", "state": "****",
                    "region": "****",
                },
                "region": "TH",
            },
        )
        self.assertEqual(partner.name, "naokibee")
        self.assertEqual(partner.country_id, self.env.ref("base.th"))
        for field_name in ("street", "street2", "city", "zip", "state_id",
                           "phone", "email"):
            self.assertFalse(partner[field_name], field_name)

    def test_real_thai_address_is_mapped(self):
        thailand = self.env.ref("base.th")
        state = self.env["res.country.state"].search(
            [("country_id", "=", thailand.id)], limit=1
        )
        if not state:
            self.skipTest("No Thai provinces loaded")
        partner = self.env["res.partner"].find_or_create_shopee_buyer(
            self.config,
            {
                "order_sn": "REAL-1",
                "buyer_user_id": 992,
                "recipient_address": {
                    "name": "Somchai", "phone": "0812345678",
                    "full_address": "99 Sukhumvit", "district": "Khlong Toei",
                    "city": "Bangkok", "zipcode": "10110",
                    "state": state.name, "region": "TH",
                },
            },
        )
        self.assertEqual(partner.name, "Somchai")
        self.assertEqual(partner.street, "99 Sukhumvit")
        self.assertEqual(partner.street2, "Khlong Toei")
        self.assertEqual(partner.country_id, thailand)
        self.assertEqual(partner.state_id, state)
        self.assertEqual(partner.phone, "0812345678")

    def test_masked_update_keeps_real_buyer_data(self):
        Partner = self.env["res.partner"]
        order = {
            "order_sn": "KEEP-1", "buyer_user_id": 993,
            "recipient_address": {"name": "Real Name", "phone": "0899999999",
                                  "full_address": "5 Real St", "region": "TH"},
        }
        partner = Partner.find_or_create_shopee_buyer(self.config, order)
        masked = dict(order, recipient_address={
            "name": "****", "phone": "****", "full_address": "****", "region": "TH",
        })
        same = Partner.find_or_create_shopee_buyer(self.config, masked)
        self.assertEqual(same, partner)
        self.assertEqual(partner.name, "Real Name")
        self.assertEqual(partner.street, "5 Real St")
        self.assertEqual(partner.phone, "0899999999")

    def test_clear_company_copies(self):
        company = self.config.company_id
        company.partner_id.with_context(skip_partner_required_fields=True).write({
            "street": "1 Company Rd", "phone": "021234567",
            "email": "contact@example.com",
        })
        buyer = self.env["res.partner"].with_context(
            skip_partner_required_fields=True
        ).create({
            "name": "naokibee", "shopee_config_id": self.config.id,
            "shopee_buyer_id": "994", "street": "1 Company Rd",
            "phone": "021234567", "email": "contact@example.com",
            "city": "Real City",
        })
        self.env["res.partner"]._shopee_clear_company_copies()
        self.assertFalse(buyer.street)
        self.assertFalse(buyer.phone)
        self.assertFalse(buyer.email)
        self.assertEqual(buyer.city, "Real City")

    # ------------------------------------------------------------------
    def test_trade_channel_set_on_import_and_backfill(self):
        SaleOrder = self.env["sale.order"]
        if not SaleOrder._shopee_trade_channel_values():
            self.skipTest("marketplace_settlement 'shopee' channel not available")
        customer = self.env["res.partner"].search([], limit=1)
        order = SaleOrder.create_from_shopee({
            "order_sn": "TEST-SN-CHANNEL",
            "item_list": [{"item_name": "Widget", "model_sku": self.sku}],
        }, partner=customer)
        self.assertEqual(order.trade_channel, "shopee")

        order.trade_channel = False
        SaleOrder._shopee_backfill_trade_channel()
        self.assertEqual(order.trade_channel, "shopee")

    # ------------------------------------------------------------------
    def test_cancelled_shopee_order_imported_as_cancelled(self):
        customer = self.env["res.partner"].search([], limit=1)
        order = self.env["sale.order"].create_from_shopee({
            "order_sn": "TEST-SN-CANCELLED",
            "order_status": "CANCELLED",
            "item_list": [{"item_name": "Widget", "model_sku": self.sku}],
        }, partner=customer)
        self.assertEqual(order.state, "cancel")

    def test_status_sync_cancels_open_quotation(self):
        customer = self.env["res.partner"].search([], limit=1)
        order = self.env["sale.order"].create_from_shopee({
            "order_sn": "TEST-SN-LATER-CANCEL",
            "order_status": "READY_TO_SHIP",
            "item_list": [{"item_name": "Widget", "model_sku": self.sku}],
        }, partner=customer)
        self.assertEqual(order.state, "draft")
        order.update_shopee_status("CANCELLED")
        self.assertEqual(order.state, "cancel")

    def test_status_sync_fills_address_once_unmasked(self):
        masked = {
            "order_sn": "TEST-SN-UNMASK", "order_status": "UNPAID",
            "buyer_user_id": 995, "buyer_username": "465twj8odj", "region": "TH",
            "recipient_address": {"name": "****", "phone": "****",
                                  "full_address": "****", "region": "****"},
            "item_list": [{"item_name": "Widget", "model_sku": self.sku}],
        }
        order = self.env["sale.order"].create_from_shopee(masked, config=self.config)
        self.assertFalse(order.partner_id.street)

        paid = dict(masked, order_status="READY_TO_SHIP", recipient_address={
            "name": "เค้ก", "phone": "66644976555",
            "full_address": "เลขที่ 63/50 หมู่ที่ 5 ตำบลบ่อผุด",
            "district": "เกาะสมุย", "city": "บ่อผุด", "zipcode": "84320",
            "state": "จังหวัดสุราษฎร์ธานี", "region": "TH",
        })
        order.apply_shopee_detail(paid)
        partner = order.partner_id
        self.assertEqual(order.shopee_order_status, "READY_TO_SHIP")
        self.assertEqual(partner.name, "เค้ก")
        self.assertEqual(partner.phone, "0644976555")
        self.assertEqual(partner.street, "เลขที่ 63/50 หมู่ที่ 5")
        self.assertEqual(partner.zip, "84320")

    def test_thai_phone_format(self):
        to_thai = self.env["res.partner"]._shopee_thai_phone
        self.assertEqual(to_thai("66819283179"), "0819283179")
        self.assertEqual(to_thai("+66 81 928 3179"), "0819283179")
        self.assertEqual(to_thai("0819283179"), "0819283179")
        self.assertEqual(to_thai("021509710"), "021509710")

    def test_price_excludes_vat(self):
        self.assertEqual(self.config.shopee_price_vat_rate, 7.0)
        order = self.env["sale.order"].create_from_shopee({
            "order_sn": "TEST-SN-VAT", "buyer_user_id": 996, "region": "TH",
            "item_list": [{"item_name": "Widget", "model_sku": self.sku,
                           "model_discounted_price": 963.0}],
        }, config=self.config)
        self.assertAlmostEqual(order.order_line.price_unit, 900.0, places=2)

    def test_commitment_date_follows_cutoff(self):
        import pytz
        from datetime import datetime
        SaleOrder = self.env["sale.order"].with_user(self.env.user)
        self.env.user.tz = "Asia/Bangkok"
        bkk = pytz.timezone("Asia/Bangkok")
        before = bkk.localize(datetime(2026, 9, 21, 13, 59))
        after = bkk.localize(datetime(2026, 9, 21, 14, 0))
        # 14:00 Bangkok = 07:00 UTC
        self.assertEqual(
            SaleOrder._shopee_commitment_date(before, self.config),
            datetime(2026, 9, 21, 7, 0),
        )
        self.assertEqual(
            SaleOrder._shopee_commitment_date(after, self.config),
            datetime(2026, 9, 22, 7, 0),
        )
        self.assertEqual(
            SaleOrder._shopee_commitment_date(int(before.timestamp()), self.config),
            datetime(2026, 9, 21, 7, 0),
        )

    def test_import_orders_from_backfills_in_windows(self):
        from datetime import timedelta
        from odoo import fields as odoo_fields

        existing = self.env["sale.order"].create_from_shopee({
            "order_sn": "BACKFILL-EXISTING", "buyer_user_id": 997,
            "item_list": [{"item_name": "Widget", "model_sku": self.sku}],
        }, config=self.config)
        self.config.import_orders_from = odoo_fields.Datetime.now() - timedelta(days=20)
        windows = []

        def _fake_list(self_api, token, time_from, time_to, cursor=""):
            windows.append((time_from, time_to))
            sns = ["BACKFILL-EXISTING", "BACKFILL-NEW"] if len(windows) == 1 else []
            return {"response": {"order_list": [{"order_sn": sn} for sn in sns],
                                 "more": False}}

        def _fake_detail(self_api, token, order_sns):
            return {"response": {"order_list": [{
                "order_sn": sn, "buyer_user_id": 998, "order_status": "SHIPPED",
                "item_list": [{"item_name": "Widget", "model_sku": self.sku}],
            } for sn in order_sns]}}

        with patch.object(ShopeeAPI, "get_order_list", _fake_list), \
             patch.object(ShopeeAPI, "get_order_detail", _fake_detail):
            created = self.config.action_sync_orders()

        self.assertEqual(created, 1)
        self.assertEqual(len(windows), 2)
        for time_from, time_to in windows:
            self.assertLessEqual(time_to - time_from, 15 * 24 * 3600)
        self.assertEqual(windows[0][1], windows[1][0])
        self.assertFalse(self.config.import_orders_from)
        self.assertEqual(self.env["sale.order"].search_count([
            ("shopee_order_sn", "=", "BACKFILL-EXISTING"),
        ]), 1)
        self.assertTrue(existing.exists())

    def test_apply_payment_adds_shipping_voucher_and_fee_note(self):
        order = self.env["sale.order"].create_from_shopee({
            "order_sn": "TEST-SN-PAY", "buyer_user_id": 999, "region": "TH",
            "buyer_username": "phai5987",
            "item_list": [{"item_name": "Widget", "model_sku": self.sku,
                           "model_discounted_price": 5590.0}],
        }, config=self.config)
        payment = {
            "source": "escrow", "products_total": 5590.0, "shipping": 200.0,
            "voucher_amount": 10.0, "voucher_codes": ["MOGEN083"],
            "commission": 1075.0, "service_fee": 478.0, "infra_fee": 1.0,
            "transaction_fee": 186.0, "net_income": 4040.0,
        }
        order._shopee_apply_payment(payment)
        order._shopee_apply_payment(payment)  # re-apply replaces, never adds

        shipping = order.order_line.filtered(lambda l: l.shopee_line_type == "shipping")
        voucher = order.order_line.filtered(lambda l: l.shopee_line_type == "voucher")
        self.assertEqual(len(shipping), 1)
        self.assertEqual(len(voucher), 1)
        self.assertAlmostEqual(shipping.price_unit, 200 / 1.07, places=2)
        self.assertAlmostEqual(voucher.price_unit, -10 / 1.07, places=2)
        self.assertIn("MOGEN083", voucher.name)
        self.assertEqual(shipping.product_id.default_code, "Service04")
        self.assertAlmostEqual(
            sum(order.order_line.mapped("price_subtotal")), 5780 / 1.07, places=1,
        )
        self.assertIn("4,040.00", str(order.note))
        self.assertNotIn("****", str(order.note))
        self.assertEqual(order.shopee_net_income, 4040.0)

    def _refill_setup(self, shopee_stock, refill_below, sync_out=True):
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.config.company_id.id)], limit=1
        )
        if not warehouse:
            self.skipTest("No warehouse available")
        self.config.write({"shopee_push_stock": True, "shopee_warehouse_id": warehouse.id})
        self.product.write({"shopee_sync_stock_out": sync_out})
        mapping = self.env["shopee.product.mapping"].upsert(
            self.config, sku=self.sku, product=self.product,
            item_id="77", model_id="701", shopee_stock=shopee_stock,
        )
        mapping.refill_below = refill_below
        return mapping, warehouse

    def _capture_pushes(self, callback):
        calls = []

        def _fake_update(self_api, token, item_id, model_id, qty, location_id=None):
            calls.append(qty)
            return {"response": {}}

        with patch.object(ShopeeAPI, "update_stock", _fake_update):
            callback()
        return calls

    def test_refill_threshold_skips_until_shopee_runs_low(self):
        mapping, warehouse = self._refill_setup(shopee_stock=15, refill_below=10)
        calls = self._capture_pushes(
            lambda: self.config._push_stock_for_products(self.product))
        self.assertEqual(calls, [])

        mapping.shopee_stock = 5
        calls = self._capture_pushes(
            lambda: self.config._push_stock_for_products(self.product))
        expected = int(max(
            self.product.with_context(warehouse=warehouse.id).free_qty, 0))
        self.assertEqual(calls, [expected])
        self.assertEqual(mapping.odoo_available_stock, expected)

    def test_mapping_button_forces_push(self):
        mapping, _warehouse = self._refill_setup(
            shopee_stock=500, refill_below=10, sync_out=False)
        calls = self._capture_pushes(mapping.action_push_odoo_stock)
        self.assertEqual(calls, [mapping.odoo_available_stock])
        self.assertEqual(mapping.last_pushed_stock, mapping.odoo_available_stock)

    def test_manual_odoo_available_stock_is_pushed(self):
        mapping, _warehouse = self._refill_setup(shopee_stock=500, refill_below=0)
        real = mapping.odoo_free_qty
        mapping.odoo_available_stock = real + 25
        self.assertTrue(mapping.use_stock_override)
        calls = self._capture_pushes(mapping.action_push_odoo_stock)
        self.assertEqual(calls, [real + 25])

        mapping.action_reset_stock_override()
        self.assertEqual(mapping.odoo_available_stock, real)
        calls = self._capture_pushes(mapping.action_push_odoo_stock)
        self.assertEqual(calls, [real])

    def test_editing_shopee_stock_does_not_push(self):
        mapping, _warehouse = self._refill_setup(shopee_stock=500, refill_below=0)
        calls = self._capture_pushes(lambda: mapping.write({"shopee_stock": 7}))
        self.assertEqual(calls, [])
        self.assertEqual(mapping.shopee_stock, 7)

    def test_partial_stock_failure_preserves_success_and_retry_is_not_duplicated(self):
        mapping, _warehouse = self._refill_setup(shopee_stock=500, refill_below=0)
        other = self.env["product.product"].create({
            "name": "QA failed stock", "default_code": "QA-FAILED-STOCK",
            "type": "product", "shopee_sync_stock_out": True,
        })
        failed = self.env["shopee.product.mapping"].upsert(
            self.config, "QA-FAILED-STOCK", other, item_id="88", shopee_stock=500,
        )
        def update(_api, _token, item_id, *args, **kwargs):
            if item_id == 88:
                raise ShopeeAPIError("temporary", "Try later")
            return {"response": {}}
        with patch.object(ShopeeAPI, "update_stock", update):
            self.assertEqual(self.config._push_stock_for_products(), 1)
            queue = self.env["shopee.retry.queue"].search([("shopee_config_id", "=", self.config.id)])
            self.assertEqual(len(queue), 1)
            queue._run_one()
        self.assertTrue(mapping.last_stock_push)
        self.assertFalse(failed.last_stock_push)
        self.assertEqual(queue.state, "pending")
        self.assertEqual(self.env["shopee.retry.queue"].search_count([
            ("shopee_config_id", "=", self.config.id),
        ]), 1)

    def test_order_sync_wizard_imports_and_syncs(self):
        from datetime import timedelta
        from odoo import fields as odoo_fields

        wizard = self.env["shopee.order.sync.wizard"].create({
            "config_id": self.config.id,
            "import_orders_from": odoo_fields.Datetime.now() - timedelta(days=3),
        })

        def _fake_list(self_api, token, time_from, time_to, cursor=""):
            return {"response": {"order_list": [{"order_sn": "WIZ-1"}], "more": False}}

        def _fake_detail(self_api, token, order_sns):
            return {"response": {"order_list": [{
                "order_sn": sn, "buyer_user_id": 321, "order_status": "SHIPPED",
                "item_list": [{"item_name": "Widget", "model_sku": self.sku}],
            } for sn in order_sns]}}

        with patch.object(ShopeeAPI, "get_order_list", _fake_list), \
             patch.object(ShopeeAPI, "get_order_detail", _fake_detail):
            wizard.action_import_orders()

        self.assertEqual(wizard.state, "done")
        self.assertIn("1 new order(s)", wizard.result_message)
        self.assertEqual(self.config.import_orders_from, False)  # cleared by the sync
        order = self.env["sale.order"].search([("shopee_order_sn", "=", "WIZ-1")])
        self.assertEqual(len(order), 1)

        wizard.state = "draft"
        with patch.object(ShopeeAPI, "get_order_detail", _fake_detail):
            wizard.action_sync_status()
        self.assertIn("1 order(s)", wizard.result_message)
