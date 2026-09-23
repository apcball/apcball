"""Security and recovery regressions; run only with the Odoo test runner."""
import hashlib
import hmac
import json
from datetime import timedelta
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

from odoo import fields
from odoo.http import Response
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger

from ..controllers import main as controllers
from ..models.shopee_api import ShopeeAPI


@tagged("post_install", "-at_install")
class TestShopeeHardening(TransactionCase):
    def setUp(self):
        super().setUp()
        self.config = self.env["shopee.config"].create({
            "name": "QA Shop", "partner_id": "100", "partner_key": "qa-private-key",
            "shop_id": "91001", "access_token": "qa-private-token",
            "token_expires_at": "2999-01-01 00:00:00",
            "redirect_url": "https://qa.invalid/shopee/callback?existing=1",
        })
        self.Queue = self.env["shopee.retry.queue"]
        self.Config = type(self.config)
        self.network = patch.object(ShopeeAPI, "_request", side_effect=AssertionError("Unexpected HTTP call"))
        self.network.start()
        self.addCleanup(self.network.stop)

    def _job(self, operation="sync_order", payload=None):
        return self.Queue.enqueue(self.config, operation, payload or {"order_sn": "QA-ORDER"})

    def _webhook(self, payload, signature=True):
        raw = json.dumps(payload).encode()
        headers = {}
        if signature:
            headers["Authorization"] = hmac.new(b"qa-private-key", raw, hashlib.sha256).hexdigest()
        request = Mock(env=self.env)
        request.httprequest.get_data.return_value = raw
        request.httprequest.headers = headers
        request.make_json_response.side_effect = lambda body, status=200: Response(
            json.dumps(body), status=status, content_type="application/json",
        )
        with patch.object(controllers, "request", request):
            response = controllers.ShopeeWebhookController().shopee_webhook()
            return response.status_code, json.loads(response.get_data())

    def test_unsigned_webhook_rejected_without_optional_secret(self):
        status, body = self._webhook({"shop_id": 91001, "event_type": "ORDER_NEW"}, signature=False)
        self.assertEqual(status, 401)
        self.assertEqual(body["error"], "invalid_signature")

    def test_signature_rejects_tampering_and_non_ascii(self):
        verify = controllers.ShopeeWebhookController._signature_valid
        raw = b'{"shop_id":91001}'
        signed = hmac.new(b"qa-private-key", raw, hashlib.sha256).hexdigest()
        self.assertTrue(verify(self.config, raw, signed))
        self.assertFalse(verify(self.config, raw + b" ", signed))
        self.assertFalse(verify(self.config, raw, "ลายเซ็น"))
        self.config.webhook_secret = "dedicated-key"
        self.assertFalse(verify(self.config, raw, signed))

    def test_webhook_requires_object_and_consistent_shop(self):
        for payload in ([], None, {"data": []}, {"shop_id": 91001, "data": {"shop_id": 91002}}):
            with self.subTest(payload=payload):
                self.assertEqual(self._webhook(payload)[0], 400)

    def test_numeric_unknown_event_is_safely_ignored(self):
        status, body = self._webhook({"shop_id": 91001, "code": 987654, "data": {}})
        self.assertEqual(status, 200)
        self.assertEqual(body["result"], "ignored")

    @mute_logger("odoo.sql_db")
    def test_webhook_rolls_back_partial_work_before_queueing(self):
        def fail(config, payload):
            config.name = "Partial change"
            config.env.cr.execute("SELECT 1 / 0")
        with patch.object(self.Config, "process_webhook", fail):
            status, body = self._webhook({
                "shop_id": 91001, "event_type": "ORDER_NEW", "data": {"order_sn": "QA-ORDER"},
            })
        self.assertEqual((status, body["queued"]), (200, True))
        self.assertEqual(self.config.name, "QA Shop")
        self.assertEqual(self.Queue.search_count([("shopee_config_id", "=", self.config.id)]), 1)

    def test_webhook_failed_enqueue_returns_retryable_http_status(self):
        with patch.object(self.Config, "process_webhook", side_effect=UserError("temporary")), \
             patch.object(type(self.Queue), "enqueue", side_effect=UserError("queue unavailable")):
            status, body = self._webhook({
                "shop_id": 91001, "event_type": "ORDER_NEW", "data": {"order_sn": "QA-ORDER"},
            })
        self.assertEqual(status, 503)
        self.assertFalse(body["queued"])

    def test_stock_webhook_failure_is_durably_queued(self):
        with patch.object(self.Config, "action_sync_stock", side_effect=UserError("temporary")):
            status, body = self._webhook({"shop_id": 91001, "event_type": "ITEM_STOCK"})
        self.assertEqual((status, body["queued"]), (200, True))
        self.assertEqual(self.Queue.search([("shopee_config_id", "=", self.config.id)]).operation_type, "sync_stock")

    def test_oauth_state_in_redirect_and_consumed_once(self):
        action = self.config.action_get_authorization_url()
        query = parse_qs(urlsplit(action["url"]).query)
        redirect_query = parse_qs(urlsplit(query["redirect"][0]).query)
        state = self.config.oauth_state
        self.assertEqual(redirect_query["state"], [state])
        self.assertEqual(redirect_query["existing"], ["1"])
        self.assertTrue(self.config._accept_oauth_callback(state, "auth-code", "91001"))
        self.assertFalse(self.config._accept_oauth_callback(state, "replay", "91001"))
        self.assertEqual(self.config.temp_auth_code, "auth-code")

    def test_oauth_rejects_expired_missing_and_wrong_shop(self):
        self.config.action_get_authorization_url()
        state = self.config.oauth_state
        self.assertFalse(self.config._accept_oauth_callback(None, "code", "91001"))
        self.assertFalse(self.config._accept_oauth_callback("wrong", "code", "91001"))
        self.assertFalse(self.config._accept_oauth_callback(state, "code", "91002"))
        self.config.oauth_state_expires_at = fields.Datetime.now() - timedelta(seconds=1)
        self.assertFalse(self.config._accept_oauth_callback(state, "code", "91001"))
        self.assertFalse(self.config.temp_auth_code)

    def test_retry_invalid_payload_does_not_block_following_job(self):
        broken, good = self._job(), self._job()
        broken.payload = "[invalid JSON"
        with patch.object(self.Config, "import_order_by_sn", return_value=True) as call:
            self.Queue.cron_process()
        self.assertEqual(broken.state, "failed")
        self.assertEqual(good.state, "done")
        self.assertEqual(call.call_count, 1)

    @mute_logger("odoo.sql_db")
    def test_retry_rolls_back_database_error_and_continues(self):
        broken = self._job(payload={"order_sn": "BAD"})
        good = self._job(payload={"order_sn": "GOOD"})
        def import_order(config, order_sn):
            if order_sn == "BAD":
                config.name = "Partial retry"
                config.env.cr.execute("SELECT 1 / 0")
            return True
        with patch.object(self.Config, "import_order_by_sn", import_order):
            self.Queue.cron_process()
        self.assertEqual(self.config.name, "QA Shop")
        self.assertEqual(broken.state, "pending")
        self.assertEqual(broken.attempts, 1)
        self.assertGreater(broken.next_retry_at, fields.Datetime.now())
        self.assertEqual(good.state, "done")

    def test_retry_stops_at_limit_and_never_repeats_done_jobs(self):
        failed, done = self._job(), self._job()
        failed.write({"attempts": 4, "max_attempts": 5})
        done.state = "done"
        with patch.object(self.Config, "import_order_by_sn", side_effect=UserError("temporary")) as call:
            failed._run_one()
            failed._run_one()
            done._run_one()
        self.assertEqual(call.call_count, 1)
        self.assertEqual((failed.state, failed.attempts), ("failed", 5))

    def test_retry_inactive_shop_is_not_executed(self):
        job = self._job()
        self.config.active = False
        with patch.object(self.Config, "import_order_by_sn") as call:
            job._run_one()
        call.assert_not_called()
        self.assertEqual(job.attempts, 0)

    def test_retry_backoff_is_respected_by_worker(self):
        job = self._job()
        job.next_retry_at = fields.Datetime.now() + timedelta(minutes=5)
        with patch.object(self.Config, "import_order_by_sn") as call:
            job._run_one()
        call.assert_not_called()
        self.assertEqual(job.attempts, 0)

    def test_log_redacts_nested_and_serialized_secrets(self):
        log = self.env["shopee.api.log"].create_api_log(
            self.config, request_data={"nested": [{"Authorization": "secret-header"}]},
            response_data=json.dumps({"refresh_token": "new-secret"}),
            error_message="URL contains qa-private-token and qa-private-key",
        )
        content = str(log.read(["request_data", "response_data", "error_message"]))
        for secret in ("secret-header", "new-secret", "qa-private-token", "qa-private-key"):
            self.assertNotIn(secret, content)

    @mute_logger("odoo.sql_db", "odoo.addons.shopee_connector.models.shopee_api")
    def test_log_failure_does_not_poison_transaction(self):
        def fail(*args, **kwargs):
            self.env.cr.execute("SELECT 1 / 0")
        with patch.object(type(self.env["shopee.api.log"]), "create_api_log", fail):
            self.config._get_api()._write_log("GET", "/test", {}, {}, {}, "success", 200, 0, None)
        self.env.cr.execute("SELECT 1")
        self.assertEqual(self.env.cr.fetchone()[0], 1)

    def test_free_item_stays_free(self):
        order = self.env["sale.order"].create_from_shopee({
            "order_sn": "QA-FREE", "buyer_user_id": 999,
            "item_list": [{"item_name": "Free item", "model_discounted_price": 0,
                           "model_original_price": 107, "model_quantity_purchased": 1}],
        }, config=self.config)
        self.assertEqual(order.order_line.price_unit, 0)

    def test_status_sync_filters_before_limit(self):
        partner = self.env["res.partner"].with_context(skip_partner_required_fields=True).create({"name": "QA Buyer"})
        orders = self.env["sale.order"].create([{
            "partner_id": partner.id, "is_shopee_order": True,
            "shopee_config_id": self.config.id, "shopee_order_sn": "QA-%03d" % index,
        } for index in range(201)])
        detail = {"response": {"order_list": [{"order_sn": "QA-000", "order_status": "READY_TO_SHIP"}]}}
        with patch.object(ShopeeAPI, "get_order_status", return_value=detail) as call, \
             patch.object(type(orders), "_shopee_fetch_escrow"):
            self.assertEqual(self.config.sync_order_statuses(["QA-000"]), 1)
        self.assertEqual(call.call_args.args[1], ["QA-000"])
        self.assertEqual(orders[0].shopee_order_status, "READY_TO_SHIP")

    def test_broken_pagination_does_not_advance_watermark(self):
        client = Mock()
        client.get_order_list.return_value = {"response": {"order_list": [], "more": True, "next_cursor": ""}}
        with patch.object(self.Config, "_get_api", return_value=client):
            with self.assertRaises(UserError):
                self.config.action_sync_orders()
        self.assertFalse(self.config.last_order_sync)

    def test_incomplete_details_do_not_advance_watermark(self):
        client = Mock()
        client.get_order_list.return_value = {"response": {"order_list": [{"order_sn": "MISSING"}], "more": False}}
        client.get_order_detail.return_value = {"response": {"order_list": []}}
        with patch.object(self.Config, "_get_api", return_value=client), self.assertRaises(UserError):
            self.config.action_sync_orders()
        self.assertFalse(self.config.last_order_sync)

    def test_missing_order_status_is_not_marked_success(self):
        job = self._job("sync_order_status", {"order_sn": "NOT-IMPORTED"})
        job._run_one()
        self.assertEqual(job.state, "pending")
        self.assertEqual(job.attempts, 1)

    def test_order_import_is_idempotent(self):
        detail = {"response": {"order_list": [{
            "order_sn": "QA-IDEMPOTENT", "buyer_user_id": 999, "order_status": "READY_TO_SHIP", "item_list": [],
        }]}}
        with patch.object(ShopeeAPI, "get_order_detail", return_value=detail):
            first = self.config.import_order_by_sn("QA-IDEMPOTENT")
            second = self.config.import_order_by_sn("QA-IDEMPOTENT")
        self.assertEqual(first, second)
        self.assertEqual(self.env["sale.order"].search_count([
            ("shopee_config_id", "=", self.config.id), ("shopee_order_sn", "=", "QA-IDEMPOTENT"),
        ]), 1)

    def test_duplicate_sku_requires_explicit_mapping(self):
        self.env["product.product"].create([
            {"name": "QA duplicate A", "default_code": "QA-DUP"},
            {"name": "QA duplicate B", "default_code": "QA-DUP"},
        ])
        with self.assertRaises(UserError):
            self.env["sale.order"]._shopee_find_product({"model_sku": "QA-DUP"}, config=self.config)

    def test_token_refresh_is_mocked_and_expiry_is_renewed(self):
        self.config.write({"token_expires_at": "2000-01-01 00:00:00", "refresh_token": "old-refresh"})
        with patch.object(ShopeeAPI, "refresh_access_token", return_value={
            "access_token": "renewed-token", "refresh_token": "renewed-refresh", "expire_in": 14400,
        }) as call:
            self.assertEqual(self.config._ensure_valid_token(), "renewed-token")
            self.assertEqual(self.config._ensure_valid_token(), "renewed-token")
        self.assertEqual(call.call_count, 1)
        self.assertGreater(self.config.token_expires_at, fields.Datetime.now())

    def test_cross_company_order_uses_shop_company(self):
        other = self.env["res.company"].with_context(skip_partner_required_fields=True).create({"name": "QA order company"})
        config = self.config.copy({"company_id": other.id, "shop_id": "QA-OTHER", "partner_key": "other-key"})
        order = self.env["sale.order"].create_from_shopee({
            "order_sn": "QA-COMPANY", "buyer_user_id": 6789, "item_list": [],
        }, config=config)
        self.assertEqual(order.company_id, other)
        self.assertEqual(order.partner_id.company_id, other)

    def test_missing_retry_product_is_not_success(self):
        job = self._job("push_stock", {"product_id": 2147483647})
        job._run_one()
        self.assertEqual(job.state, "pending")
        self.assertEqual(job.attempts, 1)

    def test_company_rules_and_relations(self):
        other = self.env["res.company"].with_context(skip_partner_required_fields=True).create({"name": "QA Other Company"})
        other_config = self.config.copy({"company_id": other.id, "shop_id": "91002", "partner_key": "other-key"})
        mapping = self.env["shopee.product.mapping"].create({"shopee_config_id": other_config.id})
        log = self.env["shopee.api.log"].create_api_log(other_config, endpoint="/qa")
        retry = self.Queue.enqueue(other_config, "sync_order", {"order_sn": "OTHER"})
        manager = new_test_user(
            self.env(context=dict(self.env.context, skip_partner_required_fields=True)),
            login="shopee_qa_manager", groups="sales_team.group_sale_manager",
            company_id=self.env.company.id, company_ids=[fields.Command.set(self.env.company.ids)],
        )
        for record in (other_config, mapping, log, retry):
            restricted = record.with_user(manager).with_context(allowed_company_ids=self.env.company.ids)
            with self.subTest(model=record._name), self.assertRaises(AccessError):
                restricted.read(["id", "display_name"])
        product = self.env["product.product"].create({"name": "Other product", "company_id": other.id})
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.env["shopee.product.mapping"].create({"shopee_config_id": self.config.id, "product_id": product.id})

    def test_masked_buyer_with_required_fields_addon(self):
        if not self.env.ref("buz_partner_required_fields.group_partner_required_fields_bypass", raise_if_not_found=False):
            self.skipTest("Optional partner required-fields addon is not installed")
        manager = new_test_user(
            self.env(context=dict(self.env.context, skip_partner_required_fields=True)),
            login="shopee_qa_buyer_manager", groups="sales_team.group_sale_manager",
        )
        Partner = self.env["res.partner"].with_user(manager)
        with self.assertRaises(ValidationError):
            Partner.create({"name": "Incomplete ordinary buyer"})
        buyer = Partner.find_or_create_shopee_buyer(self.config.with_user(manager), {
            "order_sn": "QA-MASKED", "buyer_user_id": 123, "buyer_username": "Masked QA Buyer",
            "recipient_address": {"name": "****", "phone": "****", "full_address": "****"},
        })
        self.assertTrue(buyer)
        self.assertFalse(buyer.email)
        self.assertFalse(buyer.street)
        self.assertEqual(buyer.company_id, self.config.company_id)

    def test_views_load(self):
        for model in ("shopee.config", "shopee.product.mapping", "shopee.fulfillment.batch",
                      "shopee.fulfillment.job", "shopee.stock.import.wizard",
                      "shopee.buyer.address.import.wizard", "shopee.order.sync.wizard"):
            with self.subTest(model=model):
                self.assertIn("arch", self.env[model].get_view(view_type="form"))


@tagged("post_install", "-at_install")
class TestShopeeHttpRoutes(HttpCase):
    def test_webhook_http_authentication(self):
        self.env["shopee.config"].create({
            "name": "QA HTTP", "partner_id": "100", "partner_key": "qa-http-key",
            "shop_id": "991003",
        })
        self.env.flush_all()
        raw = json.dumps({"shop_id": 991003, "code": 987654, "data": {}})
        headers = {"Content-Type": "application/json"}
        rejected = self.url_open("/shopee/webhook", data=raw, headers=headers)
        self.assertEqual(rejected.status_code, 401)
        headers["Authorization"] = hmac.new(b"qa-http-key", raw.encode(), hashlib.sha256).hexdigest()
        accepted = self.url_open("/shopee/webhook", data=raw, headers=headers)
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.json()["result"], "ignored")

    def test_callback_without_state_is_rejected_over_http(self):
        response = self.url_open("/shopee/callback?code=qa-code&shop_id=991003", allow_redirects=False)
        self.assertEqual(response.status_code, 400)
