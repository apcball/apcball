# -*- coding: utf-8 -*-
"""มูลค่า — กระทบกับ stock.valuation.layer และซอยลงช่วงอายุ"""

from odoo.tests.common import tagged

from .common import StockAgingCommon, days_ago


@tagged("post_install", "-at_install")
class TestAgingValue(StockAgingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._seed_standard()

    def _svl_value(self, products):
        layers = self.env["stock.valuation.layer"].search([
            ("product_id", "in", products.ids), ("company_id", "=", self.company.id),
        ])
        return sum(layers.mapped("value"))

    def test_bucket_values_sum_to_row_value(self):
        data = self._data(unfold_level=7, group_lot=True)
        for line in data["lines"]:
            if line["kind"] != "group":
                continue
            total = sum(line["b%d_value" % i] for i in range(6))
            if line["closing_qty"] > 0:
                self.assertAlmostEqual(total, line["closing_value"], places=2, msg=line["id"])

    def test_closing_value_reconciles_to_svl(self):
        data = self._data()
        self.assertTrue(data["checks"]["svl_reconciled"], data["checks"])
        self.assertAlmostEqual(data["totals"]["closing_value"],
                               self._svl_value(self.all_products), places=2)
        self.assertAlmostEqual(data["checks"]["svl_difference"], 0.0, places=2)

    def test_value_follows_average_cost_of_product(self):
        data = self._data(unfold_level=7)
        row = self._product_row(data, self.product_w, self.wh_a)
        # ต้นทุนเฉลี่ย ณ วันที่ = มูลค่า SVL ของสินค้า ÷ จำนวน SVL
        expected = self._svl_value(self.product_w)
        self.assertAlmostEqual(row["closing_value"], expected, places=2)
        unit = expected / 120.0
        self.assertAlmostEqual(row["b0_value"], 60 * unit, places=2)
        self.assertAlmostEqual(row["b3_value"], 60 * unit, places=2)

    def test_warehouse_filter_does_not_overstate_value(self):
        full = self._data(unfold_level=7)
        part = self._data(unfold_level=7, warehouse_ids=[self.wh_b.id])
        self.assertTrue(part["checks"]["svl_scope_limited"])
        row_full = self._product_row(full, self.product_c, self.wh_b)
        row_part = self._product_row(part, self.product_c, self.wh_b)
        self.assertAlmostEqual(row_part["closing_value"], row_full["closing_value"], places=2)
        self.assertLess(row_part["closing_value"], self._svl_value(self.product_c))
        self.assertIsNone(self._product_row(part, self.product_c, self.wh_a))

    def test_svl_value_without_quantity_goes_to_unassigned_node(self):
        product = self._make_product("AG Ghost", self.categ, 1.0, code="AGH")
        self._do(product, 10, self.supplier, self.stock_a, days_ago(30), price=1.0)
        self._do(product, 10, self.stock_a, self.customer, days_ago(20))
        # ปรับมูลค่าล้วน ๆ (ไม่มีจำนวน) หลังของหมด
        layer = self.env["stock.valuation.layer"].create({
            "product_id": product.id, "company_id": self.company.id,
            "quantity": 0.0, "value": 7.5, "description": "AG landed cost",
        })
        # ชั้นที่ไม่ผูก move ใช้ create_date เป็นวันที่ — ต้องย้อนให้อยู่ก่อน ณ วันที่
        self._backdate_svl(layer, days_ago(10))
        data = self._data(product_ids=[product.id], unfold_level=7)
        self.assertTrue(data["checks"]["svl_reconciled"], data["checks"])
        wh_rows = [l for l in data["lines"] if l["kind"] == "group" and l["group_type"] == "wh"]
        self.assertTrue(any(r["res_id"] == 0 for r in wh_rows), "unassigned warehouse row missing")
        self.assertAlmostEqual(data["totals"]["closing_value"], 7.5, places=2)
        self.assertAlmostEqual(data["checks"]["unbucketed_value"], 7.5, places=2)

    def test_user_without_value_rights_sees_quantities_only(self):
        user = self.env["res.users"].create({
            "name": "AG Stock Only", "login": "ag_stock_only",
            "groups_id": [(6, 0, [self.env.ref("stock.group_stock_user").id])],
        })
        data = self.report.with_user(user).get_report_data(self._options(unfold_level=7))
        self.assertFalse(data["options"]["show_value"])
        self.assertEqual(data["checks"]["value_hidden_reason"], "no_accounting_group")
        row = self._product_row(data, self.product_w, self.wh_a)
        self.assertAlmostEqual(row["closing_qty"], 120.0, places=3)
        self.assertEqual(row["closing_value"], 0.0)
        self.assertIsNone(data["kpis"]["closing_value"])
        self.assertIsNone(data["kpis"]["over"][0]["value"])
        self.assertFalse(any(c["type"] == "money" for c in data["columns"]))

    def test_accounting_user_without_stock_manager_reads_svl(self):
        user = self.env["res.users"].create({
            "name": "AG Accountant", "login": "ag_accountant",
            "groups_id": [(6, 0, [
                self.env.ref("stock.group_stock_user").id,
                self.env.ref("account.group_account_readonly").id,
            ])],
        })
        data = self.report.with_user(user).get_report_data(self._options())
        self.assertTrue(data["options"]["show_value"])
        self.assertAlmostEqual(data["totals"]["closing_value"],
                               self._svl_value(self.all_products), places=2)
