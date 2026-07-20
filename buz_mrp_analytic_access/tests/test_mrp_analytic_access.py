from odoo.tests.common import TransactionCase
from odoo import Command


class TestMrpAnalyticAccess(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.access_group = cls.env.ref(
            "buz_mrp_analytic_access.group_mrp_analytic_distribution_user"
        )
        cls.analytic_group = cls.env.ref("analytic.group_analytic_accounting")
        cls.stock_manager_group = cls.env.ref("stock.group_stock_manager")
        cls.test_user = cls.env["res.users"].create({
            "name": "MO Analytic Distribution Test User",
            "login": "mo_analytic_distribution_test_user",
            "email": "mo_analytic_distribution_test_user@example.com",
            "groups_id": [
                Command.set([
                    cls.env.ref("base.group_user").id,
                    cls.env.ref("mrp.group_mrp_user").id,
                    cls.access_group.id,
                ])
            ],
        })

    def test_group_implies_analytic_accounting(self):
        self.assertIn(self.analytic_group, self.access_group.implied_ids)

    def test_user_sees_mo_analytic_distribution_without_inventory_manager(self):
        self.assertNotIn(self.stock_manager_group, self.test_user.groups_id)
        view = self.env["mrp.production"].with_user(self.test_user).get_view(
            view_id=self.env.ref("mrp_account.mrp_production_form_view_inherited").id,
            view_type="form",
        )
        self.assertIn('name="analytic_distribution"', view["arch"])
