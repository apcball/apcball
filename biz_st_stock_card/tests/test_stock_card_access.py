# -*- coding: utf-8 -*-
"""สิทธิ์ หลายบริษัท drill-down และการส่งออกไฟล์"""

import io

from odoo.exceptions import AccessError
from odoo.tests.common import tagged

from .common import StockCardCommon, read_xlsx

MEASURES = (
    "opening_qty", "in_qty", "out_qty", "closing_qty",
    "opening_value", "in_value", "out_value", "adj_value", "closing_value",
)


@tagged("post_install", "-at_install")
class TestStockCardAccess(StockCardCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._do(cls.product, 100, cls.supplier, cls.stock_a, cls.before)
        cls._do(cls.product, 50, cls.supplier, cls.stock_a, cls.d1)
        cls._do(cls.product, 30, cls.stock_a, cls.customer, cls.d2)
        cls._do(cls.product, 20, cls.stock_a, cls.stock_b, cls.d3)

    # ------------------------------------------------------------- options
    def test_normalize_options_clamps_and_whitelists(self):
        options = self.report._normalize_options({
            "company_ids": [self.company.id],
            "date_from": "2025-06-30", "date_to": "2025-06-01",  # กลับด้าน
            "company_mode": "bogus", "group_mode": "bogus", "detail_mode": "bogus",
            "value_mode": "bogus", "value_date_basis": "bogus", "opening_basis": "bogus",
            "display_product": "bogus", "date_format": "bogus",
            "unfold_level": 99, "detail_limit": 99999, "max_groups": 1,
            "tz": "Mars/Olympus", "unfolded": ["ok-1/prod-2", "DROP ME", 42],
            "product_ids": ["7", None, 7],
        })
        self.assertEqual(options["date_from"], "2025-06-01")  # สลับให้แล้ว
        self.assertEqual(options["date_to"], "2025-06-30")
        self.assertEqual(options["company_mode"], "consolidated")
        self.assertEqual(options["group_mode"], "wh_product")
        self.assertEqual(options["detail_mode"], "unfolded")
        self.assertEqual(options["value_mode"], "imputed")
        self.assertEqual(options["value_date_basis"], "move")
        self.assertEqual(options["opening_basis"], "moves")
        self.assertEqual(options["display_product"], "movement")
        self.assertEqual(options["date_format"], "be")
        self.assertEqual(options["unfold_level"], 7)
        self.assertEqual(options["detail_limit"], 2000)
        self.assertEqual(options["max_groups"], 1000)
        self.assertEqual(options["tz"], "UTC")
        self.assertEqual(options["unfolded"], ["ok-1/prod-2"])
        self.assertEqual(options["product_ids"], [7])

    def test_accounting_value_date_basis_downgrades_without_the_field(self):
        """ไม่มี stock_fifo_by_location ติดตั้ง → ไม่มี accounting_date บน SVL

        ต้องลดระดับกลับ "move" เงียบ ๆ พร้อมติดแฟล็กบอกเหตุผล ไม่ error
        """
        options = self.report._normalize_options(self._options(value_date_basis="accounting"))
        if self.report._svl_has_accounting_date():
            self.skipTest("stock_fifo_by_location is installed in this test DB")
        self.assertEqual(options["value_date_basis"], "move")
        self.assertTrue(options["value_date_basis_downgraded"])

    def test_normalize_options_is_idempotent(self):
        once = self.report._normalize_options(self._options())
        twice = self.report._normalize_options(once)
        self.assertEqual(once, twice)

    def test_period_bounds_are_local_midnight_in_utc(self):
        options = self.report._normalize_options(self._options(tz="Asia/Bangkok"))
        self.assertEqual(options["datetime_from"], "2025-05-31 17:00:00")
        self.assertEqual(options["datetime_to"], "2025-06-30 16:59:59")

    # ------------------------------------------------- multi-company
    def test_company_outside_user_access_is_refused(self):
        outsider = self.env["res.company"].create({"name": "SC Outsider Co"})
        # res.company.create() ผูกบริษัทใหม่เข้ากับผู้สร้างให้อัตโนมัติ ต้องถอดออกก่อน
        # ถึงจะจำลอง "บริษัทที่ผู้ใช้ไม่มีสิทธิ์" ได้จริง
        self.env.user.company_ids = [(3, outsider.id)]
        self.assertNotIn(outsider, self.env.user.company_ids)
        with self.assertRaises(AccessError):
            self.report.get_report_data({
                "company_ids": [outsider.id],
                "date_from": self.date_from, "date_to": self.date_to,
            })

    def test_requested_company_works_even_when_not_in_the_switcher(self):
        """ir.rule ของ stock อิง env.companies — รายงานต้องไม่ว่างเปล่าเพราะ switcher"""
        other = self.env["res.company"].create({"name": "SC Switcher Co"})
        self.env.user.company_ids = [(4, other.id)]
        # จำลองผู้ใช้ที่ติ๊กเฉพาะบริษัทอื่นไว้ใน switcher แล้วขอรายงานของบริษัทหลัก
        scoped = self.report.with_context(allowed_company_ids=[other.id])
        data = scoped.get_report_data(self._options())
        self.assertTrue(self._product_rows(data),
                        "ir.rule scoping swallowed the data silently")
        self.assertAlmostEqual(data["totals"]["closing_qty"], 120.0, places=3)

    def test_consolidated_and_split_totals_are_identical(self):
        consolidated = self._data(company_mode="consolidated")["totals"]
        split = self._data(company_mode="split")["totals"]
        for measure in MEASURES:
            self.assertAlmostEqual(consolidated[measure], split[measure], places=2)

    def test_split_mode_adds_a_company_level_only_with_several_companies(self):
        single = self._data(company_mode="split")
        self.assertNotEqual(single["levels"][0]["type"], "company")
        other = self.env["res.company"].create({"name": "SC Second Co"})
        self.env.user.company_ids = [(4, other.id)]
        both = self._data(company_mode="split",
                          company_ids=[self.company.id, other.id])
        self.assertEqual(both["levels"][0]["type"], "company")

    def test_mixed_currency_is_flagged_not_silently_summed(self):
        currency = self.env["res.currency"].with_context(active_test=False).search(
            [("id", "!=", self.company.currency_id.id)], limit=1
        )
        if not currency:
            self.skipTest("no second currency available")
        other = self.env["res.company"].create({
            "name": "SC Yen Co", "currency_id": currency.id,
        })
        self.env.user.company_ids = [(4, other.id)]
        data = self._data(company_ids=[self.company.id, other.id])
        self.assertTrue(data["checks"]["mixed_currency"])
        self.assertEqual(data["checks"]["mixed_currency"][0]["id"], other.id)

    def test_allowed_companies_matches_user_company_ids(self):
        data = self._data()
        self.assertEqual(
            {c["id"] for c in data["allowed_companies"]},
            set(self.env.user.company_ids.ids),
        )

    # ------------------------------------------------------ drill-down
    def test_drill_down_action_carries_views(self):
        data = self._data()
        row = self._find(data, "product", self.product.id)
        action = self.report.action_drill_down(row["id"], data["options"], "moves")
        # OWL doAction ไม่ผ่าน clean_action — ขาด views แล้วพังที่ _preprocessAction
        self.assertIn("views", action)
        self.assertEqual(action["views"], [(False, "list"), (False, "form")])
        self.assertEqual(action["res_model"], "stock.move.line")

    def test_drill_down_domain_reproduces_the_row(self):
        data = self._data()
        row = self._find(data, "wh", self.wh_a.id)
        action = self.report.action_drill_down(row["id"], data["options"], "moves")
        lines = self.env["stock.move.line"].search(action["domain"])
        self.assertAlmostEqual(
            sum(lines.mapped("quantity_product_uom")),
            row["in_qty"] + row["out_qty"], places=3,
        )

    def test_valuation_drill_down_is_product_level_and_says_so(self):
        data = self._data()
        row = self._find(data, "product", self.product.id)
        action = self.report.action_drill_down(row["id"], data["options"], "valuation")
        self.assertEqual(action["res_model"], "stock.valuation.layer")
        self.assertIn("ระดับบริษัท", action["name"])

    def test_move_row_drills_to_its_document(self):
        data = self._data(unfold_level=7, detail_mode="all")
        move = next(line for line in data["lines"] if line["kind"] == "move")
        action = self.report.action_drill_down(move["id"], data["options"], "document")
        self.assertIn(action["res_model"], ("stock.picking", "stock.move.line"))

    # ---------------------------------------------------------- exports
    def test_xlsx_export_has_the_expected_sheets_and_formula_total(self):
        book = read_xlsx(self.env["biz.stock.card.xlsx"].generate(self._options()))
        self.assertEqual(
            list(book), ["สต๊อกการ์ด", "สรุประดับบนสุด", "ข้อสังเกต"]
        )
        formulas = [
            cell for row in book["สต๊อกการ์ด"] for cell in row
            if isinstance(cell, str) and cell.startswith("=SUMPRODUCT(")
        ]
        self.assertTrue(formulas, "the grand total must be a checkable formula")

    def test_xlsx_notes_sheet_reports_the_reconciliation(self):
        book = read_xlsx(self.env["biz.stock.card.xlsx"].generate(self._options()))
        text = " ".join(
            str(cell) for row in book["ข้อสังเกต"] for cell in row if cell is not None
        )
        self.assertIn("กระทบยอดได้", text)
        self.assertIn("การโอนข้ามคลัง", text)

    def test_pdf_html_embeds_the_thai_font_without_escaped_quotes(self):
        wizard = self.env["biz.stock.card.wizard"]._create_from_options(self._options())
        report = self.env.ref("biz_st_stock_card.action_report_stock_card")
        html = report._render_qweb_html(
            report.report_name, wizard.ids, data={"options": self._options()}
        )[0]
        if isinstance(html, bytes):
            html = html.decode("utf-8")
        self.assertIn("font-family:Sarabun", html)
        self.assertIn("data:font/truetype;base64,", html)
        # QWeb escape single-quote เป็น &#39; แล้ว wkhtmltopdf อ่าน @font-face ไม่ออก
        font_face = html[html.index("@font-face"):html.index("@font-face") + 400]
        self.assertNotIn("&#39;", font_face)

    def test_all_three_outputs_agree_on_the_grand_total(self):
        options = self._options()
        data = self.report.get_report_data(options)
        screen = round(data["totals"]["closing_qty"], 2)

        book = read_xlsx(self.env["biz.stock.card.xlsx"].generate(options))
        columns = self.report.report_columns(data)
        index = next(i for i, col in enumerate(columns) if col["key"] == "closing_qty")
        values = [
            row[index] for row in book["สรุประดับบนสุด"]
            if len(row) > index and isinstance(row[index], (int, float))
        ]
        self.assertAlmostEqual(round(values[-1], 2), screen, places=2)

        report = self.env.ref("biz_st_stock_card.action_report_stock_card")
        wizard = self.env["biz.stock.card.wizard"]._create_from_options(options)
        html = report._render_qweb_html(
            report.report_name, wizard.ids, data={"options": options}
        )[0]
        if isinstance(html, bytes):
            html = html.decode("utf-8")
        self.assertIn("{:,.2f}".format(screen), html)

    def test_wizard_round_trip_preserves_options(self):
        wizard = self.env["biz.stock.card.wizard"]._create_from_options(
            self._options(group_mode="product_wh", group_lot=True, value_mode="svl")
        )
        options = wizard._get_options()
        self.assertEqual(options["group_mode"], "product_wh")
        self.assertTrue(options["group_lot"])
        self.assertEqual(options["value_mode"], "svl")
        action = wizard.action_view_report()
        self.assertEqual(action["tag"], "biz_st_stock_card.stock_card")
        self.assertIn("sc_options", action["context"])
