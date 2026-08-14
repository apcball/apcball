from datetime import datetime

from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestStockCardReport(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.engine = cls.env["buz.stock.card.report"]

        cls.loc_supplier = cls.env.ref("stock.stock_location_suppliers")
        cls.loc_customer = cls.env.ref("stock.stock_location_customers")
        cls.loc_stock = cls.env.ref("stock.stock_location_stock")

        cls.loc_a = cls.env["stock.location"].create({
            "name": "Test Shelf A",
            "usage": "internal",
            "location_id": cls.loc_stock.id,
        })
        cls.loc_b = cls.env["stock.location"].create({
            "name": "Test Shelf B",
            "usage": "internal",
            "location_id": cls.loc_stock.id,
        })

        cls.product = cls.env["product.product"].create({
            "name": "Test Stock Card Product",
            "type": "product",
        })
        cls.uom_dozen = cls.env.ref("uom.product_uom_dozen")

    def _mk_move(self, src, dest, qty, date_val, uom=None, state="done"):
        uom = uom or self.product.uom_id
        move = self.env["stock.move"].create({
            "name": "test move",
            "product_id": self.product.id,
            "product_uom_qty": qty,
            "product_uom": uom.id,
            "location_id": src.id,
            "location_dest_id": dest.id,
            "state": state,
            "date": date_val,
            "move_line_ids": [Command.create({
                "product_id": self.product.id,
                "product_uom_id": uom.id,
                "quantity": qty,
                "location_id": src.id,
                "location_dest_id": dest.id,
                "date": date_val,
            })],
        })
        return move

    def _dt(self, s):
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")

    def test_opening_balance(self):
        self._mk_move(self.loc_supplier, self.loc_a, 100.0, self._dt("2024-05-15 10:00:00"))
        data = self.engine.get_stock_card_data(
            self.product.id, [self.loc_a.id], "2024-06-01", "2024-06-30", page_size=20, page=0,
        )
        self.assertEqual(data["opening_balance"], 100.0)
        self.assertEqual(len(data["lines"]), 0)

    def test_incoming(self):
        data = self.engine.get_stock_card_data(
            self.product.id, [self.loc_a.id], "2024-06-01", "2024-06-30", page_size=20, page=0,
        )
        self.assertEqual(data["opening_balance"], 0.0)
        self._mk_move(self.loc_supplier, self.loc_a, 50.0, self._dt("2024-06-10 08:00:00"))
        data = self.engine.get_stock_card_data(
            self.product.id, [self.loc_a.id], "2024-06-01", "2024-06-30", page_size=20, page=0,
        )
        self.assertEqual(len(data["lines"]), 1)
        self.assertEqual(data["lines"][0]["in"], 50.0)
        self.assertEqual(data["lines"][0]["out"], 0.0)
        self.assertEqual(data["lines"][0]["balance"], 50.0)

    def test_outgoing(self):
        self._mk_move(self.loc_supplier, self.loc_a, 100.0, self._dt("2024-05-15 10:00:00"))
        self._mk_move(self.loc_a, self.loc_customer, 30.0, self._dt("2024-06-10 08:00:00"))
        data = self.engine.get_stock_card_data(
            self.product.id, [self.loc_a.id], "2024-06-01", "2024-06-30", page_size=20, page=0,
        )
        self.assertEqual(data["opening_balance"], 100.0)
        self.assertEqual(data["lines"][0]["out"], 30.0)
        self.assertEqual(data["lines"][0]["balance"], 70.0)

    def test_internal_transfer_excluded_when_scope_covers_both_sides(self):
        self._mk_move(self.loc_supplier, self.loc_a, 100.0, self._dt("2024-05-15 10:00:00"))
        self._mk_move(self.loc_a, self.loc_b, 50.0, self._dt("2024-06-10 08:00:00"))
        scope_ids = self.env["stock.location"].search(
            [("id", "child_of", self.loc_stock.id)]
        ).ids
        data = self.engine.get_stock_card_data(
            self.product.id, scope_ids, "2024-06-01", "2024-06-30", page_size=20, page=0,
        )
        self.assertEqual(len(data["lines"]), 0)
        self.assertEqual(data["opening_balance"], 100.0)

    def test_internal_transfer_shows_both_sides_for_single_location_scope(self):
        self._mk_move(self.loc_supplier, self.loc_a, 100.0, self._dt("2024-05-15 10:00:00"))
        self._mk_move(self.loc_a, self.loc_b, 50.0, self._dt("2024-06-10 08:00:00"))

        data_a = self.engine.get_stock_card_data(
            self.product.id, [self.loc_a.id], "2024-06-01", "2024-06-30", page_size=20, page=0,
        )
        data_b = self.engine.get_stock_card_data(
            self.product.id, [self.loc_b.id], "2024-06-01", "2024-06-30", page_size=20, page=0,
        )
        self.assertEqual(data_a["lines"][0]["out"], 50.0)
        self.assertEqual(data_a["lines"][0]["balance"], 50.0)
        self.assertEqual(data_b["lines"][0]["in"], 50.0)
        self.assertEqual(data_b["lines"][0]["balance"], 50.0)

    def test_date_boundary_inclusive_end_of_day(self):
        self._mk_move(self.loc_supplier, self.loc_a, 10.0, self._dt("2024-06-30 23:59:00"))
        data = self.engine.get_stock_card_data(
            self.product.id, [self.loc_a.id], "2024-06-01", "2024-06-30", page_size=20, page=0,
        )
        self.assertEqual(len(data["lines"]), 1)
        self.assertEqual(data["lines"][0]["in"], 10.0)

    def test_mixed_uom_running_balance(self):
        self._mk_move(self.loc_supplier, self.loc_a, 1.0, self._dt("2024-06-01 08:00:00"), uom=self.uom_dozen)
        self._mk_move(self.loc_a, self.loc_customer, 6.0, self._dt("2024-06-15 08:00:00"))
        data = self.engine.get_stock_card_data(
            self.product.id, [self.loc_a.id], "2024-06-01", "2024-06-30", page_size=20, page=0,
        )
        self.assertAlmostEqual(data["lines"][0]["balance"], 12.0)
        self.assertAlmostEqual(data["lines"][1]["balance"], 6.0)

    def test_pagination_running_balance_consistent_across_pages(self):
        for i in range(5):
            self._mk_move(self.loc_supplier, self.loc_a, 10.0, self._dt(f"2024-06-0{i + 1} 08:00:00"))
        data_p0 = self.engine.get_stock_card_data(
            self.product.id, [self.loc_a.id], "2024-06-01", "2024-06-30", page_size=2, page=0,
        )
        data_p1 = self.engine.get_stock_card_data(
            self.product.id, [self.loc_a.id], "2024-06-01", "2024-06-30", page_size=2, page=1,
        )
        data_p2 = self.engine.get_stock_card_data(
            self.product.id, [self.loc_a.id], "2024-06-01", "2024-06-30", page_size=2, page=2,
        )
        self.assertEqual(data_p0["total_count"], 5)
        self.assertEqual([l["balance"] for l in data_p0["lines"]], [10.0, 20.0])
        self.assertEqual([l["balance"] for l in data_p1["lines"]], [30.0, 40.0])
        self.assertEqual([l["balance"] for l in data_p2["lines"]], [50.0])
        self.assertTrue(data_p0["has_next"])
        self.assertFalse(data_p0["has_prev"])
        self.assertTrue(data_p2["has_prev"])
        self.assertFalse(data_p2["has_next"])

    def test_show_movements_only_does_not_drop_real_movements(self):
        # stock.move.line enforces quantity != 0 at the ORM level, so every
        # real line is a genuine movement; the toggle must be a no-op here.
        self._mk_move(self.loc_supplier, self.loc_a, 10.0, self._dt("2024-06-10 08:00:00"))
        data_all = self.engine.get_stock_card_data(
            self.product.id, [self.loc_a.id], "2024-06-01", "2024-06-30",
            page_size=20, page=0, show_movements_only=False,
        )
        data_moves = self.engine.get_stock_card_data(
            self.product.id, [self.loc_a.id], "2024-06-01", "2024-06-30",
            page_size=20, page=0, show_movements_only=True,
        )
        self.assertEqual(len(data_all["lines"]), 1)
        self.assertEqual(len(data_moves["lines"]), 1)

    def test_multi_company_isolation(self):
        country_th = self.env.ref("base.th")
        state_th = self.env["res.country.state"].search(
            [("country_id", "=", country_th.id)], limit=1
        )
        partner2 = self.env["res.partner"].create({
            "name": "Test Company 2",
            "company_type": "company",
            "street": "1 Test Rd",
            "street2": "Test Sub-district",
            "city": "Bangkok",
            "state_id": state_th.id,
            "zip": "10110",
            "country_id": country_th.id,
            "vat": "1234567890123",
            "phone": "0000000000",
            "email": "test-company-2@example.com",
            "branch": "00000",
        })
        company2 = self.env["res.company"].create({
            "name": "Test Company 2",
            "partner_id": partner2.id,
        })
        warehouse2 = self.env["stock.warehouse"].create({
            "name": "Test Warehouse C2",
            "code": "TWC2",
            "company_id": company2.id,
        })
        loc_c2 = warehouse2.lot_stock_id
        move = self._mk_move(self.loc_supplier, loc_c2, 100.0, self._dt("2024-06-10 08:00:00"))
        move.company_id = company2.id
        move.move_line_ids.company_id = company2.id

        data = self.engine.get_stock_card_data(
            self.product.id, [loc_c2.id], "2024-06-01", "2024-06-30",
            page_size=20, page=0, company_ids=[self.env.company.id],
        )
        self.assertEqual(len(data["lines"]), 0)

    def test_deterministic_ordering_same_date(self):
        for _ in range(3):
            self._mk_move(self.loc_supplier, self.loc_a, 10.0, self._dt("2024-06-10 08:00:00"))
        data = self.engine.get_stock_card_data(
            self.product.id, [self.loc_a.id], "2024-06-01", "2024-06-30", page_size=20, page=0,
        )
        self.assertEqual([l["seq"] for l in data["lines"]], [1, 2, 3])
        self.assertEqual([l["balance"] for l in data["lines"]], [10.0, 20.0, 30.0])

    def test_negative_stock_allowed(self):
        self._mk_move(self.loc_a, self.loc_customer, 50.0, self._dt("2024-06-10 08:00:00"))
        data = self.engine.get_stock_card_data(
            self.product.id, [self.loc_a.id], "2024-06-01", "2024-06-30", page_size=20, page=0,
        )
        self.assertEqual(data["opening_balance"], 0.0)
        self.assertEqual(data["lines"][0]["balance"], -50.0)

    def test_empty_result(self):
        data = self.engine.get_stock_card_data(
            self.product.id, [self.loc_a.id], "2024-06-01", "2024-06-30", page_size=20, page=0,
        )
        self.assertEqual(data["opening_balance"], 0.0)
        self.assertEqual(len(data["lines"]), 0)
        self.assertEqual(data["total_count"], 0)
