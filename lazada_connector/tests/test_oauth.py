from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase

from ..models.lazada_api import LazadaAPIError


class TestLazadaOAuth(TransactionCase):
    def setUp(self):
        super().setUp()
        self.config = self.env["lazada.config"].create(
            {
                "name": "OAuth test seller",
                "company_id": self.env.company.id,
                "app_key": "1000001",
                "app_secret": "test-secret",
                "region": "th",
                "redirect_url": "https://example.com/lazada/callback",
            }
        )

    def test_new_authorization_discards_stale_code(self):
        self.config.write({"temp_auth_code": "old-code"})

        action = self.config.action_get_authorization_url()

        self.assertFalse(self.config.temp_auth_code)
        self.assertTrue(self.config.oauth_state)
        self.assertIn("force_auth=true", action["url"])
        self.assertIn("country=th", action["url"])

    @patch("odoo.addons.lazada_connector.models.lazada_config.LazadaAPI.get_seller_info")
    @patch("odoo.addons.lazada_connector.models.lazada_config.LazadaAPI.get_access_token")
    def test_complete_authorization_stores_tokens_and_clears_attempt(
        self, get_access_token, get_seller_info
    ):
        self.config.write({"oauth_state": "pending", "temp_auth_code": "code"})
        get_access_token.return_value = {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "expires_in": 3600,
            "country_user_info": [{"seller_id": "12345"}],
        }
        get_seller_info.return_value = {"seller_id": "12345"}

        self.config._complete_authorization("code")

        self.assertEqual(self.config.access_token, "access-token")
        self.assertEqual(self.config.refresh_token, "refresh-token")
        self.assertEqual(self.config.seller_id, "12345")
        self.assertFalse(self.config.oauth_state)
        self.assertFalse(self.config.temp_auth_code)

    @patch("odoo.addons.lazada_connector.models.lazada_config.LazadaAPI.get_access_token")
    def test_failed_authorization_clears_attempt(self, get_access_token):
        self.config.write({"oauth_state": "pending", "temp_auth_code": "code"})
        get_access_token.side_effect = LazadaAPIError(
            "InvalidCode", "Invalid authorization code"
        )

        with self.assertRaises(LazadaAPIError):
            self.config._complete_authorization("code")

        self.assertFalse(self.config.oauth_state)
        self.assertFalse(self.config.temp_auth_code)
        self.assertFalse(self.config.access_token)

    @patch("odoo.addons.lazada_connector.models.lazada_config.LazadaAPI.get_access_token")
    def test_missing_access_token_clears_attempt(self, get_access_token):
        self.config.write({"oauth_state": "pending", "temp_auth_code": "code"})
        get_access_token.return_value = {"code": "0"}

        with self.assertRaises(UserError):
            self.config._complete_authorization("code")

        self.assertFalse(self.config.oauth_state)
        self.assertFalse(self.config.temp_auth_code)
