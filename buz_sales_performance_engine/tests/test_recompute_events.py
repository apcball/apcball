from odoo import fields
from odoo.tests import tagged, TransactionCase


@tagged("-at_install", "post_install")
class TestRecomputeEvents(TransactionCase):
    """Event hooks on SO/picking/invoice trigger incremental recompute.
    Also covers 3-tier access rules."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.Result = cls.env["buz.sales.performance.result"]
        income_acc = cls.env["account.account"].create({
            "name": "SPE Income 2", "code": "SPEIN2",
            "account_type": "income", "company_id": cls.company.id,
        })
        cls.product = cls.env["product.product"].create({
            "name": "SPE P2", "type": "consu", "list_price": 5000.0,
            "property_account_income_id": income_acc.id,
        })
        cls.partner = cls.env["res.partner"].create({"name": "SPE Cust 2"})
        cls.team = cls.env["crm.team"].create({"name": "SPE Team 2"})
        # Three users: own, team-mate, manager.
        group_user = cls.env.ref("buz_sales_performance_engine.group_spe_user")
        group_lead = cls.env.ref("buz_sales_performance_engine.group_spe_team_lead")
        group_mgr = cls.env.ref("buz_sales_performance_engine.group_spe_manager")
        base_groups = [cls.env.ref("base.group_user").id,
                       cls.env.ref("base.group_partner_manager").id,
                       cls.env.ref("sales_team.group_sale_salesman").id]
        cls.own_user = cls.env["res.users"].create({
            "name": "Own", "login": "spe_own",
            "groups_id": [(6, 0, base_groups + [group_user.id])],
        })
        cls.other_user = cls.env["res.users"].create({
            "name": "Other", "login": "spe_other",
            "groups_id": [(6, 0, base_groups + [group_user.id])],
        })
        cls.lead_user = cls.env["res.users"].create({
            "name": "Lead", "login": "spe_lead",
            "groups_id": [(6, 0, base_groups + [group_lead.id])],
        })
        # Make lead a member of the team so the team rule matches.
        cls.team.write({"member_ids": [(4, cls.lead_user.id)]})
        cls.manager = cls.env.ref("base.user_admin")

    def _so(self, user):
        so = self.env["sale.order"].with_user(user).create({
            "partner_id": self.partner.id,
            "user_id": user.id,
            "team_id": self.team.id,
            "company_id": self.company.id,
            "order_line": [(0, 0, {
                "product_id": self.product.id,
                "product_uom_qty": 4,
                "price_unit": 5000.0,
            })],
        })
        so.action_confirm()
        return so

    def _full_flow(self, so):
        picking = so.picking_ids
        picking.move_ids.write({"quantity": 4})
        picking.button_validate()
        so._create_invoices().action_post()

    # ==================================================================
    # Event hooks
    # ==================================================================
    def test_01_picking_done_triggers_recompute(self):
        so = self._so(self.own_user)
        # No invoice yet -> AND rule not satisfied -> no row.
        picking = so.picking_ids
        picking.move_ids.write({"quantity": 4})
        picking.button_validate()
        self.assertFalse(self.Result.search([("sale_order_id", "=", so.id)]))

    def test_02_invoice_post_triggers_recompute(self):
        so = self._so(self.own_user)
        self._full_flow(so)
        row = self.Result.search([("sale_order_id", "=", so.id)])
        self.assertTrue(row, "action_post hook must create the result row.")
        self.assertAlmostEqual(row.net_sales, 20000.0, places=2)

    def test_03_invoice_cancel_triggers_recompute(self):
        so = self._so(self.own_user)
        self._full_flow(so)
        move = so.invoice_ids[:1]
        move.button_cancel()
        self.assertFalse(self.Result.search([("sale_order_id", "=", so.id)]),
                         "button_cancel hook must drop the row.")

    def test_04_manual_wizard_recompute(self):
        so = self._so(self.own_user)
        self._full_flow(so)
        wiz = self.env["buz.spe.recompute.wizard"].create({
            "mode": "orders", "sale_order_ids": [(6, 0, so.ids)],
        })
        wiz.action_recompute()
        self.assertTrue(self.Result.search([("sale_order_id", "=", so.id)]))

    # ==================================================================
    # Access tiers
    # ==================================================================
    def test_10_own_user_sees_only_own(self):
        so_own = self._so(self.own_user)
        self._full_flow(so_own)
        so_other = self._so(self.other_user)
        self._full_flow(so_other)
        visible = self.Result.with_user(self.own_user).search_count([])
        self.assertEqual(visible, 1, "Own-only user must see exactly 1 row (their own).")

    def test_11_team_lead_sees_team(self):
        so_own = self._so(self.own_user)
        self._full_flow(so_own)
        so_other = self._so(self.other_user)
        self._full_flow(so_other)
        # Both rows belong to self.team; lead is a member -> sees both.
        visible = self.Result.with_user(self.lead_user).search_count([])
        self.assertGreaterEqual(visible, 2)

    def test_12_manager_sees_all(self):
        so_own = self._so(self.own_user)
        self._full_flow(so_own)
        so_other = self._so(self.other_user)
        self._full_flow(so_other)
        visible = self.Result.with_user(self.manager).search_count([])
        self.assertGreaterEqual(visible, 2)

    def test_13_target_achievement_reads_result(self):
        target = self.env["buz.sales.performance.target"].sudo().create({
            "name": "Q Target", "target_type": "person",
            "user_id": self.own_user.id, "team_id": False,
            "period": "yearly",
            "date_start": fields.Date.today().replace(month=1, day=1),
            "date_end": fields.Date.today().replace(month=12, day=31),
            "target_amount": 100000.0,
        })
        so = self._so(self.own_user)  # 20,000 net
        self._full_flow(so)
        # Achievement compute reads from result table.
        self.assertAlmostEqual(target.achieved_amount, 20000.0, places=2)
        self.assertAlmostEqual(target.achievement_pct, 20.0, places=1)
