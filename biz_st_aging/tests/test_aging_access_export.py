# -*- coding: utf-8 -*-
"""options, สิทธิ์, หลายบริษัท, drill-down, การส่งออกไฟล์, config"""

from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import tagged

from .common import StockAgingCommon, days_ago, read_xlsx


@tagged("post_install", "-at_install")
class TestAgingAccessExport(StockAgingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._seed_standard()

    # ------------------------------------------------------------- options
    def test_normalize_options_clamps_and_whitelists(self):
        options = self.report._normalize_options({
            "company_ids": [self.company.id],
            "date_to": "2025-06-30",
            "company_mode": "bogus", "group_mode": "bogus", "age_basis": "bogus",
            "cost_basis": "bogus", "display_product": "bogus", "date_format": "bogus",
            "unfold_level": 99, "max_groups": 1,
            "tz": "Mars/Olympus", "unfolded": ["wh-1/prod-2", "DROP ME", 42],
            "product_ids": ["7", None, 7], "product_search": 12,
        })
        self.assertEqual(options["date_from"], "2025-01-01")
        self.assertEqual(options["company_mode"], "consolidated")
        self.assertEqual(options["group_mode"], "wh_product")
        self.assertEqual(options["age_basis"], "node_in")
        self.assertEqual(options["cost_basis"], "average")
        self.assertEqual(options["display_product"], "on_hand")
        self.assertEqual(options["date_format"], "be")
        self.assertEqual(options["unfold_level"], 7)
        self.assertEqual(options["max_groups"], 1000)
        self.assertEqual(options["tz"], "UTC")
        self.assertEqual(options["unfolded"], ["wh-1/prod-2"])
        self.assertEqual(options["product_ids"], [7])
        self.assertEqual(options["product_search"], "")
        self.assertEqual(options["bucket_edges"], [30, 60, 90, 180, 365])
        self.assertEqual(len(options["buckets"]), 6)

    def test_normalize_options_is_idempotent(self):
        once = self.report._normalize_options(self._options())
        twice = self.report._normalize_options(once)
        self.assertEqual(once, twice)

    def test_period_bounds_are_local_midnight_in_utc(self):
        options = self.report._normalize_options(self._options(tz="Asia/Bangkok"))
        self.assertEqual(options["datetime_from"], "2024-12-31 17:00:00")
        self.assertEqual(options["datetime_to"], "2025-06-30 16:59:59")

    # ------------------------------------------------- access / companies
    def test_user_without_stock_rights_is_refused(self):
        user = self.env["res.users"].create({
            "name": "AG Nobody", "login": "ag_nobody",
            "groups_id": [(6, 0, [self.env.ref("base.group_user").id])],
        })
        with self.assertRaises(AccessError):
            self.report.with_user(user).get_report_data(self._options())

    def test_company_outside_user_access_is_refused(self):
        outsider = self.env["res.company"].create({"name": "AG Outsider Co"})
        # res.company.create() ผูกบริษัทใหม่เข้ากับผู้สร้างให้อัตโนมัติ ต้องถอดออกก่อน
        self.env.user.company_ids = [(3, outsider.id)]
        with self.assertRaises(AccessError):
            self.report.get_report_data({"company_ids": [outsider.id], "date_to": self.date_to})

    def test_requested_company_works_even_when_not_in_the_switcher(self):
        other = self.env["res.company"].create({"name": "AG Switcher Co"})
        self.env.user.company_ids = [(4, other.id)]
        scoped = self.report.with_context(allowed_company_ids=[other.id])
        data = scoped.get_report_data(self._options())
        self.assertTrue(self._rows(data, "product"), "ir.rule scoping swallowed the data silently")
        self.assertAlmostEqual(data["totals"]["closing_qty"], 120 + 40 + 60 + 7 + 8 + 5, places=3)

    def test_consolidated_and_split_totals_are_identical(self):
        a = self._data(company_mode="consolidated")["totals"]
        b = self._data(company_mode="split")["totals"]
        self.assertAlmostEqual(a["closing_qty"], b["closing_qty"], places=3)
        self.assertAlmostEqual(a["closing_value"], b["closing_value"], places=2)

    # ----------------------------------------------------------- actions
    def test_drill_down_rebuilds_domain_and_carries_views(self):
        data = self._data(unfold_level=7)
        row = self._product_row(data, self.product_w, self.wh_a)
        action = self.report.action_drill_down(row["id"], self._options(unfold_level=7))
        self.assertEqual(action["res_model"], "stock.move.line")
        self.assertIn("views", action)
        lines = self.env["stock.move.line"].search(action["domain"])
        self.assertEqual(set(lines.mapped("product_id").ids), {self.product_w.id})
        self.assertEqual(len(lines), 5)

    def test_open_product_falls_back_to_moves_or_stock_card(self):
        data = self._data(unfold_level=7)
        row = self._product_row(data, self.product_w, self.wh_a)
        action = self.report.action_open_product(row["id"], self._options())
        if data["checks"]["has_stock_card"]:
            self.assertEqual(action["tag"], "biz_st_stock_card.product_card")
            self.assertEqual(action["context"]["sc_product_id"], self.product_w.id)
            self.assertNotIn("cost_basis", action["context"]["sc_options"])
        else:
            self.assertEqual(action["res_model"], "stock.move.line")

    def test_open_config_targets_main_company_row(self):
        action = self.report.action_open_config(self._options())
        self.assertEqual(action["res_model"], "biz.stock.aging.config")
        self.assertEqual(action["res_id"], self.config.id)
        self.assertEqual(action["views"], [(False, "form")])

    # ------------------------------------------------------------ config
    def test_config_is_created_once_and_validated(self):
        other = self.env["res.company"].create({"name": "AG Config Co"})
        first = self.env["biz.stock.aging.config"].get_for_company(other.id)
        second = self.env["biz.stock.aging.config"].get_for_company(other.id)
        self.assertEqual(first, second)
        self.assertEqual(first.edges(), [30, 60, 90, 180, 365])
        with self.assertRaises(ValidationError):
            first.write({"bucket_2": 20})
        with self.assertRaises(ValidationError):
            first.write({"obsolete_days": 60})
        with self.assertRaises(ValidationError):
            first.write({"usage_months": 0})

    # ------------------------------------------------------------ export
    def test_xlsx_has_three_sheets_and_formula_totals(self):
        content = self.env["biz.stock.aging.xlsx"].generate(self._options(unfold_level=7))
        sheets = read_xlsx(content)
        self.assertEqual(list(sheets), ["อายุสินค้าคงเหลือ", "สรุปตามช่วงอายุ", "ข้อสังเกต"])
        main = sheets["อายุสินค้าคงเหลือ"]
        formulas = [cell for row in main for cell in row if isinstance(cell, str) and cell.startswith("=")]
        self.assertTrue(formulas)
        self.assertTrue(all(f.startswith("=SUMPRODUCT(") for f in formulas))
        data = self._data(unfold_level=7)
        columns = data["columns"]
        additive = sum(1 for c in columns if c["additive"])
        self.assertEqual(len(formulas), additive)
        total_row = next(r for r in main if len(r) > 1 and r[1] == data["totals"]["name"])
        avg_index = next(i for i, c in enumerate(columns) if c["key"] == "avg_age")
        self.assertNotIsInstance(total_row[avg_index], str)
        notes = "\n".join(str(c) for row in sheets["ข้อสังเกต"] for c in row if c)
        self.assertIn("กระทบยอดได้", notes)

    def test_pdf_html_embeds_the_thai_font_without_escaped_quotes(self):
        wizard = self.env["biz.stock.aging.wizard"]._create_from_options(self._options())
        report = self.env.ref("biz_st_aging.action_report_stock_aging")
        html = report._render_qweb_html(report.report_name, wizard.ids, data={
            "options": wizard._get_options(),
        })[0].decode("utf-8")
        self.assertIn("font-family:Sarabun", html)
        self.assertIn("data:font/truetype;base64,", html)
        self.assertNotIn("&#39;", html.split("</style>")[0])
        self.assertIn("อายุสินค้าคงเหลือ", html)
        self.assertIn("ตาย", html)  # สถานะของสินค้า B ถูกพิมพ์

    def test_all_three_outputs_agree_on_totals(self):
        options = self._options(unfold_level=7)
        data = self.report.get_report_data(options)
        sheets = read_xlsx(self.env["biz.stock.aging.xlsx"].generate(options))
        main = sheets["อายุสินค้าคงเหลือ"]
        total_row = next(r for r in main if len(r) > 1 and r[1] == data["totals"]["name"])
        qty_index = next(i for i, c in enumerate(data["columns"]) if c["key"] == "closing_qty")
        self.assertTrue(str(total_row[qty_index]).startswith("=SUMPRODUCT("))
        # แถวระดับบนสุดในชีต = counts_to_total ของเครื่องยนต์
        top_names = [l["name"] for l in data["lines"] if l.get("counts_to_total")]
        sheet_names = [r[1] for r in main if r and len(r) > 1 and r[1] in top_names]
        self.assertEqual(sorted(sheet_names), sorted(top_names))
        pdf_values = self.env["report.biz_st_aging.report_stock_aging_doc"]._get_report_values(
            [], data={"options": options}
        )
        self.assertAlmostEqual(pdf_values["d"]["totals"]["closing_qty"], data["totals"]["closing_qty"], places=3)
        self.assertAlmostEqual(pdf_values["d"]["totals"]["closing_value"], data["totals"]["closing_value"], places=2)

    def test_wizard_round_trip_keeps_filters(self):
        options = self._options(group_lot=True, warehouse_ids=[self.wh_a.id], unfold_level=3)
        wizard = self.env["biz.stock.aging.wizard"]._create_from_options(options)
        back = wizard._get_options()
        self.assertEqual(back["date_to"], "2025-06-30")
        self.assertTrue(back["group_lot"])
        self.assertEqual(back["warehouse_ids"], [self.wh_a.id])
        self.assertEqual(back["unfold_level"], 3)
        action = wizard.action_view_report()
        self.assertEqual(action["context"]["ag_options"]["date_to"], "2025-06-30")
        export = self.env["biz.stock.aging.wizard"].action_export_from_options(options, "xlsx")
        self.assertEqual(export["type"], "ir.actions.act_url")
        self.assertIn("download=true", export["url"])

    # ----------------------------------------------------------- max_lines
    def test_max_lines_refuses_oversized_trees_but_not_folded_ones(self):
        from odoo.exceptions import UserError
        options = self._options(unfold_level=7, group_location=True, group_lot=True, max_lines=10)
        self.assertEqual(self.report._normalize_options(options)["max_lines"], 10)
        with self.assertRaises(UserError):
            self.report.get_report_data(options)
        folded = self.report.get_report_data(dict(options, unfold_level=0))
        self.assertLessEqual(len(folded["lines"]), 10)
        # Excel ตั้งเพดานของตัวเอง จึงยังออกไฟล์ได้จาก options เดียวกัน
        self.assertTrue(self.env["biz.stock.aging.xlsx"].generate(options))

    # --------------------------------------------------------------- cache
    def test_node_cache_hits_on_render_only_changes_and_expires_on_new_data(self):
        """กาง/หุบแถว ใช้แคชระดับโหนด; รายการใหม่ทำให้ลายนิ้วมือเปลี่ยนและคำนวณใหม่เอง"""
        from ..models.stock_aging_report import NODES_CACHE
        NODES_CACHE.clear()
        first = self._data(unfold_level=0)
        self.assertFalse(first["checks"]["from_cache"])
        # เปลี่ยนเฉพาะคีย์ที่กระทบการแสดงผล → ไม่แตะ DB แต่ทรีต้องต่างกันจริง
        unfolded = self._data(unfold_level=7, date_format="ce")
        self.assertTrue(unfolded["checks"]["from_cache"])
        self.assertGreater(len(unfolded["lines"]), len(first["lines"]))
        self.assertEqual(unfolded["totals"]["closing_qty"], first["totals"]["closing_qty"])
        self.assertEqual(unfolded["totals"]["closing_value"], first["totals"]["closing_value"])
        # เปลี่ยนคีย์ที่กระทบตัวเลข → คำนวณใหม่
        by_lot = self._data(group_lot=True)
        self.assertFalse(by_lot["checks"]["from_cache"])
        # ปุ่ม "ปรับปรุงข้อมูล" ข้ามแคชแม้ options เดิม และ nocache ไม่ถูก echo กลับ
        fresh = self.report.get_report_data(dict(self._options(), nocache=True))
        self.assertFalse(fresh["checks"]["from_cache"])
        self.assertNotIn("nocache", fresh["options"])
        self.assertTrue(self._data()["checks"]["from_cache"])
        # รายการใหม่ (แม้ย้อนวันที่) → ลายนิ้วมือเปลี่ยน → ตัวเลขใหม่โดยไม่ต้องกด refresh
        self._do(self.product_b, 7, self.supplier, self.stock_a, days_ago(5), price=5.0)
        after = self._data()
        self.assertFalse(after["checks"]["from_cache"])
        self.assertAlmostEqual(
            after["totals"]["closing_qty"], first["totals"]["closing_qty"] + 7, places=3
        )
        # แก้บรรทัดเดิมโดยไม่เพิ่มแถว → write_date เปลี่ยน → คำนวณใหม่เช่นกัน
        # (ในเทส ทุก write อยู่ทรานแซกชันเดียว ได้ write_date = cr.now() ค่าเดียวกันหมด จึงต้อง
        # ขยับด้วย SQL ตรง ๆ; บน prod แต่ละ request เป็นคนละทรานแซกชันอยู่แล้ว)
        self.assertTrue(self._data()["checks"]["from_cache"])
        line = self.env["stock.move.line"].search(
            [("product_id", "=", self.product_b.id), ("state", "=", "done")], limit=1,
            order="id desc",
        )
        self.env.cr.execute(
            "UPDATE stock_move_line SET write_date = write_date + interval '1 second' WHERE id = %s",
            (line.id,),
        )
        line.invalidate_recordset(["write_date"])
        self.assertFalse(self._data()["checks"]["from_cache"])
