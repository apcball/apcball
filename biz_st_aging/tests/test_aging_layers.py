# -*- coding: utf-8 -*-
"""การจัดชั้นอายุแบบ FIFO และการกระจายลงช่วง"""

from odoo.tests.common import tagged

from .common import StockAgingCommon, days_ago


@tagged("post_install", "-at_install")
class TestAgingLayers(StockAgingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._seed_standard()

    def test_fifo_layers_consume_newest_receipts_first(self):
        data = self._data(unfold_level=7)
        row = self._product_row(data, self.product_w, self.wh_a)
        self.assertIsNotNone(row)
        self.assertAlmostEqual(row["closing_qty"], 120.0, places=3)
        # 50 @10 วัน + 10 @15 วัน อยู่ในช่วง 0-30, ที่เหลือ 60 มาจาก IN @100 วัน (ช่วง 91-180)
        self.assertEqual(self._buckets(row), [60.0, 0.0, 0.0, 60.0, 0.0, 0.0])
        self.assertAlmostEqual(row["avg_age"], (50 * 10 + 10 * 15 + 60 * 100) / 120.0, places=1)
        self.assertEqual(row["flag"], "ok")

    def test_buckets_sum_to_closing_for_every_row(self):
        data = self._data(unfold_level=7, group_location=True, group_lot=True)
        for line in data["lines"]:
            if line["kind"] != "group" or line["closing_qty"] <= 0:
                continue
            self.assertAlmostEqual(sum(self._buckets(line)), line["closing_qty"], places=3,
                                   msg=line["id"])
            self.assertAlmostEqual(line["bucketed_qty"], line["closing_qty"], places=3)
        self.assertAlmostEqual(data["checks"]["bucket_qty_difference"], 0.0, places=3)

    def test_old_stock_lands_in_last_bucket(self):
        data = self._data(unfold_level=7)
        row = self._product_row(data, self.product_b, self.wh_b)
        self.assertEqual(self._buckets(row), [0.0, 0.0, 0.0, 0.0, 0.0, 40.0])
        self.assertAlmostEqual(row["avg_age"], 400.0, places=1)

    def test_interwarehouse_transfer_resets_age_at_destination(self):
        data = self._data(unfold_level=7)
        row_a = self._product_row(data, self.product_c, self.wh_a)
        row_b = self._product_row(data, self.product_c, self.wh_b)
        self.assertEqual(self._buckets(row_a), [0.0, 0.0, 0.0, 0.0, 40.0, 0.0])
        self.assertEqual(self._buckets(row_b), [20.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        # ระดับสินค้า (สินค้า→คลัง) รวมทั้งสองคลัง
        data = self._data(group_mode="product_wh", unfold_level=7)
        row = self._find(data, "product", self.product_c.id)
        self.assertEqual(self._buckets(row), [20.0, 0.0, 0.0, 0.0, 40.0, 0.0])

    def test_intra_warehouse_relocation_keeps_age(self):
        product = self._make_product("AG Relocated", self.categ, 1.0, code="AGR")
        self._do(product, 10, self.supplier, self.stock_a, days_ago(120), price=1.0)
        self._do(product, 10, self.stock_a, self.shelf_a, days_ago(3))
        data = self._data(product_ids=[product.id], unfold_level=7)
        row = self._product_row(data, product, self.wh_a)
        self.assertEqual(self._buckets(row), [0.0, 0.0, 0.0, 10.0, 0.0, 0.0])
        # เปิดระดับที่เก็บ → ย้ายชั้นถือเป็นการรับเข้าใหม่ของที่เก็บนั้น (นับอายุที่ระดับที่แสดง)
        data = self._data(product_ids=[product.id], unfold_level=7, group_location=True)
        shelf = self._find(data, "loc", self.shelf_a.id)
        self.assertEqual(self._buckets(shelf), [10.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        self.assertIn("ที่เก็บ", data["checks"]["age_granularity"])

    def test_lot_level_ages_each_lot_separately(self):
        data = self._data(unfold_level=7, group_lot=True)
        lot_1 = self._find(data, "lot", self.lot_1.id)
        lot_2 = self._find(data, "lot", self.lot_2.id)
        self.assertEqual(self._buckets(lot_1), [0.0, 6.0, 0.0, 0.0, 0.0, 0.0])
        self.assertEqual(self._buckets(lot_2), [1.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        # ปิดระดับล็อต → FIFO รวมทั้งสินค้า: คงเหลือ 7 = 4 (@5 วัน) + 3 (@50 วัน)
        pooled = self._data(unfold_level=7)
        row = self._product_row(pooled, self.product_l, self.wh_a)
        self.assertEqual(self._buckets(row), [4.0, 3.0, 0.0, 0.0, 0.0, 0.0])
        # ผลรวมทั้งสองแบบเท่ากันเสมอ
        self.assertAlmostEqual(
            sum(self._buckets(lot_1)) + sum(self._buckets(lot_2)), sum(self._buckets(row)), places=3,
        )

    def test_customer_return_and_inventory_adjustment_are_layers(self):
        data = self._data(unfold_level=7)
        gasket = self._product_row(data, self.product_g, self.wh_a)
        self.assertEqual(self._buckets(gasket), [8.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        filt = self._product_row(data, self.product_f, self.wh_a)
        self.assertAlmostEqual(filt["closing_qty"], 5.0, places=3)
        self.assertEqual(self._buckets(filt), [0.0, 5.0, 0.0, 0.0, 0.0, 0.0])

    def test_same_day_in_and_out_needs_no_special_case(self):
        product = self._make_product("AG SameDay", self.categ, 1.0, code="AGS")
        self._do(product, 20, self.supplier, self.stock_a, days_ago(40), price=1.0)
        self._do(product, 5, self.supplier, self.stock_a, days_ago(1, hour=1), price=1.0)
        self._do(product, 5, self.stock_a, self.customer, days_ago(1, hour=5))
        data = self._data(product_ids=[product.id], unfold_level=7)
        row = self._product_row(data, product, self.wh_a)
        # คงเหลือ 20 = 5 (รับวันเมื่อวาน) + 15 (รับเมื่อ 40 วันก่อน)
        self.assertEqual(self._buckets(row), [5.0, 15.0, 0.0, 0.0, 0.0, 0.0])

    def test_negative_stock_is_flagged_and_not_bucketed(self):
        product = self._make_product("AG Negative", self.categ, 1.0, code="AGN")
        self._do(product, 5, self.stock_a, self.customer, days_ago(9))
        data = self._data(product_ids=[product.id], unfold_level=7, display_product="all")
        row = self._product_row(data, product, self.wh_a)
        self.assertAlmostEqual(row["closing_qty"], -5.0, places=3)
        self.assertEqual(row["flag"], "negative")
        self.assertEqual(self._buckets(row), [0.0] * 6)
        self.assertIsNone(row["status"])
        self.assertAlmostEqual(data["checks"]["bucket_qty_difference"], -5.0, places=3)
        self.assertTrue(data["checks"]["negative_balances"])

    def test_layer_day_respects_user_timezone(self):
        """รับเข้า 2025-06-30 16:30 UTC = 23:30 ไทย ยังอยู่ในวันที่รายงาน; 17:30 UTC เป็นวันถัดไป"""
        product = self._make_product("AG Timezone", self.categ, 1.0, code="AGT")
        self._do(product, 3, self.supplier, self.stock_a, days_ago(0, hour=16).replace(minute=30), price=1.0)
        self._do(product, 4, self.supplier, self.stock_a, days_ago(0, hour=17).replace(minute=30), price=1.0)
        data = self._data(product_ids=[product.id], unfold_level=7)
        row = self._product_row(data, product, self.wh_a)
        self.assertAlmostEqual(row["closing_qty"], 3.0, places=3)
        self.assertEqual(self._buckets(row), [3.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        self.assertAlmostEqual(row["avg_age"], 0.0, places=1)

    def test_walk_is_a_single_query_returning_only_needed_layers(self):
        """SQL walk = คิวรีเดียวเสมอ และส่งกลับเฉพาะชั้นที่ต้องใช้ ไม่ใช่ประวัติทั้งหมด"""
        data = self._data(product_ids=[self.product_g.id])
        self.assertEqual(data["checks"]["walk_windows_run"], 1)
        self.assertEqual(data["checks"]["layer_rows"], 1)
        data = self._data(product_ids=[self.product_b.id])
        self.assertEqual(data["checks"]["walk_windows_run"], 1)
        # W มี IN 3 วัน (100/15/10 วัน) คงเหลือ 120 → ต้องใช้ทั้ง 3 ชั้น แต่ไม่มีแถวเกินนั้น
        data = self._data(product_ids=[self.product_w.id])
        self.assertEqual(data["checks"]["layer_rows"], 3)

    def test_sql_walk_matches_windowed_orm_walk_bit_for_bit(self):
        """เวอร์ชัน SQL (ใช้จริง) ต้องให้ผลเท่าเวอร์ชัน ORM รายหน้าต่างเดิมทุกโหนดทุกระดับ"""
        report = self.report
        stock_b_shelf = self.env["stock.location"].create({
            "name": "AG Shelf B", "usage": "internal", "location_id": self.stock_b.id,
            "company_id": self.company.id,
        })
        # ย้ายภายในคลังเดียวกัน (ไม่ปล่อย fact ที่ระดับคลัง แต่ปล่อยที่ระดับที่เก็บ) + โอนข้ามคลัง + ล็อต
        self._do(self.product_c, 5, self.stock_b, stock_b_shelf, days_ago(4))
        self._do(self.product_l, 2, self.stock_a, self.stock_b, days_ago(1), lot=self.lot_1)
        for kw in (
            {},
            {"group_location": True},
            {"group_lot": True},
            {"group_location": True, "group_lot": True},
            {"warehouse_ids": [self.wh_b.id], "group_location": True, "group_lot": True},
            {"tz": "UTC", "group_lot": True},
        ):
            opt = report._normalize_options(self._options(**kw))
            maps = report._load_maps(opt)
            results = []
            for walk in (report._walk_layers, report._walk_layers_windowed):
                stats = {"layer_rows": 0, "walk_windows_run": 0, "unbucketed_value": 0.0}
                nodes, _den = report._ledger_nodes(opt, maps, stats)
                walk(opt, maps, nodes, stats)
                results.append({
                    key: {k: v for k, v in node.items() if k != "last_out"}
                    for key, node in sorted(nodes.items())
                })
            self.assertEqual(results[0], results[1], "walk differs for options %s" % kw)
            self.assertTrue(any(n["bucketed_qty"] > 0 for n in results[0].values()))

    def test_custom_bucket_edges_change_labels_and_assignment(self):
        self.config.write({"bucket_1": 7, "bucket_2": 14, "bucket_3": 30, "bucket_4": 60, "bucket_5": 120})
        data = self._data(unfold_level=7)
        self.assertEqual([b["label"] for b in data["buckets"]],
                         ["0-7", "8-14", "15-30", "31-60", "61-120", "> 120"])
        row = self._product_row(data, self.product_w, self.wh_a)
        # 50 @10 → 8-14, 10 @15 → 15-30, 60 @100 → 61-120
        self.assertEqual(self._buckets(row), [0.0, 50.0, 10.0, 0.0, 60.0, 0.0])
        self.assertEqual([o["edge"] for o in data["kpis"]["over"]], [30, 60, 120])
