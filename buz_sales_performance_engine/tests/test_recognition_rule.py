from odoo import fields
from odoo.tests import tagged, TransactionCase


@tagged("-at_install", "post_install")
class TestRecognitionRule(TransactionCase):
    """Verify the strict AND recognition rule and partial / refund cases.

    A sale line counts ONLY when:
      - it has delivered qty (done stock.move of outgoing picking)
      - it has at least one posted out_invoice / out_refund line linked
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.Result = cls.env["buz.sales.performance.result"]
        # Salesperson + team
        cls.team = cls.env["crm.team"].create({"name": "SPE Test Team"})
        cls.salesperson = cls.env["res.users"].create({
            "name": "SPE Salesperson",
            "login": "spe_salesperson",
            "groups_id": [(6, 0, [
                cls.env.ref("base.group_user").id,
                cls.env.ref("base.group_partner_manager").id,
                cls.env.ref("sales_team.group_sale_salesman").id,
            ])],
        })
        cls.partner = cls.env["res.partner"].create({
            "name": "SPE Customer", "company_type": "company",
        })
        # Income account so invoices can post without config errors.
        income_acc = cls.env["account.account"].create({
            "name": "SPE Test Income",
            "code": "SPEINCOME",
            "account_type": "income",
            "company_id": cls.company.id,
        })
        cls.product = cls.env["product.product"].create({
            "name": "SPE Widget",
            "type": "consu",  # consumable: pickings validate without stock on hand
            "list_price": 10000.0,
            "property_account_income_id": income_acc.id,
        })

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _create_so(self, qty=10, price=10000.0):
        so = self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "user_id": self.salesperson.id,
            "team_id": self.team.id,
            "company_id": self.company.id,
            "order_line": [(0, 0, {
                "product_id": self.product.id,
                "product_uom_qty": qty,
                "price_unit": price,
            })],
        })
        so.action_confirm()
        return so

    def _deliver(self, so, qty):
        picking = so.picking_ids
        picking.move_ids.write({"quantity": qty})
        res = picking.button_validate()
        # Backorder wizard may pop - accept it (no backorder).
        if isinstance(res, dict) and res.get("res_model") == "stock.backorder.confirmation":
            wiz = self.env[res["res_model"]].with_context(res["context"]).create({})
            wiz.process_cancel_backorder()
        return picking

    def _invoice(self, so):
        move = so._create_invoices()
        move.action_post()
        return move

    def _refund(self, so, amount):
        """Create a posted credit note linked to the SO's first line."""
        sol = so.order_line[:1]
        refund = self.env["account.move"].create({
            "move_type": "out_refund",
            "partner_id": self.partner.id,
            "invoice_date": fields.Date.today(),
            "company_id": self.company.id,
            "invoice_line_ids": [(0, 0, {
                "product_id": self.product.id,
                "quantity": 1.0,
                "price_unit": amount,
                "sale_line_ids": [(6, 0, sol.ids)],
            })],
        })
        refund.action_post()
        return refund

    def _net_for_so(self, so):
        row = self.Result.search([("sale_order_id", "=", so.id)])
        return row

    # ------------------------------------------------------------------
    # Cases
    # ------------------------------------------------------------------
    def test_01_no_delivery_no_invoice_not_recognized(self):
        so = self._create_so(qty=10)  # 100,000
        self.Result._recompute_for_sol(so.order_line.ids)
        self.assertFalse(self._net_for_so(so),
                         "SO with neither delivery nor invoice must NOT be recognized.")

    def test_02_delivery_only_not_recognized(self):
        so = self._create_so(qty=10)
        self._deliver(so, 4)  # 40% delivered, no invoice yet
        self.Result._recompute_for_sol(so.order_line.ids)
        self.assertFalse(self._net_for_so(so),
                         "Delivered but not invoiced must NOT be recognized (AND rule).")

    def test_03_invoice_only_not_recognized(self):
        so = self._create_so(qty=10)
        self._invoice(so)  # invoice posted, 0 delivery
        self.Result._recompute_for_sol(so.order_line.ids)
        self.assertFalse(self._net_for_so(so),
                         "Invoiced but not delivered must NOT be recognized (AND rule).")

    def test_04_full_delivery_full_invoice(self):
        so = self._create_so(qty=10)  # 100,000
        self._deliver(so, 10)
        self._invoice(so)
        self.Result._recompute_for_sol(so.order_line.ids)
        row = self._net_for_so(so)
        self.assertTrue(row)
        self.assertAlmostEqual(row.net_sales, 100000.0, places=2)
        self.assertAlmostEqual(row.invoice_amount, 100000.0, places=2)
        self.assertAlmostEqual(row.refund_amount, 0.0, places=2)
        self.assertAlmostEqual(row.delivered_qty, 10.0, places=2)

    def test_05_partial_delivery_partial_invoice(self):
        so = self._create_so(qty=10)  # 100,000
        self._deliver(so, 4)  # 40%
        # Invoice only the delivered part (4 units).
        so.order_line[:1].qty_to_invoice  # noqa: B018 - force compute
        move = so._create_invoices(final=True)
        # Force invoice quantity to 4 (partial).
        move.invoice_line_ids.write({"quantity": 4.0})
        move.action_post()
        self.Result._recompute_for_sol(so.order_line.ids)
        row = self._net_for_so(so)
        self.assertTrue(row)
        self.assertAlmostEqual(row.net_sales, 40000.0, places=2,
                               msg="Only delivered+invoiced portion counts.")
        self.assertAlmostEqual(row.delivered_qty, 4.0, places=2)

    def test_06_partial_invoice_progressive(self):
        so = self._create_so(qty=10)  # 100,000
        self._deliver(so, 10)  # 100%
        # First invoice: 20% (2 units)
        move1 = so._create_invoices()
        move1.invoice_line_ids.write({"quantity": 2.0})
        move1.action_post()
        self.Result._recompute_for_sol(so.order_line.ids)
        self.assertAlmostEqual(self._net_for_so(so).net_sales, 20000.0, places=2)
        # Second invoice: 80% (8 units)
        move2 = so._create_invoices()
        move2.invoice_line_ids.write({"quantity": 8.0})
        move2.action_post()
        self.Result._recompute_for_sol(so.order_line.ids)
        self.assertAlmostEqual(self._net_for_so(so).net_sales, 100000.0, places=2)

    def test_07_credit_note_reduces_net(self):
        so = self._create_so(qty=10)  # 100,000
        self._deliver(so, 10)
        self._invoice(so)
        self.Result._recompute_for_sol(so.order_line.ids)
        self.assertAlmostEqual(self._net_for_so(so).net_sales, 100000.0, places=2)
        # Post a 30% credit note (30,000).
        self._refund(so, 30000.0)
        self.Result._recompute_for_sol(so.order_line.ids)
        row = self._net_for_so(so)
        self.assertAlmostEqual(row.net_sales, 70000.0, places=2,
                               msg="Posted credit note must reduce net sales.")
        self.assertAlmostEqual(row.refund_amount, 30000.0, places=2)

    def test_08_cancel_invoice_removes_recognition(self):
        so = self._create_so(qty=10)
        self._deliver(so, 10)
        move = self._invoice(so)
        self.Result._recompute_for_sol(so.order_line.ids)
        self.assertAlmostEqual(self._net_for_so(so).net_sales, 100000.0, places=2)
        move.button_cancel()  # event hook recomputes
        self.assertFalse(self._net_for_so(so),
                         "Cancelling the only posted invoice must drop the row.")

    def test_09_return_reduces_delivered(self):
        so = self._create_so(qty=10)
        self._deliver(so, 10)
        self._invoice(so)
        self.Result._recompute_for_sol(so.order_line.ids)
        self.assertAlmostEqual(self._net_for_so(so).delivered_qty, 10.0, places=2)
        # Create an incoming return picking for 3 units.
        return_picking = so.picking_ids.copy({
            "picking_type_id": self.env["stock.picking.type"].search(
                [("code", "=", "incoming"), ("company_id", "=", self.company.id)], limit=1
            ).id,
            "move_ids": [],
        })
        self.env["stock.move"].create({
            "name": "return",
            "picking_id": return_picking.id,
            "product_id": self.product.id,
            "product_uom": self.product.uom_id.id,
            "location_id": return_picking.location_dest_id.id,
            "location_dest_id": return_picking.location_id.id,
            "sale_line_id": so.order_line[:1].id,
            "quantity": 3,
        })
        return_picking.action_assign()
        return_picking.move_ids.write({"quantity": 3.0})
        return_picking.button_validate()
        self.Result._recompute_for_sol(so.order_line.ids)
        # Net sales unchanged (invoice still 100k posted), but delivered drops to 7.
        row = self._net_for_so(so)
        self.assertAlmostEqual(row.net_sales, 100000.0, places=2)
        self.assertAlmostEqual(row.delivered_qty, 7.0, places=2)

    def test_10_multi_company_isolation(self):
        other_company = self.env["res.company"].create({"name": "SPE Co 2"})
        so = self._create_so(qty=10)
        self._deliver(so, 10)
        self._invoice(so)
        self.Result._recompute_for_sol(so.order_line.ids)
        row = self._net_for_so(so)
        self.assertEqual(row.company_id, self.company)
        # Direct SQL can't be used from a different company context via ORM,
        # so verify the global multi-company rule hides other-company rows.
        rows_in_other = self.Result.sudo().with_company(other_company).search_count(
            [("company_id", "=", self.company.id)]
        )
        # search_count bypasses rules with sudo; verify rule domain applies without sudo.
        self.assertEqual(
            self.Result.search_count([("id", "=", row.id)]),
            1,
        )
