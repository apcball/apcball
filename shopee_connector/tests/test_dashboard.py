"""Ops health dashboard; run only with the Odoo test runner."""
import json

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestShopeeDashboard(TransactionCase):
    def setUp(self):
        super().setUp()
        Config = self.env["shopee.config"]
        vals = {"partner_id": "100", "partner_key": "qa-key", "access_token": "qa-token"}
        self.shop_a = Config.create(dict(vals, name="Shop A", shop_id="95001"))
        self.shop_b = Config.create(dict(vals, name="Shop B", shop_id="95002"))
        self.user = new_test_user(
            self.env, login="shopee_dash_user", groups="shopee_connector.group_shopee_user",
        )
        self.outsider = new_test_user(
            self.env, login="shopee_dash_outsider", groups="base.group_user",
        )
        self.Dashboard = self.env["shopee.dashboard"]

    def _data(self, user=None, **kwargs):
        model = self.Dashboard.with_user(user or self.user)
        return model.get_dashboard_data(**kwargs)

    def test_access_gate(self):
        with self.assertRaises(AccessError):
            self._data(user=self.outsider)

    def test_payload_serializable(self):
        json.dumps(self._data())

    def test_counts_and_shop_filter(self):
        Queue = self.env["shopee.retry.queue"]
        Queue.create({"shopee_config_id": self.shop_a.id, "operation_type": "push_stock",
                      "payload": "{}", "state": "failed"})
        Queue.create({"shopee_config_id": self.shop_b.id, "operation_type": "push_price",
                      "payload": "{}", "state": "failed"})
        self.env["shopee.api.log"].create({
            "name": "qa error", "shopee_config_id": self.shop_a.id, "log_type": "request",
            "status": "error", "endpoint": "/x",
        })
        self.env["shopee.product.mapping"].create({
            "shopee_config_id": self.shop_a.id, "shopee_item_id": "1", "shopee_model_id": "0",
        })
        base = self._data(shop_ids=[self.shop_a.id, self.shop_b.id])["tiles"]
        only_a = self._data(shop_ids=[self.shop_a.id])["tiles"]
        self.assertGreaterEqual(base["retry_failed"]["value"], 2)
        self.assertEqual(only_a["retry_failed"]["value"], 1)
        self.assertEqual(only_a["stock_failed"]["value"], 1)
        self.assertEqual(only_a["api_errors"]["value"], 1)
        self.assertEqual(only_a["unmapped"]["value"], 1)
        self.assertEqual(only_a["retry_failed"]["severity"], "warn")

    def test_series_and_sections(self):
        data = self._data(days=7)
        n = len(data["dates"])
        self.assertGreaterEqual(n, 7)
        self.assertEqual(len(data["orders"]["trend"]), n)
        self.assertEqual(len(data["sync"]["ok_series"]), n)
        self.assertEqual(len(data["sync"]["failed_series"]), n)
        for key in ("api_errors", "retry_failed", "stock_failed", "unmapped", "fulfillment"):
            self.assertEqual(len(data["tiles"][key]["series"]), n)
        self.assertIn(data["shop_rows"][0]["status"], ("active", "expired", "no_token"))

    def test_sync_rate(self):
        Log = self.env["shopee.api.log"]
        for status in ("success", "success", "success", "error"):
            Log.create({"name": "qa", "shopee_config_id": self.shop_a.id,
                        "log_type": "request", "status": status})
        sync = self._data(shop_ids=[self.shop_a.id])["sync"]
        self.assertEqual((sync["ok"], sync["failed"], sync["rate"]), (3, 1, 75.0))
        self.assertEqual(sum(sync["ok_series"]), 3)
        self.assertEqual(sum(sync["failed_series"]), 1)

    def test_bad_period_falls_back(self):
        self.assertEqual(self._data(days="abc")["days"], 7)
        self.assertEqual(self._data(days=99)["days"], 7)

    def test_company_isolation(self):
        other = self.env["res.company"].create({"name": "Other Co"})
        foreign = self.env["shopee.config"].create({
            "name": "Foreign", "partner_id": "1", "partner_key": "k", "shop_id": "95999",
            "access_token": "t", "company_id": other.id,
        })
        shop_ids = [s["id"] for s in self._data()["shops"]]
        self.assertNotIn(foreign.id, shop_ids)
