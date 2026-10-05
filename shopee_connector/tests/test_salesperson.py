"""Salesperson on imported orders; run only with the Odoo test runner."""
from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged

from ..models.shopee_api import ShopeeAPI


@tagged("post_install", "-at_install")
class TestShopeeSalesperson(TransactionCase):
    def setUp(self):
        super().setUp()
        escrow = patch.object(ShopeeAPI, "get_escrow_detail", return_value={"response": {}})
        escrow.start()
        self.addCleanup(escrow.stop)
        self.product = self.env["product.product"].create({
            "name": "Shopee QA SP", "default_code": "SHOPEE-QA-SP", "type": "product",
        })
        self.config = self.env["shopee.config"].create({
            "name": "SP Shop", "environment": "sandbox", "partner_id": "1000002",
            "partner_key": "k", "shop_id": "333", "access_token": "tok",
            "token_expires_at": "2999-01-01 00:00:00",
        })
        self.salesperson = new_test_user(
            self.env, login="shopee_sp_user", groups="sales_team.group_sale_salesman",
        )
        self.customer = self.env["res.partner"].create({"name": "SP Buyer"})

    def _import(self, sn):
        return self.env["sale.order"].with_user(self.env.ref("base.user_root")).create_from_shopee({
            "order_sn": sn, "order_status": "READY_TO_SHIP", "buyer_username": "sp_buyer",
            "item_list": [{
                "item_name": "W", "model_sku": self.product.default_code,
                "model_quantity_purchased": 1, "model_discounted_price": 10,
            }],
        }, partner=self.customer, config=self.config)

    def test_new_order_uses_configured_salesperson(self):
        self.config.shopee_salesperson_id = self.salesperson
        self.assertEqual(self._import("SP-001").user_id, self.salesperson)

    def test_unset_keeps_default_and_old_orders_untouched(self):
        old = self._import("SP-OLD")
        old_user = old.user_id
        self.config.shopee_salesperson_id = self.salesperson
        self.assertEqual(old.user_id, old_user)
        self.config.shopee_salesperson_id = False
        self.assertEqual(self._import("SP-002").user_id, self.env.ref("base.user_root"))

    def test_salesperson_must_belong_to_company(self):
        other = self.env["res.company"].create({"name": "Other SP Co"})
        self.config.company_id = other
        with self.assertRaises(ValidationError):
            self.config.shopee_salesperson_id = self.salesperson
