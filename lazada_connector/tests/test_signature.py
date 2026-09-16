import hashlib
import hmac
from types import SimpleNamespace
from unittest.mock import Mock, patch

from odoo.tests import TransactionCase

from ..controllers.main import LazadaWebhookController
from ..models.lazada_api import LazadaAPI


def _lazada_sign(secret, path, params):
    filtered = {k: v for k, v in params.items() if k != "sign"}
    base = path + "".join(
        f"{key}{filtered[key]}" for key in sorted(filtered)
    )
    return hmac.new(
        secret.encode(), base.encode(), hashlib.sha256
    ).hexdigest().upper()


class TestLazadaSignature(TransactionCase):
    def setUp(self):
        super().setUp()
        self.api = LazadaAPI(
            app_key="1000001",
            app_secret="testkey",
            region="th",
            environment="production",
        )

    def test_public_signature_matches_spec(self):
        path = "/auth/token/create"
        params = {"app_key": "1000001", "code": "0_abc", "timestamp": 1700000000000}
        expected = _lazada_sign("testkey", path, params)
        sign = self.api._sign(path, dict(params, sign="ignored"))
        self.assertEqual(sign, expected)
        self.assertTrue(sign.isupper())

    def test_user_signature_includes_access_token(self):
        path = "/orders/get"
        params = {
            "app_key": "1000001",
            "access_token": "tok",
            "order_id": "123",
            "timestamp": 1700000000000,
        }
        expected = _lazada_sign("testkey", path, params)
        self.assertEqual(self.api._sign(path, params), expected)

    def test_signature_changes_with_params(self):
        path = "/orders/get"
        base = {"app_key": "1000001", "timestamp": 1700000000000}
        self.assertNotEqual(
            self.api._sign(path, base),
            self.api._sign(path, dict(base, offset=50)),
        )

    def test_authorization_url_encodes_redirect(self):
        url = self.api.get_authorization_url("https://mogdev.work/lazada/callback")
        self.assertIn(
            "redirect_uri=https%3A%2F%2Fmogdev.work%2Flazada%2Fcallback", url
        )
        self.assertIn("force_auth=true", url)
        self.assertIn("country=th", url)
        self.assertTrue(url.startswith("https://auth.lazada.com/oauth/authorize"))

    def test_region_selects_api_host(self):
        self.assertEqual(self.api.host, "https://api.lazada.co.th/rest")
        sandbox = LazadaAPI(
            app_key="1", app_secret="s", region="th", environment="sandbox"
        )
        self.assertEqual(sandbox.host, "https://api.lazada.co.th/rest")

    def test_webhook_signature_includes_app_key_and_raw_body(self):
        config = SimpleNamespace(
            app_key="1000001", app_secret="testkey", webhook_secret=False
        )
        raw_body = b'{"seller_id":"12345","message_type":0}'
        signature = hmac.new(
            b"testkey", b"1000001" + raw_body, hashlib.sha256
        ).hexdigest()

        self.assertTrue(
            LazadaWebhookController._signature_valid(
                config, raw_body, signature
            )
        )
        self.assertFalse(
            LazadaWebhookController._signature_valid(config, raw_body, None)
        )

    @patch("odoo.addons.lazada_connector.models.lazada_api.requests.request")
    def test_token_creation_uses_get_with_code_in_query(self, request_mock):
        response = Mock(status_code=200)
        response.json.return_value = {"code": "0", "access_token": "token"}
        request_mock.return_value = response

        result = self.api.get_access_token("one-time-code")
        self.assertEqual(result["access_token"], "token")

        self.assertEqual(request_mock.call_args.args[0], "GET")
        self.assertEqual(
            request_mock.call_args.kwargs["params"]["code"], "one-time-code"
        )

    @patch("odoo.addons.lazada_connector.models.lazada_api.requests.request")
    def test_refresh_preserves_top_level_tokens(self, request_mock):
        response = Mock(status_code=200)
        response.json.return_value = {
            "code": "0", "access_token": "renewed", "expires_in": 3600,
            "refresh_token": "next-refresh",
        }
        request_mock.return_value = response
        self.assertEqual(
            self.api.refresh_access_token("old-refresh"), response.json.return_value
        )

    @patch("odoo.addons.lazada_connector.models.lazada_api.requests.request")
    def test_business_response_and_log_field_names(self, request_mock):
        response = Mock(status_code=200)
        response.json.return_value = {"code": "0", "data": {"seller_id": "42"}}
        request_mock.return_value = response
        self.api.log_callback = Mock()
        self.assertEqual(self.api.get_seller_info("token"), {"seller_id": "42"})
        values = self.api.log_callback.call_args.kwargs
        self.assertEqual(values["http_method"], "GET")
        self.assertEqual(values["endpoint"], "/seller/get")
        self.assertNotIn("method", values)
        self.assertNotIn("path", values)
