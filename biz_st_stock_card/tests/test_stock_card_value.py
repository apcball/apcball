# -*- coding: utf-8 -*-
"""มูลค่า — invariant หลักคือ "มูลค่าในงวดต้องกระทบกับ stock.valuation.layer" """

from odoo.tests.common import new_test_user, tagged

from .common import StockCardCommon


@tagged("post_install", "-at_install")
class TestStockCardValue(StockCardCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._do(cls.product, 100, cls.supplier, cls.stock_a, cls.before)
        cls._do(cls.product, 50, cls.supplier, cls.stock_a, cls.d1)
        cls._do(cls.product, 30, cls.stock_a, cls.customer, cls.d2)
        cls._do(cls.product, 20, cls.stock_a, cls.stock_b, cls.d3)

    def _svl_period_total(self, options):
        report = self.report
        domain = report._svl_period_domain(options)
        layers = self.env["stock.valuation.layer"].search(domain)
        return sum(layers.mapped("value"))

    def test_period_value_reconciles_to_svl_in_both_modes(self):
        for mode in ("imputed", "svl"):
            data = self._data(value_mode=mode)
            checks = data["checks"]
            self.assertTrue(
                checks["svl_reconciled"],
                "value did not reconcile in %s mode: diff=%s" % (mode, checks["svl_difference"]),
            )
            self.assertAlmostEqual(
                checks["svl_period_value"], self._svl_period_total(data["options"]), places=2
            )

    def test_in_value_equals_positive_svl_sum(self):
        data = self._data()
        options = data["options"]
        layers = self.env["stock.valuation.layer"].search(
            self.report._svl_period_domain(options) + [("quantity", ">", 0)]
        )
        expected = sum(layers.mapped("value"))
        self.assertAlmostEqual(data["totals"]["in_value_ext"], expected, places=2)

    def test_out_value_equals_negative_svl_sum_as_positive(self):
        data = self._data()
        options = data["options"]
        layers = self.env["stock.valuation.layer"].search(
            self.report._svl_period_domain(options) + [("quantity", "<", 0)]
        )
        expected = -sum(layers.mapped("value"))
        self.assertAlmostEqual(data["totals"]["out_value_ext"], expected, places=2)

    def test_imputed_internal_transfer_cancels_at_company_level(self):
        """การโอนภายในถูกตีมูลค่าเป็นคู่ ที่ระดับบริษัทจึงหักล้างกันหมด"""
        data = self._data(value_mode="imputed")
        checks = data["checks"]
        self.assertTrue(checks["imputed_internal"]["value"] > 0,
                        "the inter-warehouse transfer should carry an imputed value")
        self.assertAlmostEqual(checks["imputed_internal"]["net"], 0.0, places=2)
        self.assertTrue(checks["svl_reconciled"])

    def test_svl_mode_leaves_internal_transfer_at_zero_value(self):
        data = self._data(value_mode="svl")
        self.assertAlmostEqual(data["checks"]["imputed_internal"]["value"], 0.0, places=2)
        destination = self._find(data, "wh", self.wh_b.id)
        self.assertAlmostEqual(destination["in_qty"], 20.0, places=3)
        self.assertAlmostEqual(destination["in_value"], 0.0, places=2)

    def test_imputed_mode_values_the_receiving_warehouse(self):
        data = self._data(value_mode="imputed")
        destination = self._find(data, "wh", self.wh_b.id)
        self.assertGreater(destination["closing_value"], 0.0,
                           "the receiving warehouse must not hold stock worth nothing")

    def test_opening_value_reconciles_to_svl_opening(self):
        data = self._data()
        options = data["options"]
        layers = self.env["stock.valuation.layer"].search(
            self.report._svl_domain(options)
            + self.report._svl_date_domain(options, "<", options["datetime_from"])
        )
        self.assertAlmostEqual(
            data["totals"]["opening_value"], sum(layers.mapped("value")), places=2
        )

    def test_revaluation_appears_as_adjustment_with_no_quantity(self):
        """ปรับราคาต้นทุนสร้าง SVL ที่ quantity = 0 ต้องไปอยู่คอลัมน์ปรับมูลค่า"""
        before = self._data()["totals"]
        self.product.standard_price = 12.0
        layer = self.env["stock.valuation.layer"].search(
            [("product_id", "=", self.product.id), ("quantity", "=", 0)],
            order="id desc", limit=1,
        )
        self.assertTrue(layer, "changing the cost must create a zero-quantity layer")
        self._backdate_svl(layer, self.d2)

        after = self._data()
        self.assertAlmostEqual(after["totals"]["adj_value"], layer.value, places=2)
        # ส่วนที่มี SVL หนุนหลังต้องไม่ขยับ — การปรับมูลค่าไม่ใช่การรับเข้า
        self.assertAlmostEqual(
            after["totals"]["in_value_ext"], before["in_value_ext"], places=2
        )
        # แต่ ``in_value`` ขยับได้ตามจริง เพราะต้นทุนที่ใช้ประมาณการโอนภายในสูงขึ้น
        # (ทั้งขารับและขาจ่ายขยับเท่ากัน จึงยังกระทบยอดกับ SVL ได้)
        self.assertAlmostEqual(
            after["totals"]["in_value"] - after["totals"]["out_value"]
            - (before["in_value"] - before["out_value"]),
            0.0, places=2,
        )
        self.assertTrue(after["checks"]["svl_reconciled"],
                        "diff=%s" % after["checks"]["svl_difference"])

    def test_unattributable_value_goes_to_an_unassigned_node(self):
        """มูลค่าที่ไม่มีจำนวนถ่วงน้ำหนักต้องโผล่เป็นโหนด "ไม่ระบุคลัง" ไม่ใช่หายไป"""
        idle = self._make_product("SC Zero Balance", self.categ, 10.0)
        self._do(idle, 10, self.supplier, self.stock_a, self.before)
        self._do(idle, 10, self.stock_a, self.customer, self.before)
        layer = self.env["stock.valuation.layer"].create({
            "company_id": self.company.id, "product_id": idle.id,
            "quantity": 0.0, "unit_cost": 0.0, "value": 500.0,
            "description": "SC manual revaluation",
        })
        self._backdate_svl(layer, self.d2)

        data = self.report.get_report_data(self._options(product_ids=[idle.id]))
        self.assertTrue(data["checks"]["svl_reconciled"],
                        "diff=%s" % data["checks"]["svl_difference"])
        self.assertAlmostEqual(data["totals"]["adj_value"], 500.0, places=2)
        unassigned = self._find(data, "wh", 0)
        self.assertIsNotNone(unassigned, "the value must be visible under an unassigned row")
        self.assertAlmostEqual(unassigned["adj_value"], 500.0, places=2)

    def test_product_with_valuation_but_no_movement_still_reconciles(self):
        """สินค้าที่ไม่มีความเคลื่อนไหวเลยในงวด แต่มี SVL — ห้ามตกหาย"""
        ghost = self._make_product("SC Ghost", self.categ, 10.0)
        layer = self.env["stock.valuation.layer"].create({
            "company_id": self.company.id, "product_id": ghost.id,
            "quantity": 0.0, "unit_cost": 0.0, "value": 321.0,
            "description": "SC ghost revaluation",
        })
        self._backdate_svl(layer, self.d2)

        data = self.report.get_report_data(self._options(product_ids=[ghost.id]))
        self.assertAlmostEqual(data["totals"]["adj_value"], 321.0, places=2)
        self.assertTrue(data["checks"]["svl_reconciled"],
                        "diff=%s" % data["checks"]["svl_difference"])
        row = self._find(data, "product", ghost.id)
        self.assertIsNotNone(row, "a value-only product must still get a row")

    def test_warehouse_filter_does_not_overstate_value(self):
        """กรองคลัง A แล้ว A ต้องไม่ได้รับมูลค่า SVL ของทั้งสินค้าไปทั้งก้อน"""
        everything = self._data()
        filtered = self._data(warehouse_ids=[self.wh_a.id])
        row_all = self._find(everything, "wh", self.wh_a.id)
        row_filtered = self._find(filtered, "wh", self.wh_a.id)
        # ตัวหารของการกระจายมูลค่ามาจากชุดที่ไม่ถูกกรอง คลัง A จึงได้ส่วนแบ่งเท่าเดิม
        self.assertAlmostEqual(
            row_filtered["in_value"], row_all["in_value"], places=2,
            msg="filtering must not change the value attributed to a warehouse",
        )
        self.assertAlmostEqual(
            row_filtered["closing_value"], row_all["closing_value"], places=2
        )
        # และต้องไม่ได้รับมูลค่าของคลัง B มาด้วย
        self.assertLess(
            filtered["totals"]["closing_value"], everything["totals"]["closing_value"]
        )

    def test_scope_limited_report_reports_that_it_cannot_reconcile(self):
        """SVL ไม่มีมิติคลัง รายงานที่กรองคลังจึงต้องบอกว่ากระทบยอดไม่ได้ ไม่ใช่ฟ้องว่าผิด"""
        checks = self._data(warehouse_ids=[self.wh_b.id])["checks"]
        self.assertTrue(checks["svl_scope_limited"])
        self.assertFalse(checks["svl_reconciled"])
        unscoped = self._data()["checks"]
        self.assertFalse(unscoped["svl_scope_limited"])
        self.assertTrue(unscoped["svl_reconciled"])

    def test_multiple_svl_per_move_are_not_double_counted(self):
        data = self._data()
        options = data["options"]
        layers = self.env["stock.valuation.layer"].search(
            self.report._svl_period_domain(options)
        )
        by_move = {}
        for layer in layers:
            by_move.setdefault(layer.stock_move_id.id, 0)
            by_move[layer.stock_move_id.id] += 1
        self.assertAlmostEqual(
            data["checks"]["report_period_value"], sum(layers.mapped("value")), places=2,
            msg="report value drifted from SVL (layers per move: %s)" % by_move,
        )

    def test_avg_cost_is_value_over_qty_not_a_unit_cost_aggregate(self):
        """``unit_cost`` มี group_operator=None จะรวมยอดไม่ได้ ต้องหารเอง"""
        row = self._find(self._data(), "product", self.product.id)
        self.assertAlmostEqual(
            row["avg_cost"], row["closing_value"] / row["closing_qty"], places=4
        )

    def test_consignment_lines_excluded_by_default(self):
        owner = self.env["res.partner"].create({"name": "SC Consignee"})
        self._do(self.product_b, 12, self.supplier, self.stock_a, self.d1, owner=owner)
        without = self._data()
        self.assertIsNone(self._find(without, "product", self.product_b.id))
        with_consignment = self._data(include_consignment=True)
        row = self._find(with_consignment, "product", self.product_b.id)
        self.assertAlmostEqual(row["in_qty"], 12.0, places=3)

    def test_value_hidden_for_user_without_accounting_rights(self):
        """ผู้ใช้ที่ไม่มีสิทธิ์บัญชีต้องได้รายงานจำนวน ไม่ใช่ AccessError"""
        user = new_test_user(
            self.env, login="sc_stock_only", groups="stock.group_stock_user",
            company_ids=[(6, 0, [self.company.id])], company_id=self.company.id,
        )
        data = self.report.with_user(user).get_report_data(self._options())
        self.assertFalse(data["options"]["show_value"])
        self.assertEqual(data["checks"]["value_hidden_reason"], "no_accounting_group")
        for key in ("opening_value", "in_value", "out_value", "closing_value"):
            self.assertAlmostEqual(data["totals"][key], 0.0, places=2)
        # จำนวนยังต้องใช้งานได้เต็มที่
        self.assertAlmostEqual(data["totals"]["closing_qty"], 120.0, places=3)

    def test_accounting_user_without_stock_manager_can_read_value(self):
        """ACL ของ SVL ให้เฉพาะ stock manager — เส้นทาง sudo ต้องทำงานให้ฝ่ายบัญชี"""
        user = new_test_user(
            self.env, login="sc_accountant",
            groups="stock.group_stock_user,account.group_account_readonly",
            company_ids=[(6, 0, [self.company.id])], company_id=self.company.id,
        )
        self.assertFalse(user.has_group("stock.group_stock_manager"))
        data = self.report.with_user(user).get_report_data(self._options())
        self.assertTrue(data["options"]["show_value"])
        self.assertTrue(data["checks"]["svl_reconciled"])
        self.assertGreater(data["totals"]["closing_value"], 0.0)

    def test_user_without_stock_rights_is_refused(self):
        user = new_test_user(self.env, login="sc_nobody", groups="base.group_user")
        with self.assertRaises(Exception):
            self.report.with_user(user).get_report_data(self._options())
