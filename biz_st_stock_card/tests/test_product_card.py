# -*- coding: utf-8 -*-
"""การ์ดสินค้ารายวัน

invariant หลัก: การ์ดเป็นการ "ซอย" รายงานหลักตามวัน ไม่ใช่เครื่องยนต์ตัวที่สอง
ผลรวมรายวันจึงต้องกลับมาเท่ากับแถวสินค้าในรายงานหลักเสมอ ทั้งจำนวนและมูลค่า
"""

from datetime import datetime

from odoo.exceptions import AccessError, UserError
from odoo.tests.common import new_test_user, tagged

from .common import StockCardCommon

MEASURES = (
    "opening_qty", "in_qty", "out_qty", "closing_qty",
    "in_qty_ext", "out_qty_ext",
    "opening_value", "in_value", "out_value", "adj_value", "closing_value",
)


@tagged("post_install", "-at_install")
class TestProductCard(StockCardCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # ยอดยกมา 100 ที่ต้นทุน 10
        cls._do(cls.product, 100, cls.supplier, cls.stock_a, cls.before)
        # ตั้งราคารับของแต่ละวันให้ต่างกันจริง เพื่อพิสูจน์ว่าคอลัมน์ราคาเป็นของ "วันนั้น"
        # ``disable_auto_svl`` กันไม่ให้การเขียนราคาสร้างชั้นปรับมูลค่าเพิ่มมากวนงวดของเทส
        cls.product.with_context(disable_auto_svl=True).standard_price = 20.0
        cls.move_in1 = cls._do(cls.product, 50, cls.supplier, cls.stock_a, cls.d1)
        cls.move_out = cls._do(cls.product, 30, cls.stock_a, cls.customer, cls.d2)
        cls.product.with_context(disable_auto_svl=True).standard_price = 25.0
        cls.move_in2 = cls._do(cls.product, 40, cls.supplier, cls.stock_a, cls.d3)
        # โอนข้ามคลังวันเดียวกัน — วันนั้นต้องมีทั้งรับและจ่ายเหมือนรายงานหลัก
        cls.move_xfer = cls._do(cls.product, 20, cls.stock_a, cls.stock_b, cls.d3)

    # ------------------------------------------------------------------
    def _card(self, product=None, **kw):
        return self.report.get_product_card(
            self._options(**kw), (product or self.product).id
        )

    def _main_row(self, **kw):
        """แถวสินค้าของรายงานหลัก ซึ่งเป็นยอดรวมทุกคลังเมื่อแกนเป็น สินค้า → คลัง"""
        data = self._data(group_mode="product_wh", product_ids=[self.product.id], **kw)
        return self._find(data, "product", self.product.id)

    # ------------------------------------------------------- invariant หลัก
    def test_card_totals_match_product_row_in_main_report(self):
        row = self._main_row()
        totals = self._card()["totals"]
        for key in MEASURES:
            self.assertAlmostEqual(
                totals[key], row[key], places=2,
                msg="การ์ดกับรายงานหลักไม่ตรงกันที่ %s" % key,
            )

    def test_card_is_the_same_from_both_group_modes(self):
        """group_mode เป็นแค่การนำเสนอของรายงานหลัก การ์ดจึงต้องไม่ขยับตาม"""
        first = self._card(group_mode="wh_product")["totals"]
        second = self._card(group_mode="product_wh")["totals"]
        for key in MEASURES:
            self.assertAlmostEqual(first[key], second[key], places=2, msg=key)

    def test_day_series_sums_back_to_totals(self):
        card = self._card()
        totals = card["totals"]
        self.assertAlmostEqual(
            sum(day["in_qty"] for day in card["days"]), totals["in_qty"], places=3
        )
        self.assertAlmostEqual(
            sum(day["out_qty"] for day in card["days"]), totals["out_qty"], places=3
        )
        self.assertTrue(card["checks"]["qty_reconciled"])
        self.assertAlmostEqual(card["checks"]["qty_difference"], 0.0, places=3)

    def test_last_day_balance_equals_closing(self):
        card = self._card()
        self.assertAlmostEqual(
            card["days"][-1]["balance_qty"], card["totals"]["closing_qty"], places=3
        )
        self.assertAlmostEqual(
            card["days"][-1]["balance_value"], card["totals"]["closing_value"], places=2
        )
        self.assertTrue(card["checks"]["value_reconciled"])

    def test_only_days_with_movement_are_emitted_in_order(self):
        card = self._card()
        dates = [day["date"] for day in card["days"]]
        self.assertEqual(dates, ["2025-06-05", "2025-06-10", "2025-06-20"])
        self.assertEqual(dates, sorted(dates))
        self.assertEqual(card["checks"]["day_count"], 3)

    def test_interwarehouse_day_shows_both_directions(self):
        """การโอนข้ามคลังนับสองครั้งโดยตั้งใจ — การ์ดต้องเล่าเรื่องเดียวกับรายงานหลัก"""
        day = next(d for d in self._card()["days"] if d["date"] == "2025-06-20")
        self.assertAlmostEqual(day["in_qty"], 60.0, places=3)   # รับ 40 + เข้าคลัง B 20
        self.assertAlmostEqual(day["out_qty"], 20.0, places=3)  # ออกจากคลัง A 20
        self.assertAlmostEqual(day["change"], 40.0, places=3)

    def test_change_column_is_in_minus_out(self):
        for day in self._card()["days"]:
            self.assertAlmostEqual(
                day["change"], day["in_qty"] - day["out_qty"], places=3
            )

    # ------------------------------------------------------------- มูลค่า
    def test_day_values_reconcile_to_svl(self):
        card = self._card()
        checks = card["checks"]
        self.assertTrue(checks["svl_reconciled"], checks["svl_difference"])
        self.assertAlmostEqual(
            sum(day["in_value"] for day in card["days"]),
            card["totals"]["in_value"], places=2,
        )
        self.assertAlmostEqual(
            sum(day["out_value"] for day in card["days"]),
            card["totals"]["out_value"], places=2,
        )

    def test_unit_cost_is_the_price_of_that_day(self):
        """ราคา/หน่วยต้องเป็นต้นทุนของวันนั้นจริง ไม่ใช่ค่าเฉลี่ยทั้งงวด"""
        days = {day["date"]: day for day in self._card()["days"]}
        self.assertAlmostEqual(days["2025-06-05"]["unit_in"], 20.0, places=2)
        self.assertAlmostEqual(days["2025-06-20"]["unit_in"], 25.0, places=2)
        # วันที่ไม่มีของเข้าออกฝั่งนั้น ไม่ต้องเดาราคาให้
        self.assertIsNone(days["2025-06-10"]["unit_in"])
        self.assertIsNone(days["2025-06-05"]["unit_out"])

    def test_unit_out_matches_the_layers_of_that_delivery(self):
        """oracle อิสระ — ราคาจ่ายของวันนั้นต้องเท่ากับชั้นมูลค่าของใบส่งของใบนั้น"""
        layers = self.env["stock.valuation.layer"].search(
            [("stock_move_id", "=", self.move_out.id)]
        )
        expected = -sum(layers.mapped("value")) / 30.0
        days = {day["date"]: day for day in self._card()["days"]}
        self.assertAlmostEqual(days["2025-06-10"]["unit_out"], expected, places=2)

    def test_value_columns_are_zero_without_rights(self):
        user = new_test_user(
            self.env, login="sc_card_stock_only", groups="stock.group_stock_user",
            company_ids=[(6, 0, [self.company.id])], company_id=self.company.id,
        )
        card = self.report.with_user(user).get_product_card(
            self._options(), self.product.id
        )
        self.assertFalse(card["options"]["show_value"])
        self.assertEqual(card["checks"]["value_hidden_reason"], "no_accounting_group")
        for day in card["days"]:
            self.assertIsNone(day["unit_in"])
            self.assertIsNone(day["unit_out"])
            self.assertAlmostEqual(day["balance_value"], 0.0, places=2)
        self.assertAlmostEqual(card["totals"]["closing_qty"], 160.0, places=3)

    def test_user_without_stock_rights_is_refused(self):
        user = new_test_user(
            self.env, login="sc_card_no_stock", groups="base.group_user",
            company_ids=[(6, 0, [self.company.id])], company_id=self.company.id,
        )
        with self.assertRaises(AccessError):
            self.report.with_user(user).get_product_card(self._options(), self.product.id)

    # -------------------------------------------------------------- ตัวกรอง
    def test_warehouse_filter_is_carried_into_the_card(self):
        card = self._card(warehouse_ids=[self.wh_b.id])
        self.assertTrue(card["checks"]["svl_scope_limited"])
        # คลัง B ได้รับของจากการโอนอย่างเดียว
        self.assertAlmostEqual(card["totals"]["in_qty"], 20.0, places=3)
        self.assertAlmostEqual(card["totals"]["out_qty"], 0.0, places=3)
        self.assertAlmostEqual(card["totals"]["closing_qty"], 20.0, places=3)
        row = self._data(
            group_mode="product_wh", product_ids=[self.product.id],
            warehouse_ids=[self.wh_b.id],
        )
        self.assertAlmostEqual(
            card["totals"]["closing_qty"],
            self._find(row, "product", self.product.id)["closing_qty"], places=3,
        )

    def test_card_forces_a_single_product(self):
        card = self._card()
        self.assertEqual(card["options"]["product_ids"], [self.product.id])
        self.assertEqual(card["product"]["id"], self.product.id)
        self.assertFalse(card["options"]["group_lot"])
        self.assertFalse(card["options"]["group_location"])

    def test_card_without_product_is_refused(self):
        with self.assertRaises(UserError):
            self.report.get_product_card(self._options(), False)

    def test_day_boundary_respects_user_timezone(self):
        """23:30 เวลาไทยต้องตกวันไทย ไม่ใช่วันของ UTC"""
        self._do(
            self.product_b, 7, self.supplier, self.stock_a,
            datetime(2025, 6, 5, 17, 30, 0),  # = 6 มิ.ย. 00:30 ตามเวลาไทย
        )
        card = self._card(self.product_b, tz="Asia/Bangkok")
        self.assertEqual([day["date"] for day in card["days"]], ["2025-06-06"])
        card_utc = self._card(self.product_b, tz="UTC")
        self.assertEqual([day["date"] for day in card_utc["days"]], ["2025-06-05"])

    def test_empty_period_still_reconciles(self):
        card = self._card(date_from="2025-07-01", date_to="2025-07-31")
        self.assertEqual(card["days"], [])
        self.assertTrue(card["checks"]["qty_reconciled"])
        self.assertTrue(card["checks"]["value_reconciled"])
        self.assertAlmostEqual(
            card["totals"]["opening_qty"], card["totals"]["closing_qty"], places=3
        )

    # -------------------------------------------------------------- drill
    def test_day_drill_down_carries_views(self):
        action = self.report.action_day_moves(
            self._options(), self.product.id, "2025-06-05"
        )
        # OWL doAction ไม่ผ่าน clean_action — ขาด views แล้วพังที่ _preprocessAction
        self.assertIn("views", action)
        self.assertEqual(action["views"], [(False, "list"), (False, "form")])
        self.assertEqual(action["res_model"], "stock.move.line")
        lines = self.env["stock.move.line"].search(action["domain"])
        self.assertTrue(lines)
        self.assertEqual(lines.mapped("product_id"), self.product)
        # ต้องได้บรรทัดเท่ากับจำนวนรายการที่การ์ดนับไว้ของวันนั้นเป๊ะ
        day = next(d for d in self._card()["days"] if d["date"] == "2025-06-05")
        self.assertEqual(len(lines), day["move_count"])

    def test_day_drill_down_without_day_is_refused(self):
        with self.assertRaises(UserError):
            self.report.action_day_moves(self._options(), self.product.id, False)
