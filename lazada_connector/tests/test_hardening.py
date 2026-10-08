"""Security and recovery regressions; run only with the Odoo test runner."""
import hashlib
import hmac
import json
from datetime import timedelta
from unittest.mock import Mock, patch

from odoo import fields
from odoo.http import Response
from odoo.exceptions import AccessError, UserError
from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger

from ..controllers import main as controllers
from ..models.lazada_api import LazadaAPI


def _sign(app_key, secret, raw):
    return hmac.new(secret.encode(), app_key.encode() + raw, hashlib.sha256).hexdigest()


def _mock_request(env, raw=b"", headers=None):
    request = Mock(env=env)
    request.httprequest.get_data.return_value = raw
    request.httprequest.headers = headers or {}
    request.make_json_response.side_effect = lambda body, status=200: Response(
        json.dumps(body), status=status, content_type="application/json",
    )
    request.make_response.side_effect = lambda body, status=200, headers=None: Response(
        body, status=status, headers=headers,
    )
    return request


@tagged("post_install", "-at_install")
class TestLazadaHardening(TransactionCase):
    def setUp(self):
        super().setUp()
        self.config = self.env["lazada.config"].create({
            "name": "QA Seller", "app_key": "100", "app_secret": "qa-private-key",
            "seller_id": "91001", "access_token": "qa-private-token",
            "token_expires_at": "2999-01-01 00:00:00",
            "redirect_url": "https://qa.invalid/lazada/callback",
        })
        self.Queue = self.env["lazada.retry.queue"]
        self.Config = type(self.config)
        self.network = patch.object(LazadaAPI, "_request", side_effect=AssertionError("Unexpected HTTP call"))
        self.network.start()
        self.addCleanup(self.network.stop)

    def _job(self, operation="sync_order", payload=None):
        return self.Queue.enqueue(self.config, operation, payload or {"order_id": "QA-ORDER"})

    def _webhook(self, payload, signature=True):
        raw = json.dumps(payload).encode()
        headers = {"Authorization": _sign("100", "qa-private-key", raw)} if signature else {}
        with patch.object(controllers, "request", _mock_request(self.env, raw, headers)):
            response = controllers.LazadaWebhookController().lazada_webhook()
            return response.status_code, json.loads(response.get_data())

    def _order_payload(self, order_id="QA-ORDER"):
        return {"seller_id": "91001", "message_type": 0,
                "data": {"trade_order_id": order_id, "order_status": "pending"}}

    # ------------------------------------------------------------------
    # Webhooks
    # ------------------------------------------------------------------
    def test_unsigned_webhook_rejected(self):
        status, body = self._webhook(self._order_payload(), signature=False)
        self.assertEqual(status, 401)
        self.assertEqual(body["error"], "invalid_signature")

    def test_signature_rejects_tampering_and_non_ascii(self):
        verify = controllers.LazadaWebhookController._signature_valid
        raw = b'{"seller_id":"91001"}'
        signed = _sign("100", "qa-private-key", raw)
        self.assertTrue(verify(self.config, raw, signed))
        self.assertTrue(verify(self.config, raw, signed.upper()))
        self.assertFalse(verify(self.config, raw + b" ", signed))
        self.assertFalse(verify(self.config, raw, "ลายเซ็น"))
        self.config.webhook_secret = "dedicated-key"
        self.assertFalse(verify(self.config, raw, signed))

    def test_webhook_requires_object_and_consistent_seller(self):
        for payload in ([], None, {"data": []}, {"seller_id": "91001", "SellerId": "91002"}):
            with self.subTest(payload=payload):
                self.assertEqual(self._webhook(payload)[0], 400)

    def test_webhook_rejects_order_event_without_order(self):
        payload = {"seller_id": "91001", "message_type": 0, "data": {"trade_order_id": {"x": 1}}}
        self.assertEqual(self._webhook(payload)[0], 400)

    def test_unknown_event_is_safely_ignored(self):
        status, body = self._webhook({"seller_id": "91001", "message_type": 7, "data": {}})
        self.assertEqual(status, 200)
        self.assertEqual(body["result"], "ignored")

    @mute_logger("odoo.sql_db")
    def test_webhook_rolls_back_partial_work_before_queueing(self):
        def fail(config, payload):
            config.name = "Partial change"
            config.env.cr.execute("SELECT 1 / 0")
        with patch.object(self.Config, "process_webhook", fail):
            status, body = self._webhook(self._order_payload())
        self.assertEqual((status, body["queued"]), (200, True))
        self.assertEqual(self.config.name, "QA Seller")
        job = self.Queue.search([("lazada_config_id", "=", self.config.id)])
        self.assertEqual(len(job), 1)
        self.assertEqual(json.loads(job.payload), {"order_id": "QA-ORDER"})

    def test_webhook_failed_enqueue_returns_retryable_http_status(self):
        with patch.object(self.Config, "process_webhook", side_effect=UserError("temporary")), \
             patch.object(type(self.Queue), "enqueue", side_effect=UserError("queue unavailable")):
            status, body = self._webhook(self._order_payload())
        self.assertEqual(status, 503)
        self.assertFalse(body["queued"])

    def test_stock_webhook_failure_is_durably_queued(self):
        with patch.object(self.Config, "action_sync_stock", side_effect=UserError("temporary")):
            status, body = self._webhook({"seller_id": "91001", "type": "SKU_STOCK_UPDATE"})
        self.assertEqual((status, body["queued"]), (200, True))
        self.assertEqual(self.Queue.search([("lazada_config_id", "=", self.config.id)]).operation_type, "sync_stock")

    # ------------------------------------------------------------------
    # OAuth
    # ------------------------------------------------------------------
    def test_oauth_state_expires_and_is_consumed_once(self):
        self.config.action_get_authorization_url()
        state = self.config.oauth_state
        self.assertTrue(self.config.oauth_state_expires_at > fields.Datetime.now())
        self.assertFalse(self.config._accept_oauth_callback("wrong", "code"))
        self.assertFalse(self.config._accept_oauth_callback(state, ""))
        self.assertTrue(self.config._accept_oauth_callback(state, "auth-code"))
        self.assertFalse(self.config._accept_oauth_callback(state, "replay"))

    def test_oauth_rejects_expired_state(self):
        self.config.action_get_authorization_url()
        state = self.config.oauth_state
        self.config.oauth_state_expires_at = fields.Datetime.now() - timedelta(seconds=1)
        self.assertFalse(self.config._accept_oauth_callback(state, "code"))
        self.assertFalse(self.config._accept_oauth_callback(None, "code"))

    def _callback(self, **kwargs):
        with patch.object(controllers, "request", _mock_request(self.env)), \
             patch.object(self.Config, "_complete_authorization") as complete:
            response = controllers.LazadaCallbackController().lazada_callback(**kwargs)
        return response.status_code, complete

    def test_callback_without_state_needs_single_pending_authorization(self):
        status, complete = self._callback(code="qa-code")
        self.assertEqual(status, 400)
        complete.assert_not_called()

        self.config.action_get_authorization_url()
        other = self.config.copy({"name": "QA Seller 2", "seller_id": "91002", "app_secret": "k2"})
        other.action_get_authorization_url()
        status, complete = self._callback(code="qa-code")
        self.assertEqual(status, 400)
        complete.assert_not_called()

        other.oauth_state = False
        status, complete = self._callback(code="qa-code")
        self.assertEqual(status, 302)
        complete.assert_called_once_with("qa-code")
        self.assertFalse(self.config.oauth_state)

    def test_callback_with_wrong_state_is_rejected(self):
        self.config.action_get_authorization_url()
        status, complete = self._callback(code="qa-code", state="forged")
        self.assertEqual(status, 400)
        complete.assert_not_called()
        self.assertTrue(self.config.oauth_state)

    # ------------------------------------------------------------------
    # Retry queue
    # ------------------------------------------------------------------
    def test_retry_invalid_payload_does_not_block_following_job(self):
        broken, good = self._job(), self._job()
        broken.payload = "[invalid JSON"
        with patch.object(self.Config, "import_order_by_id", return_value=True) as call:
            self.Queue.cron_process()
        self.assertEqual(broken.state, "failed")
        self.assertEqual(good.state, "done")
        self.assertEqual(call.call_count, 1)

    @mute_logger("odoo.sql_db")
    def test_retry_rolls_back_database_error_and_continues(self):
        broken = self._job(payload={"order_id": "BAD"})
        good = self._job(payload={"order_id": "GOOD"})

        def import_order(config, order_id):
            if order_id == "BAD":
                config.name = "Partial retry"
                config.env.cr.execute("SELECT 1 / 0")
            return True
        with patch.object(self.Config, "import_order_by_id", import_order):
            self.Queue.cron_process()
        self.assertEqual(self.config.name, "QA Seller")
        self.assertEqual(broken.state, "pending")
        self.assertEqual(broken.attempts, 1)
        self.assertGreater(broken.next_retry_at, fields.Datetime.now())
        self.assertEqual(good.state, "done")

    def test_retry_stops_at_limit_and_never_repeats_done_jobs(self):
        failed, done = self._job(), self._job()
        failed.write({"attempts": 4, "max_attempts": 5})
        done.state = "done"
        with patch.object(self.Config, "import_order_by_id", side_effect=UserError("temporary")) as call:
            failed._run_one()
            failed._run_one()
            done._run_one()
        self.assertEqual(call.call_count, 1)
        self.assertEqual((failed.state, failed.attempts), ("failed", 5))

    def test_retry_inactive_seller_is_not_executed(self):
        job = self._job()
        self.config.active = False
        with patch.object(self.Config, "import_order_by_id") as call:
            job._run_one()
        call.assert_not_called()
        self.assertEqual(job.attempts, 0)

    def test_retry_backoff_is_respected_by_worker(self):
        job = self._job()
        job.next_retry_at = fields.Datetime.now() + timedelta(minutes=5)
        with patch.object(self.Config, "import_order_by_id") as call:
            job._run_one()
        call.assert_not_called()
        self.assertEqual(job.attempts, 0)

    def test_missing_order_status_is_not_marked_success(self):
        job = self._job("sync_order_status", {"order_id": "NOT-IMPORTED"})
        job._run_one()
        self.assertEqual(job.state, "pending")
        self.assertEqual(job.attempts, 1)

    def test_missing_retry_product_is_not_success(self):
        job = self._job("push_stock", {"product_id": 2147483647})
        job._run_one()
        self.assertEqual(job.state, "pending")
        self.assertEqual(job.attempts, 1)

    # ------------------------------------------------------------------
    # Logs
    # ------------------------------------------------------------------
    def test_log_redacts_nested_and_serialized_secrets(self):
        log = self.env["lazada.api.log"].create_api_log(
            self.config, request_data={"nested": [{"Authorization": "secret-header"}]},
            response_data=json.dumps({"refresh_token": "new-secret"}),
            error_message="URL contains qa-private-token and qa-private-key",
        )
        content = str(log.read(["request_data", "response_data", "error_message"]))
        for secret in ("secret-header", "new-secret", "qa-private-token", "qa-private-key"):
            self.assertNotIn(secret, content)

    @mute_logger("odoo.sql_db", "odoo.addons.lazada_connector.models.lazada_api")
    def test_log_failure_does_not_poison_transaction(self):
        def fail(*args, **kwargs):
            self.env.cr.execute("SELECT 1 / 0")
        with patch.object(type(self.env["lazada.api.log"]), "create_api_log", fail):
            self.config._get_api()._write_log("GET", "/test", {}, None, {}, "success", 200, 0, None)
        self.env.cr.execute("SELECT 1")
        self.assertEqual(self.env.cr.fetchone()[0], 1)

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------
    def _order_api(self, order_id, status="pending"):
        order = {"order_id": order_id, "statuses": [status], "customer_first_name": "QA"}
        return (patch.object(LazadaAPI, "get_order", return_value=order),
                patch.object(LazadaAPI, "get_order_items", return_value=[]))

    def test_status_sync_filters_before_limit(self):
        partner = self.env["res.partner"].with_context(skip_partner_required_fields=True).create({"name": "QA Buyer"})
        orders = self.env["sale.order"].create([{
            "partner_id": partner.id, "is_lazada_order": True,
            "lazada_config_id": self.config.id, "lazada_order_id": "QA-%03d" % index,
        } for index in range(201)])
        get_order, _items = self._order_api("QA-000", "ready_to_ship")
        with get_order as call:
            self.assertEqual(self.config.sync_order_statuses(["QA-000"]), 1)
        self.assertEqual(call.call_args.args[1], "QA-000")
        self.assertEqual(orders[0].lazada_order_status, "ready_to_ship")

    def test_broken_pagination_does_not_advance_watermark(self):
        partner = self.env["res.partner"].with_context(skip_partner_required_fields=True).create({"name": "QA Buyer"})
        self.env["sale.order"].create({
            "partner_id": partner.id, "is_lazada_order": True,
            "lazada_config_id": self.config.id, "lazada_order_id": "QA-EXISTING",
        })
        client = Mock()
        client.get_orders.return_value = {"orders": [{"order_id": "QA-EXISTING"}] * 50}
        with patch.object(self.Config, "_get_api", return_value=client):
            with self.assertRaises(UserError):
                self.config.action_sync_orders()
        self.assertFalse(self.config.last_order_sync)

    def test_order_without_id_does_not_advance_watermark(self):
        client = Mock()
        client.get_orders.return_value = {"orders": [{}]}
        with patch.object(self.Config, "_get_api", return_value=client), self.assertRaises(UserError):
            self.config.action_sync_orders()
        self.assertFalse(self.config.last_order_sync)

    def test_order_import_is_idempotent(self):
        get_order, get_items = self._order_api("QA-IDEMPOTENT")
        with get_order, get_items:
            first = self.config.import_order_by_id("QA-IDEMPOTENT")
            second = self.config.import_order_by_id("QA-IDEMPOTENT")
        self.assertEqual(first, second)
        self.assertEqual(self.env["sale.order"].search_count([
            ("lazada_config_id", "=", self.config.id), ("lazada_order_id", "=", "QA-IDEMPOTENT"),
        ]), 1)

    def test_import_rejects_mismatched_order(self):
        get_order, get_items = self._order_api("SOMETHING-ELSE")
        with get_order, get_items, self.assertRaises(UserError):
            self.config.import_order_by_id("QA-REQUESTED")

    def test_duplicate_sku_requires_explicit_mapping(self):
        self.env["product.product"].create([
            {"name": "QA duplicate A", "default_code": "QA-DUP"},
            {"name": "QA duplicate B", "default_code": "QA-DUP"},
        ])
        with self.assertRaises(UserError):
            self.env["sale.order"]._lazada_find_product({"sku": "QA-DUP"}, config=self.config)

    def test_token_refresh_is_mocked_and_expiry_is_renewed(self):
        self.config.write({"token_expires_at": "2000-01-01 00:00:00", "refresh_token": "old-refresh"})
        with patch.object(LazadaAPI, "refresh_access_token", return_value={
            "access_token": "renewed-token", "refresh_token": "renewed-refresh", "expires_in": 604800,
        }) as call:
            self.assertEqual(self.config._ensure_valid_token(), "renewed-token")
            self.assertEqual(self.config._ensure_valid_token(), "renewed-token")
        self.assertEqual(call.call_count, 1)
        self.assertGreater(self.config.token_expires_at, fields.Datetime.now())

    def test_cross_company_order_uses_seller_company(self):
        other = self.env["res.company"].with_context(skip_partner_required_fields=True).create({"name": "QA order company"})
        config = self.config.copy({"company_id": other.id, "seller_id": "QA-OTHER", "app_secret": "other-key"})
        get_order, get_items = self._order_api("QA-COMPANY")
        with get_order, get_items:
            order = self.env["sale.order"].create_from_lazada("QA-COMPANY", config=config)
        self.assertEqual(order.company_id, other)
        self.assertEqual(order.partner_id.company_id, other)

    def test_company_rules_and_relations(self):
        other = self.env["res.company"].with_context(skip_partner_required_fields=True).create({"name": "QA Other Company"})
        other_config = self.config.copy({"company_id": other.id, "seller_id": "91002", "app_secret": "other-key"})
        mapping = self.env["lazada.product.mapping"].create({
            "lazada_config_id": other_config.id, "seller_sku": "QA-OTHER-SKU",
        })
        log = self.env["lazada.api.log"].create_api_log(other_config, endpoint="/qa")
        retry = self.Queue.enqueue(other_config, "sync_order", {"order_id": "OTHER"})
        manager = new_test_user(
            self.env(context=dict(self.env.context, skip_partner_required_fields=True)),
            login="lazada_qa_manager", groups="lazada_connector.group_lazada_manager",
            company_id=self.env.company.id, company_ids=[fields.Command.set(self.env.company.ids)],
        )
        for record in (other_config, mapping, log, retry):
            restricted = record.with_user(manager).with_context(allowed_company_ids=self.env.company.ids)
            with self.subTest(model=record._name), self.assertRaises(AccessError):
                restricted.read(["id", "display_name"])
        product = self.env["product.product"].create({"name": "Other product", "company_id": other.id})
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.env["lazada.product.mapping"].create({
                "lazada_config_id": self.config.id, "seller_sku": "QA-X", "product_id": product.id,
            })

    def test_secrets_hidden_from_lazada_users(self):
        user = new_test_user(
            self.env(context=dict(self.env.context, skip_partner_required_fields=True)),
            login="lazada_qa_user", groups="lazada_connector.group_lazada_user",
        )
        with self.assertRaises(AccessError):
            self.config.with_user(user).read(["app_secret"])

    def test_views_load(self):
        for model in ("lazada.config", "lazada.product.mapping", "lazada.fulfillment.batch",
                      "lazada.fulfillment.job", "lazada.stock.import.wizard",
                      "lazada.order.sync.wizard", "lazada.product.mapping.import.wizard"):
            with self.subTest(model=model):
                self.assertIn("arch", self.env[model].get_view(view_type="form"))


@tagged("post_install", "-at_install")
class TestLazadaHttpRoutes(HttpCase):
    def test_webhook_http_authentication(self):
        self.env["lazada.config"].create({
            "name": "QA HTTP", "app_key": "100", "app_secret": "qa-http-key",
            "seller_id": "991003",
        })
        self.env.flush_all()
        raw = json.dumps({"seller_id": "991003", "message_type": 7, "data": {}})
        headers = {"Content-Type": "application/json"}
        rejected = self.url_open("/lazada/webhook", data=raw, headers=headers)
        self.assertEqual(rejected.status_code, 401)
        headers["Authorization"] = _sign("100", "qa-http-key", raw.encode())
        accepted = self.url_open("/lazada/webhook", data=raw, headers=headers)
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.json()["result"], "ignored")

    def test_callback_without_pending_authorization_is_rejected_over_http(self):
        response = self.url_open("/lazada/callback?code=qa-code", allow_redirects=False)
        self.assertEqual(response.status_code, 400)
