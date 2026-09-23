# -*- coding: utf-8 -*-
"""วันไม่เคลื่อนไหว / ใช้เฉลี่ย / MOS / สถานะ / KPI"""

from odoo.tests.common import tagged

from .common import StockAgingCommon, days_ago


@tagged("post_install", "-at_install")
class TestAgingMetrics(StockAgingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._seed_standard()

    def test_usage_mos_and_no_move_of_active_product(self):
        data = self._data(unfold_level=7)
        row = self._product_row(data, self.product_w, self.wh_a)
        self.assertTrue(row["has_metrics"])
        # จ่ายลูกค้า 10 + 30 ใน 6 เดือน → 40/6 ต่อเดือน; MOS = 120 ÷ (40/6) = 18
        self.assertAlmostEqual(row["avg_monthly_use"], 40 / 6.0, places=2)
        self.assertAlmostEqual(row["mos"], 18.0, places=1)
        self.assertEqual(row["no_move_days"], 5)
        self.assertFalse(row["no_move_is_estimate"])
        self.assertEqual(row["status"], "slow")

    def test_never_issued_product_estimates_no_move_from_oldest_receipt(self):
        data = self._data(unfold_level=7)
        row = self._product_row(data, self.product_b, self.wh_b)
        self.assertEqual(row["no_move_days"], 400)
        self.assertTrue(row["no_move_is_estimate"])
        self.assertIsNone(row["mos"])
        self.assertEqual(row["avg_monthly_use"], 0.0)
        self.assertEqual(row["status"], "obsolete")
        self.assertEqual(data["checks"]["no_move_estimated_rows"] >= 1, True)

    def test_internal_transfer_and_adjustment_do_not_count_as_usage(self):
        data = self._data(unfold_level=7)
        cable_a = self._product_row(data, self.product_c, self.wh_a)
        # โอนไปคลัง B ไม่ใช่การใช้ แต่เป็นการเคลื่อนไหว (จ่ายออกจากคลัง A)
        self.assertEqual(cable_a["avg_monthly_use"], 0.0)
        self.assertEqual(cable_a["no_move_days"], 20)
        self.assertFalse(cable_a["no_move_is_estimate"])
        filt = self._product_row(data, self.product_f, self.wh_a)
        self.assertEqual(filt["avg_monthly_use"], 0.0)
        self.assertEqual(filt["no_move_days"], 3)

    def test_status_thresholds_follow_config_in_priority_order(self):
        self.config.write({"non_moving_days": 3, "obsolete_days": 4})
        data = self._data(unfold_level=7)
        row = self._product_row(data, self.product_w, self.wh_a)
        self.assertEqual(row["status"], "obsolete")  # 5 วัน ≥ 4
        self.config.write({"non_moving_days": 3, "obsolete_days": 30})
        data = self._data(unfold_level=7)
        row = self._product_row(data, self.product_w, self.wh_a)
        self.assertEqual(row["status"], "non_moving")  # 5 วัน ≥ 3 แต่ < 30
        self.config.write({"non_moving_days": 90, "obsolete_days": 365, "slow_mos_months": 24.0})
        data = self._data(unfold_level=7)
        row = self._product_row(data, self.product_w, self.wh_a)
        self.assertEqual(row["status"], "normal")  # MOS 18 ≤ 24

    def test_usage_months_changes_average_and_mos(self):
        self.config.write({"usage_months": 3})
        data = self._data(unfold_level=7)
        row = self._product_row(data, self.product_w, self.wh_a)
        self.assertEqual(data["options"]["usage_months"], 3)
        self.assertEqual(data["options"]["date_from"], "2025-04-01")
        self.assertAlmostEqual(row["avg_monthly_use"], 40 / 3.0, places=2)
        self.assertAlmostEqual(row["mos"], 9.0, places=1)

    def test_rows_above_product_level_have_no_metrics(self):
        data = self._data(unfold_level=7, group_categ=True)
        wh = self._find(data, "wh", self.wh_a.id)
        self.assertFalse(wh["has_metrics"])
        self.assertIsNone(wh["status"])
        self.assertIsNone(wh["mos"])
        self.assertIsNotNone(wh["avg_age"])
        categ = self._find(data, "categ", self.categ.id)
        self.assertFalse(categ["has_metrics"])
        # โหมด สินค้า→คลัง: แถวคลังใต้สินค้าแสดงตัวชี้วัด
        data = self._data(group_mode="product_wh", unfold_level=7)
        product = self._find(data, "product", self.product_c.id)
        self.assertTrue(product["has_metrics"])
        wh_under = self._find(data, "wh", self.wh_b.id, "prod-%s/" % self.product_c.id)
        self.assertTrue(wh_under["has_metrics"])

    def test_kpis_over_thresholds_and_risk_count(self):
        data = self._data()
        totals = data["totals"]
        over = {o["edge"]: o for o in data["kpis"]["over"]}
        self.assertEqual(sorted(over), [90, 180, 365])
        self.assertAlmostEqual(over[90]["qty"], totals["b3_qty"] + totals["b4_qty"] + totals["b5_qty"], places=3)
        self.assertAlmostEqual(over[180]["qty"], totals["b4_qty"] + totals["b5_qty"], places=3)
        self.assertAlmostEqual(over[365]["qty"], totals["b5_qty"], places=3)
        self.assertAlmostEqual(
            over[90]["value"], totals["b3_value"] + totals["b4_value"] + totals["b5_value"], places=2,
        )
        # สินค้าเสี่ยง: B (ตาย 400 วัน) และ C? — C จ่ายออกครั้งสุดท้าย 20 วัน (โอน) จึงไม่เสี่ยง
        self.assertEqual(data["kpis"]["risk"]["count"], 1)
        self.assertAlmostEqual(data["kpis"]["risk"]["qty"], 40.0, places=3)
        self.assertEqual(data["kpis"]["risk"]["product_count"], len(self.all_products))
        self.assertAlmostEqual(data["kpis"]["avg_age"], totals["avg_age"], places=1)

    def test_risk_count_is_independent_of_axis_and_unfold(self):
        base = self._data()["kpis"]["risk"]
        for kw in ({"group_mode": "product_wh"}, {"unfold_level": 0}, {"unfold_level": 7, "group_lot": True}):
            self.assertEqual(self._data(**kw)["kpis"]["risk"]["count"], base["count"], kw)

    def test_window_cards_reflect_usage_window_ledger(self):
        data = self._data(product_ids=[self.product_w.id])
        cards = data["kpis"]["cards"]
        # ทุกรายการของ W อยู่ในช่วง 6 เดือน → ยกมา 0, รับ 160, จ่าย 40, คงเหลือ 120
        self.assertAlmostEqual(cards["opening_qty"], 0.0, places=3)
        self.assertAlmostEqual(cards["in_qty"], 160.0, places=3)
        self.assertAlmostEqual(cards["out_qty"], 40.0, places=3)
        self.assertAlmostEqual(cards["closing_qty"], 120.0, places=3)
        data = self._data(product_ids=[self.product_b.id])
        self.assertAlmostEqual(data["kpis"]["cards"]["opening_qty"], 40.0, places=3)
