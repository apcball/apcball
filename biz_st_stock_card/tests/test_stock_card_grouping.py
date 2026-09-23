# -*- coding: utf-8 -*-
"""การจัดกลุ่ม — สองแกนต้องให้ตัวเลขเดียวกัน และยอดรวมต้องไม่นับซ้ำ"""

from odoo.exceptions import UserError
from odoo.tests.common import tagged

from .common import StockCardCommon

MEASURES = (
    "opening_qty", "in_qty", "out_qty", "closing_qty",
    "opening_value", "in_value", "out_value", "adj_value", "closing_value",
)


@tagged("post_install", "-at_install")
class TestStockCardGrouping(StockCardCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._do(cls.product, 100, cls.supplier, cls.stock_a, cls.before)
        cls._do(cls.product, 50, cls.supplier, cls.stock_a, cls.d1)
        cls._do(cls.product, 30, cls.stock_a, cls.customer, cls.d2)
        cls._do(cls.product, 20, cls.stock_a, cls.stock_b, cls.d3)
        cls._do(cls.product_b, 40, cls.supplier, cls.stock_b, cls.d1)
        cls._do(cls.product_b, 5, cls.stock_b, cls.customer, cls.d3)

    def _totals(self, **kw):
        data = self._data(**kw)
        return data, {key: round(data["totals"][key], 2) for key in MEASURES}

    def test_both_group_modes_produce_identical_totals(self):
        _, wh_first = self._totals(group_mode="wh_product")
        _, product_first = self._totals(group_mode="product_wh")
        self.assertEqual(wh_first, product_first)

    def test_both_group_modes_produce_identical_leaf_measures(self):
        """ใบเดียวกันต้องได้ตัวเลขเดียวกัน แม้เส้นทางจะสลับลำดับ"""
        def leaves(mode):
            data = self._data(group_mode=mode, unfold_level=7)
            out = {}
            for line in data["lines"]:
                if line["kind"] != "group" or line["child_count"]:
                    continue
                key = tuple(sorted(line["id"].split("/")))
                out[key] = tuple(round(line[m], 2) for m in MEASURES)
            return out
        self.assertEqual(leaves("wh_product"), leaves("product_wh"))

    def test_counts_to_total_rows_sum_to_grand_total(self):
        """แถวที่ติดธง counts_to_total ต้องบวกได้เท่ายอดรวมใหญ่ ทุกโหมด ทุกความลึก"""
        for mode in ("wh_product", "product_wh"):
            for depth in (0, 1, 3, 7):
                data = self._data(group_mode=mode, unfold_level=depth)
                flagged = [line for line in data["lines"] if line["counts_to_total"]]
                for measure in MEASURES:
                    self.assertAlmostEqual(
                        sum(line[measure] for line in flagged),
                        data["totals"][measure], places=2,
                        msg="%s mismatch in %s at depth %s" % (measure, mode, depth),
                    )

    def test_group_total_rows_never_count_to_total(self):
        data = self._data(unfold_level=7)
        for line in data["lines"]:
            if line["kind"] != "group":
                self.assertFalse(
                    line["counts_to_total"],
                    "%s row must not count to total" % line["kind"],
                )
            elif line["level"] != 0:
                self.assertFalse(line["counts_to_total"])

    def test_row_ids_are_unique_and_parents_resolve(self):
        data = self._data(group_categ=True, group_location=True, group_lot=True,
                          unfold_level=7, detail_mode="all")
        ids = [line["id"] for line in data["lines"]]
        self.assertEqual(len(ids), len(set(ids)), "duplicate row ids break OWL t-key")
        known = set(ids)
        for line in data["lines"]:
            if line["parent_id"]:
                self.assertIn(line["parent_id"], known, "orphan parent on %s" % line["id"])

    def test_level_equals_path_depth(self):
        data = self._data(group_categ=True, group_location=True, unfold_level=7)
        for line in data["lines"]:
            if line["kind"] == "group":
                self.assertEqual(line["level"], line["id"].count("/"))

    def test_unfold_level_changes_rows_but_never_totals(self):
        _, shallow = self._totals(unfold_level=0)
        _, deep = self._totals(unfold_level=7)
        self.assertEqual(shallow, deep)
        self.assertLess(
            len(self._data(unfold_level=0)["lines"]),
            len(self._data(unfold_level=7)["lines"]),
        )

    def test_unfolded_id_expands_only_that_branch(self):
        data = self._data(unfold_level=1)
        warehouse_row = self._find(data, "wh", self.wh_a.id)
        collapsed = self._data(unfold_level=0)
        expanded = self._data(unfold_level=0, unfolded=[warehouse_row["id"]])
        self.assertGreater(len(expanded["lines"]), len(collapsed["lines"]))
        children = [
            line for line in expanded["lines"]
            if line["parent_id"] == warehouse_row["id"] and line["kind"] == "group"
        ]
        self.assertTrue(children)
        other = self._find(expanded, "wh", self.wh_b.id)
        siblings = [
            line for line in expanded["lines"]
            if line["parent_id"] == other["id"] and line["kind"] == "group"
        ]
        self.assertFalse(siblings, "expanding one branch must not expand the others")

    def test_optional_levels_never_change_totals(self):
        _, base = self._totals()
        for categ in (False, True):
            for location in (False, True):
                for lot in (False, True):
                    _, got = self._totals(
                        group_categ=categ, group_location=location, group_lot=lot
                    )
                    self.assertEqual(
                        got, base,
                        "levels categ=%s loc=%s lot=%s changed the totals"
                        % (categ, location, lot),
                    )

    def test_category_level_groups_and_subtotals(self):
        data = self._data(group_categ=True, unfold_level=7)
        row = self._find(data, "categ", self.categ.id)
        self.assertIsNotNone(row)
        children = [
            line for line in data["lines"]
            if line["parent_id"] == row["id"] and line["kind"] == "group"
        ]
        self.assertTrue(children)
        self.assertAlmostEqual(
            sum(child["closing_qty"] for child in children), row["closing_qty"], places=3
        )

    def test_display_product_movement_hides_idle_rows_but_keeps_totals(self):
        # สินค้าที่ไม่มีความเคลื่อนไหวและไม่มียอดเลย ต้องไม่โผล่ในโหมด movement
        idle = self._make_product("SC Idle", self.categ, 1.0)
        options = {"product_ids": [self.product.id, self.product_b.id, idle.id]}
        movement = self._data(display_product="movement", **options)
        self.assertIsNone(self._find(movement, "product", idle.id))
        every = self._data(display_product="all", **options)
        for measure in MEASURES:
            self.assertAlmostEqual(
                movement["totals"][measure], every["totals"][measure], places=2
            )

    def test_max_groups_is_clamped_to_a_usable_floor(self):
        options = self.report._normalize_options(self._options(max_groups=1))
        self.assertEqual(options["max_groups"], 1000)

    def test_exceeding_max_groups_raises_an_actionable_error(self):
        """ขีดจำกัดถูก clamp ไว้ที่ 1000 จึงยิงเข้าที่ตัวป้องกันโดยตรง"""
        options = dict(self.report._normalize_options(self._options()), max_groups=2)
        nodes = {}
        with self.assertRaises(UserError) as caught:
            for index in range(5):
                self.report._add_fact(
                    nodes, (1, 1, index, 0, 0), "period", "in", 1.0, True, options
                )
        message = str(caught.exception)
        self.assertIn("เกินขีดจำกัด", message)
        self.assertIn("กรอง", message, "the error must tell the user what to do next")

    def test_detail_mode_all_downgrades_without_a_product_filter(self):
        options = self._options(detail_mode="all")
        options["product_ids"] = []
        options["categ_ids"] = []
        data = self.report.get_report_data(options)
        self.assertEqual(data["options"]["detail_mode"], "unfolded")
        self.assertTrue(data["checks"]["detail_downgraded"])

    def test_detail_mode_all_is_kept_with_a_product_filter(self):
        data = self._data(detail_mode="all", product_ids=[self.product.id])
        self.assertEqual(data["options"]["detail_mode"], "all")
        self.assertFalse(data["checks"]["detail_downgraded"])
        self.assertTrue([line for line in data["lines"] if line["kind"] == "move"])
