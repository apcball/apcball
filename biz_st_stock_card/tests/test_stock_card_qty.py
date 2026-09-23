# -*- coding: utf-8 -*-
"""บัญชีคุมด้านจำนวน — สมการยกมา/รับ/จ่าย/คงเหลือ และกฎการแตก fact ตามคลัง"""

from datetime import datetime

from odoo.tests.common import tagged

from .common import StockCardCommon


@tagged("post_install", "-at_install")
class TestStockCardQty(StockCardCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # ก่อนงวด: รับเข้าคลัง A 100
        cls._do(cls.product, 100, cls.supplier, cls.stock_a, cls.before)
        # ในงวด: รับ 50, ส่งออก 30, โอนไปคลัง B 20
        cls._do(cls.product, 50, cls.supplier, cls.stock_a, cls.d1)
        cls._do(cls.product, 30, cls.stock_a, cls.customer, cls.d2)
        cls._do(cls.product, 20, cls.stock_a, cls.stock_b, cls.d3)

    def test_closing_equals_opening_plus_in_minus_out(self):
        data = self._data(unfold_level=7)
        for line in data["lines"]:
            if line["kind"] != "group":
                continue
            expected = line["opening_qty"] + line["in_qty"] - line["out_qty"]
            self.assertAlmostEqual(
                line["closing_qty"], expected, places=3,
                msg="ledger identity broken on %s" % line["id"],
            )

    def test_opening_matches_moves_before_period(self):
        row = self._find(self._data(), "product", self.product.id)
        self.assertAlmostEqual(row["opening_qty"], 100.0, places=3)

    def test_opening_matches_qty_available_oracle(self):
        """ยืนยันยอดยกมากับ oracle อิสระของ core (qty_available ณ วันที่)"""
        data = self._data()
        options = data["options"]
        row = self._find(data, "product", self.product.id)
        oracle = self.product.with_context(
            to_date=options["datetime_from"], warehouse=self.wh_a.id
        ).qty_available
        self.assertAlmostEqual(row["opening_qty"], oracle, places=3)

    def test_closing_matches_qty_available_oracle(self):
        data = self._data()
        options = data["options"]
        for warehouse in (self.wh_a, self.wh_b):
            row = self._find(data, "wh", warehouse.id)
            if not row:
                continue
            oracle = self.product.with_context(
                to_date=options["datetime_to"], warehouse=warehouse.id
            ).qty_available
            self.assertAlmostEqual(
                row["closing_qty"], oracle, places=3,
                msg="closing != qty_available for %s" % warehouse.name,
            )

    def test_interwarehouse_transfer_is_out_for_source_and_in_for_dest(self):
        data = self._data()
        source = self._find(data, "wh", self.wh_a.id)
        dest = self._find(data, "wh", self.wh_b.id)
        self.assertAlmostEqual(source["out_qty"], 50.0, places=3)  # 30 ขาย + 20 โอนออก
        self.assertAlmostEqual(dest["in_qty"], 20.0, places=3)
        self.assertAlmostEqual(dest["opening_qty"], 0.0, places=3)

    def test_interwarehouse_transfer_nets_out_of_grand_closing(self):
        """โอนข้ามคลังไม่เปลี่ยนยอดคงเหลือรวม แต่เปลี่ยนยอดรับ/จ่ายรวมโดยตั้งใจ"""
        totals = self._data()["totals"]
        self.assertAlmostEqual(totals["closing_qty"], 120.0, places=3)  # 100 + 50 - 30
        self.assertAlmostEqual(totals["in_qty"], 70.0, places=3)   # 50 ซื้อ + 20 รับโอน
        self.assertAlmostEqual(totals["out_qty"], 50.0, places=3)  # 30 ขาย + 20 โอนออก
        self.assertEqual(self._data()["checks"]["interwarehouse"]["line_count"], 1)

    def test_intrawarehouse_relocation_is_invisible_without_location_level(self):
        """ย้ายของภายในคลังเดียวกันไม่ใช่การรับหรือจ่าย"""
        before = self._data()["totals"]
        self._do(self.product, 10, self.stock_a, self.shelf_a, self.d3)
        after = self._data()["totals"]
        self.assertAlmostEqual(after["in_qty"], before["in_qty"], places=3)
        self.assertAlmostEqual(after["out_qty"], before["out_qty"], places=3)
        self.assertAlmostEqual(after["closing_qty"], before["closing_qty"], places=3)

    def test_intrawarehouse_relocation_shows_when_location_level_is_on(self):
        self._do(self.product, 10, self.stock_a, self.shelf_a, self.d3)
        data = self._data(group_location=True, unfold_level=7)
        shelf = self._find(data, "loc", self.shelf_a.id)
        self.assertIsNotNone(shelf, "shelf row missing when grouping by location")
        self.assertAlmostEqual(shelf["in_qty"], 10.0, places=3)
        # ยอดคงเหลือของคลังไม่เปลี่ยน เพราะสองขาหักล้างกัน
        warehouse = self._find(data, "wh", self.wh_a.id)
        self.assertAlmostEqual(warehouse["closing_qty"], 100.0, places=3)

    def test_receipt_is_in_only_and_delivery_is_out_only(self):
        data = self._data(unfold_level=7, detail_mode="all")
        moves = [line for line in data["lines"] if line["kind"] == "move"]
        self.assertTrue(moves)
        for move in moves:
            self.assertTrue(
                bool(move["in_qty"]) != bool(move["out_qty"]),
                "a movement row must be either in or out, not both: %s" % move["id"],
            )

    def test_inventory_adjustment_counts_even_when_not_picked(self):
        move = self._do(self.product_b, 15, self.inventory_loss, self.stock_a, self.d2)
        move.write({"is_inventory": True})
        move.move_line_ids.write({"picked": False})
        row = self._find(self._data(), "product", self.product_b.id)
        self.assertAlmostEqual(row["in_qty"], 15.0, places=3)

    def test_excluding_inventory_flags_broken_balance(self):
        move = self._do(self.product_b, 15, self.inventory_loss, self.stock_a, self.d2)
        move.write({"is_inventory": True})
        data = self._data(include_inventory=False)
        self.assertTrue(data["checks"]["balance_broken_by_filter"])
        row = self._find(data, "product", self.product_b.id)
        self.assertIsNone(row)

    def test_scrap_counts_as_out(self):
        self._do(self.product, 5, self.stock_a, self.scrap, self.d3, scrapped=True)
        row = self._find(self._data(), "wh", self.wh_a.id)
        self.assertAlmostEqual(row["out_qty"], 55.0, places=3)

    def test_draft_moves_are_excluded(self):
        self.env["stock.move"].create({
            "name": "draft", "product_id": self.product.id,
            "product_uom": self.product.uom_id.id, "product_uom_qty": 999,
            "location_id": self.supplier.id, "location_dest_id": self.stock_a.id,
            "company_id": self.company.id,
        })
        # 50 ที่ซื้อเข้าคลัง A + 20 ที่คลัง B รับโอน — ใบร่าง 999 ต้องไม่โผล่
        self.assertAlmostEqual(self._data()["totals"]["in_qty"], 70.0, places=3)

    def test_uom_conversion_uses_product_reference_uom(self):
        """บรรทัดหน่วยโหล ต้องรายงานเป็นหน่วยชิ้น"""
        self._do(self.product_b, 2, self.supplier, self.stock_a, self.d1, uom=self.uom_dozen)
        row = self._find(self._data(), "product", self.product_b.id)
        self.assertAlmostEqual(row["in_qty"], 24.0, places=3)

    def test_running_balance_ends_at_leaf_closing(self):
        data = self._data(unfold_level=7, detail_mode="all")
        leaves = [
            line for line in data["lines"]
            if line["kind"] == "group" and line["child_count"] == 0
        ]
        self.assertTrue(leaves)
        checked = 0
        for leaf in leaves:
            details = [
                line for line in data["lines"]
                if line["parent_id"] == leaf["id"] and line["kind"] in ("move", "more")
            ]
            if not details:
                continue
            checked += 1
            self.assertAlmostEqual(
                details[-1]["balance_qty"], leaf["closing_qty"], places=3,
                msg="running balance does not land on closing for %s" % leaf["id"],
            )
        self.assertTrue(checked, "no leaf had detail rows")

    def test_detail_rows_are_ordered_by_date_then_id(self):
        # สอง move เวลาเดียวกัน — ลำดับต้องนิ่งด้วย id
        self._do(self.product, 3, self.supplier, self.stock_a, self.d2)
        data = self._data(unfold_level=7, detail_mode="all")
        moves = [
            line for line in data["lines"]
            if line["kind"] == "move" and line["parent_id"].endswith("prod-%s" % self.product.id)
        ]
        keys = [(line["date"], line["move_line_id"]) for line in moves]
        self.assertEqual(keys, sorted(keys))

    def test_truncated_detail_keeps_the_running_balance_correct(self):
        data = self._data(unfold_level=7, detail_mode="all", detail_limit=1)
        more = [line for line in data["lines"] if line["kind"] == "more"]
        self.assertTrue(more, "expected a truncation marker")
        self.assertTrue(data["checks"]["truncated_leaves"])
        for marker in more:
            leaf = self._row(data, marker["parent_id"])
            self.assertAlmostEqual(marker["balance_qty"], leaf["closing_qty"], places=3)

    def test_period_boundary_respects_user_timezone(self):
        """ของเข้า 23:30 เวลาไทยของวันสุดท้าย ต้องอยู่ในงวด ไม่หลุดไปเดือนหน้า"""
        # 2025-06-30 23:30 Asia/Bangkok == 2025-06-30 16:30 UTC
        self._do(self.product_b, 7, self.supplier, self.stock_a,
                 datetime(2025, 6, 30, 16, 30, 0))
        row = self._find(self._data(), "product", self.product_b.id)
        self.assertAlmostEqual(row["in_qty"], 7.0, places=3)
        # ในเขตเวลา UTC วันเดียวกันก็ยังอยู่ในงวด แต่ 17:30 UTC จะหลุดออกเมื่อใช้ไทย
        self._do(self.product_b, 9, self.supplier, self.stock_a,
                 datetime(2025, 6, 30, 17, 30, 0))
        row = self._find(self._data(), "product", self.product_b.id)
        self.assertAlmostEqual(
            row["in_qty"], 7.0, places=3,
            msg="a move after local midnight must fall outside the period",
        )

    def test_lot_level_splits_and_sums_back(self):
        lot_a = self._lot(self.product_lot, "SC-LOT-A")
        lot_b = self._lot(self.product_lot, "SC-LOT-B")
        self._do(self.product_lot, 6, self.supplier, self.stock_a, self.d1, lot=lot_a)
        self._do(self.product_lot, 4, self.supplier, self.stock_a, self.d2, lot=lot_b)
        data = self._data(group_lot=True, unfold_level=7)
        row_a = self._find(data, "lot", lot_a.id)
        row_b = self._find(data, "lot", lot_b.id)
        self.assertAlmostEqual(row_a["closing_qty"], 6.0, places=3)
        self.assertAlmostEqual(row_b["closing_qty"], 4.0, places=3)
        product_row = self._find(data, "product", self.product_lot.id)
        self.assertAlmostEqual(product_row["closing_qty"], 10.0, places=3)

    def test_warehouse_filter_still_shows_transfer_out_of_that_warehouse(self):
        """กรองคลัง A แล้วต้องยังเห็นการโอน 20 ที่ออกไปคลัง B เป็นรายการจ่าย"""
        data = self._data(warehouse_ids=[self.wh_a.id])
        row = self._find(data, "wh", self.wh_a.id)
        self.assertAlmostEqual(row["out_qty"], 50.0, places=3)
        self.assertIsNone(self._find(data, "wh", self.wh_b.id))

    def test_opening_basis_none_skips_opening(self):
        data = self._data(opening_basis="none")
        self.assertAlmostEqual(data["totals"]["opening_qty"], 0.0, places=3)
        self.assertTrue(data["checks"]["opening_skipped"])
