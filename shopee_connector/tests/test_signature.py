import hashlib
import hmac

from odoo.tests import TransactionCase

from ..models.shopee_api import ShopeeAPI


class TestShopeeSignature(TransactionCase):
    def setUp(self):
        super().setUp()
        self.api = ShopeeAPI(
            partner_id="1000001",
            partner_key="testkey",
            shop_id="222",
            environment="sandbox",
        )

    def test_public_signature_matches_spec(self):
        path = "/api/v2/auth/token/get"
        ts = 1700000000
        expected = hmac.new(
            b"testkey", f"1000001{path}{ts}".encode(), hashlib.sha256
        ).hexdigest()
        self.assertEqual(self.api._sign(path, ts), expected)

    def test_shop_signature_includes_token_and_shop(self):
        path = "/api/v2/shop/get_shop_info"
        ts = 1700000000
        expected = hmac.new(
            b"testkey",
            f"1000001{path}{ts}tok222".encode(),
            hashlib.sha256,
        ).hexdigest()
        self.assertEqual(
            self.api._sign(path, ts, access_token="tok", shop_id="222"),
            expected,
        )

    def test_shop_and_public_signatures_differ(self):
        path = "/api/v2/product/get_item_list"
        ts = 1700000000
        self.assertNotEqual(
            self.api._sign(path, ts),
            self.api._sign(path, ts, access_token="tok", shop_id="222"),
        )

    def test_authorization_url_encodes_redirect(self):
        url = self.api.get_authorization_url("https://mogdev.work/shopee/callback")
        self.assertIn(
            "redirect=https%3A%2F%2Fmogdev.work%2Fshopee%2Fcallback", url
        )
        self.assertTrue(url.startswith(
            "https://openplatform.sandbox.test-stable.shopee.sg/"
        ))
