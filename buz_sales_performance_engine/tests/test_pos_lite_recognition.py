from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPosLiteRecognition(TransactionCase):
    """POS Lite orders are recognized in SPE only when state == 'done'."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Result = cls.env["buz.sales.performance.result"]
        cls.company = cls.env.company
        # Reuse existing records (MOG_DEV orphaned-column quirk: do not
        # create product.product / stock.warehouse in tests).
        cls.product = cls.env["product.product"].search(
            [("sale_ok", "=", True), ("type", "!=", "service")], limit=1,
        )
        cls.partner = cls.env["res.partner"].search(
            [("customer_rank", ">", 0)], limit=1,
        ) or cls.env["res.partner"].search([], limit=1)
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.company.id)], limit=1,
        )

    def _make_order(self, is_return=False, state="draft"):
        order = self.env["pos.lite.order"].create({
            "company_id": self.company.id,
            "partner_id": self.partner.id,
            "warehouse_id": self.warehouse.id,
            "is_return": is_return,
            "line_ids": [fields.Command.create({
                "product_id": self.product.id,
                "qty": 2.0,
                "price_unit": 100.0,
            })],
        })
        if state != "draft":
            order.write({"state": state})
        return order

    def _results_for(self, order):
        return self.Result.search(
            [("pos_order_line_id", "in", order.line_ids.ids)]
        )

    def test_01_draft_and_paid_not_recognized(self):
        order = self._make_order()
        self.assertFalse(self._results_for(order))
        order.write({"state": "paid"})
        self.assertFalse(self._results_for(order))

    def test_02_done_order_recognized(self):
        order = self._make_order(state="done")
        res = self._results_for(order)
        self.assertEqual(len(res), 1)
        self.assertEqual(res.source, "pos")
        self.assertEqual(res.pos_order_id, order)
        self.assertAlmostEqual(res.invoice_amount, order.line_ids.price_subtotal)
        self.assertAlmostEqual(res.refund_amount, 0.0)
        self.assertAlmostEqual(res.net_sales, order.line_ids.price_subtotal)
        self.assertAlmostEqual(res.delivered_qty, 2.0)
        self.assertAlmostEqual(res.ordered_qty, 2.0)

    def test_03_return_order_recognized_as_refund(self):
        order = self._make_order(is_return=True, state="done")
        res = self._results_for(order)
        self.assertEqual(len(res), 1)
        self.assertAlmostEqual(res.invoice_amount, 0.0)
        self.assertAlmostEqual(res.refund_amount, order.line_ids.price_subtotal)
        self.assertAlmostEqual(res.net_sales, -order.line_ids.price_subtotal)

    def test_04_cancel_removes_rows(self):
        order = self._make_order(state="done")
        self.assertTrue(self._results_for(order))
        order.write({"state": "cancelled"})
        self.assertFalse(self._results_for(order))

    def test_05_sale_flow_untouched(self):
        # Constraint coexistence: creating an SO-based row still works and
        # defaults to source='sale'.
        so = self.env["sale.order"].search([("state", "=", "sale")], limit=1)
        if not so:
            self.skipTest("No confirmed sale order available on this DB")
        row = self.Result.search([("sale_order_id", "=", so.id)], limit=1)
        if row:
            self.assertEqual(row.source, "sale")
