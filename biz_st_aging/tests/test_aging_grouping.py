# -*- coding: utf-8 -*-
"""การจัดกลุ่ม — สองแกนเท่ากัน, counts_to_total, การกาง"""

from odoo.exceptions import UserError
from odoo.tests.common import tagged

from .common import StockAgingCommon

ADDITIVE = ["closing_qty", "closing_value", "usage_qty", "bucketed_qty"] + [
    "b%d_qty" % i for i in range(6)
] + ["b%d_value" % i for i in range(6)]


@tagged("post_install", "-at_install")
class TestAgingGrouping(StockAgingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._seed_standard()

    def test_both_axes_produce_identical_totals_and_kpis(self):
        a = self._data(group_mode="wh_product")
        b = self._data(group_mode="product_wh")
        for key in ADDITIVE:
            self.assertAlmostEqual(a["totals"][key], b["totals"][key], places=2, msg=key)
        self.assertEqual(a["totals"]["avg_age"], b["totals"]["avg_age"])
        self.assertEqual(a["kpis"]["risk"], b["kpis"]["risk"])
        self.assertEqual(a["kpis"]["over"], b["kpis"]["over"])

    def test_optional_levels_and_unfold_never_change_totals(self):
        base = self._data()["totals"]
        for kw in (
            {"group_categ": True}, {"unfold_level": 0}, {"unfold_level": 7},
            {"group_categ": True, "unfold_level": 7}, {"group_mode": "product_wh", "unfold_level": 0},
        ):
            totals = self._data(**kw)["totals"]
            for key in ADDITIVE:
                self.assertAlmostEqual(totals[key], base[key], places=2, msg="%s %s" % (kw, key))
        # เปิดระดับ ที่เก็บ/ล็อต เปลี่ยน "ที่ที่นับอายุ" ช่วงอายุจึงต่างได้โดยตั้งใจ แต่ยอดคงเหลือ/การใช้/
        # จำนวนที่จัดชั้นต้องเท่าเดิมเสมอ
        for kw in ({"group_location": True}, {"group_lot": True}):
            totals = self._data(**kw)["totals"]
            for key in ("closing_qty", "closing_value", "usage_qty", "bucketed_qty"):
                self.assertAlmostEqual(totals[key], base[key], places=2, msg="%s %s" % (kw, key))

    def test_counts_to_total_rows_sum_to_grand_total(self):
        for kw in ({"group_mode": "wh_product", "unfold_level": 7},
                   {"group_mode": "product_wh", "unfold_level": 7, "group_lot": True},
                   {"group_mode": "wh_product", "unfold_level": 0}):
            data = self._data(**kw)
            top = [l for l in data["lines"] if l.get("counts_to_total")]
            self.assertTrue(top)
            self.assertTrue(all(l["level"] == 0 and l["kind"] == "group" for l in top))
            for key in ADDITIVE:
                self.assertAlmostEqual(sum(l[key] for l in top), data["totals"][key], places=2,
                                       msg="%s %s" % (kw, key))
            self.assertFalse(any(l.get("counts_to_total") for l in data["lines"] if l["kind"] == "group_total"))

    def test_row_ids_are_unique_and_parents_resolve(self):
        data = self._data(unfold_level=7, group_categ=True, group_lot=True, group_location=True)
        ids = [l["id"] for l in data["lines"]]
        self.assertEqual(len(ids), len(set(ids)))
        known = set(ids)
        for line in data["lines"]:
            if line["parent_id"]:
                self.assertIn(line["parent_id"], known)
                self.assertEqual(line["level"], line["id"].count("/") - (1 if line["kind"] == "group_total" else 0))

    def test_product_row_buckets_equal_sum_of_children(self):
        data = self._data(unfold_level=7, group_lot=True)
        product = self._product_row(data, self.product_l, self.wh_a)
        children = [l for l in data["lines"] if l["parent_id"] == product["id"] and l["kind"] == "group"]
        self.assertEqual(len(children), 2)
        for key in ADDITIVE:
            self.assertAlmostEqual(sum(c[key] for c in children), product[key], places=2, msg=key)

    def test_folded_rows_hide_children_and_unfolded_ids_show_them(self):
        folded = self._data(unfold_level=0)
        self.assertTrue(all(l["level"] == 0 for l in folded["lines"]))
        wh_row = self._find(folded, "wh", self.wh_a.id)
        self.assertFalse(wh_row["unfolded"])
        opened = self._data(unfold_level=0, unfolded=[wh_row["id"]])
        self.assertTrue(self._find(opened, "wh", self.wh_a.id)["unfolded"])
        self.assertIsNotNone(self._product_row(opened, self.product_w, self.wh_a))
        self.assertIsNone(self._product_row(opened, self.product_b, self.wh_b))
        self.assertTrue(any(l["kind"] == "group_total" and l["parent_id"] == wh_row["id"]
                            for l in opened["lines"]))

    def test_product_search_and_category_filters(self):
        data = self._data(product_ids=[], product_search="AGW", unfold_level=7)
        products = {l["res_id"] for l in self._rows(data, "product")}
        self.assertIn(self.product_w.id, products)
        self.assertNotIn(self.product_b.id, products)
        data = self._data(product_ids=[], categ_ids=[self.categ_other.id], unfold_level=7)
        products = {l["res_id"] for l in self._rows(data, "product")}
        self.assertIn(self.product_b.id, products)
        self.assertNotIn(self.product_w.id, products)

    def test_max_groups_is_enforced_with_actionable_error(self):
        nodes = {("x", i, 0, 0, 0): {} for i in range(1000)}
        with self.assertRaises(UserError):
            self.report._add_fact(
                nodes, ("y", 0, 0, 0, 0), "period", "in", 1.0, True, {"max_groups": 1000},
            )
