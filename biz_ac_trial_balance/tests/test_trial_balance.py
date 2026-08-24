# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestTrialBalance(TransactionCase):
    """เทสยึดวันที่จาก "ปีบัญชีของบริษัท" ไม่ใช่วันนี้ เพื่อไม่ให้ผลลัพธ์เปลี่ยนตามวันที่รัน"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.report = cls.env["biz.trial.balance.report"]

        fy = cls.company.compute_fiscalyear_dates(fields.Date.today())
        cls.fy_from = fy["date_from"]
        cls.date_from = cls.fy_from + relativedelta(months=3)
        cls.date_to = cls.date_from + relativedelta(months=1, days=-1)
        cls.date_prior_year = cls.fy_from - relativedelta(days=1)
        cls.date_in_fy_before = cls.fy_from + relativedelta(days=1)
        cls.date_in_period = cls.date_from + relativedelta(days=5)

        cls.journal = cls.env["account.journal"].create({
            "name": "TB Test Journal",
            "code": "TBTST",
            "type": "general",
            "company_id": cls.company.id,
        })

        cls.cash = cls._account("TB1001", "เงินสด", "asset_current")
        cls.bank = cls._account("TB1002", "ธนาคาร", "asset_current")
        cls.payable = cls._account("TB2000", "เจ้าหนี้การค้า", "liability_current")
        cls.equity = cls._account("TB3000", "ทุนจดทะเบียน", "equity")
        cls.income = cls._account("TB4000", "รายได้จากการขาย", "income")
        cls.expense = cls._account("TB5000", "ค่าใช้จ่ายในการขาย", "expense")

        # ปีก่อน: เงินสด 1,000 / ทุน 1,000  และ ธนาคาร 200 / รายได้ 200
        cls._move(cls.date_prior_year, [(cls.cash, 1000, 0), (cls.equity, 0, 1000)])
        cls._move(cls.date_prior_year, [(cls.bank, 200, 0), (cls.income, 0, 200)])
        # ปีนี้ก่อนงวด: ธนาคาร 500 / รายได้ 500
        cls._move(cls.date_in_fy_before, [(cls.bank, 500, 0), (cls.income, 0, 500)])
        # ในงวด: ค่าใช้จ่าย 300 / เงินสด 300
        cls._move(cls.date_in_period, [(cls.expense, 300, 0), (cls.cash, 0, 300)])
        # ในงวดแต่ยังไม่ผ่านรายการ
        cls.draft_move = cls._move(
            cls.date_in_period, [(cls.expense, 77, 0), (cls.payable, 0, 77)], post=False
        )

    @classmethod
    def _account(cls, code, name, account_type):
        return cls.env["account.account"].create({
            "code": code,
            "name": name,
            "account_type": account_type,
            "company_id": cls.company.id,
        })

    @classmethod
    def _move(cls, date, lines, post=True):
        move = cls.env["account.move"].create({
            "move_type": "entry",
            "date": date,
            "journal_id": cls.journal.id,
            "company_id": cls.company.id,
            "line_ids": [
                (0, 0, {"account_id": account.id, "debit": debit, "credit": credit})
                for account, debit, credit in lines
            ],
        })
        if post:
            move.action_post()
        return move

    # ------------------------------------------------------------------
    def _run(self, **overrides):
        options = {
            "company_id": self.company.id,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "journal_ids": [self.journal.id],
            "display_account": "all",
        }
        options.update(overrides)
        return self.report.get_report_data(options)

    def _line(self, data, account):
        for line in data["lines"]:
            if line.get("account_id") == account.id:
                return line
        return None

    # ------------------------------------------------------------------
    def test_totals_are_balanced(self):
        for kwargs in (
            {},
            {"group_by_type": False},
            {"opening_basis": "inception"},
            {"target_move": "all"},
            {"closing_mode": "after"},
            {"compare": "previous_year"},
        ):
            data = self._run(**kwargs)
            self.assertAlmostEqual(
                data["totals"]["closing_debit"],
                data["totals"]["closing_credit"],
                places=2,
                msg="งบทดลองต้องดุลเสมอ (options=%s)" % kwargs,
            )
            self.assertTrue(data["checks"]["is_balanced"])

    def test_closing_equals_opening_plus_period(self):
        data = self._run()
        for line in data["lines"]:
            if line["kind"] != "account":
                continue
            opening = line["opening_debit"] - line["opening_credit"]
            period = line["period_debit"] - line["period_credit"]
            closing = line["closing_debit"] - line["closing_credit"]
            self.assertAlmostEqual(closing, opening + period, places=2, msg=line["code"])

    def test_amounts_are_never_negative(self):
        """งบทดลองไทยลงยอดข้างเดียว ไม่มีเลขติดลบในคอลัมน์ใดเลย"""
        keys = (
            "opening_debit", "opening_credit", "period_debit",
            "period_credit", "closing_debit", "closing_credit",
        )
        data = self._run(compare="previous_period")
        for line in data["lines"]:
            for key in keys:
                self.assertGreaterEqual(line.get(key, 0.0), 0.0, "%s.%s" % (line["code"], key))

    def test_opening_basis_fiscalyear_resets_pl_accounts(self):
        fiscal = self._line(self._run(opening_basis="fiscalyear"), self.income)
        inception = self._line(self._run(opening_basis="inception"), self.income)
        # ต้นปีบัญชี: เห็นเฉพาะ 500 ของปีนี้ / ทุกรายการ: เห็น 700 รวมของปีก่อนด้วย
        self.assertAlmostEqual(fiscal["opening_credit"], 500.0, places=2)
        self.assertAlmostEqual(inception["opening_credit"], 700.0, places=2)

    def test_opening_basis_does_not_reset_balance_sheet_accounts(self):
        fiscal = self._line(self._run(opening_basis="fiscalyear"), self.cash)
        inception = self._line(self._run(opening_basis="inception"), self.cash)
        self.assertAlmostEqual(fiscal["opening_debit"], 1000.0, places=2)
        self.assertAlmostEqual(inception["opening_debit"], 1000.0, places=2)

    def test_cash_movement_and_closing(self):
        line = self._line(self._run(), self.cash)
        self.assertAlmostEqual(line["opening_debit"], 1000.0, places=2)
        self.assertAlmostEqual(line["period_credit"], 300.0, places=2)
        self.assertAlmostEqual(line["closing_debit"], 700.0, places=2)

    def test_every_account_is_its_own_flat_row(self):
        """ไม่มีบัญชีคลุม/บัญชีย่อยแล้ว — ทุกบัญชีเป็นแถวเดี่ยวถือยอดของตัวเอง"""
        data = self._run()
        cash = self._line(data, self.cash)
        bank = self._line(data, self.bank)
        self.assertAlmostEqual(cash["closing_debit"], 700.0, places=2)
        self.assertAlmostEqual(bank["closing_debit"], 700.0, places=2)
        for line in data["lines"]:
            self.assertNotIn("has_children", line)
            self.assertNotIn("is_parent_account", line)

    def test_target_move_posted_excludes_draft(self):
        posted = self._line(self._run(target_move="posted"), self.expense)
        every = self._line(self._run(target_move="all"), self.expense)
        self.assertAlmostEqual(posted["period_debit"], 300.0, places=2)
        self.assertAlmostEqual(every["period_debit"], 377.0, places=2)
        self.assertTrue(self._run(target_move="all")["checks"]["include_draft"])

    def test_closing_mode_after_zeroes_pl_accounts(self):
        data = self._run(closing_mode="after")
        for account in (self.income, self.expense):
            line = self._line(data, account)
            self.assertAlmostEqual(line["closing_debit"], 0.0, places=2)
            self.assertAlmostEqual(line["closing_credit"], 0.0, places=2)
        virtual = [line for line in data["lines"] if line.get("virtual")]
        self.assertEqual(len(virtual), 1, "ต้องมีบรรทัดกำไร(ขาดทุน)สุทธิยกไปกำไรสะสม 1 บรรทัด")
        # รายได้ 500 (ในงวด 0) − ค่าใช้จ่าย 300 = กำไร 200 เข้าฝั่งเครดิตของทุน
        self.assertAlmostEqual(virtual[0]["closing_credit"], 200.0, places=2)

    def test_abnormal_balance_is_flagged(self):
        """สินทรัพย์ที่มียอดคงเหลือฝั่งเครดิตต้องถูกติดธง"""
        self._move(self.date_in_period, [(self.bank, 0, 5000), (self.payable, 5000, 0)])
        line = self._line(self._run(), self.bank)
        self.assertGreater(line["closing_credit"], 0.0)
        self.assertEqual(line["flag"], "abnormal")

    def test_grand_total_counts_each_account_once(self):
        """แถวรวมหมวดต้องไม่ถูกนับซ้ำเข้ายอดรวมทั้งสิ้น"""
        data = self._run()
        marked = sum(
            line["closing_debit"] for line in data["lines"] if line.get("counts_to_total")
        )
        self.assertAlmostEqual(marked, data["totals"]["closing_debit"], places=2)

    def test_change_pct_matches_opening_to_closing(self):
        line = self._line(self._run(), self.cash)
        # 1,000 → 700 คือ −30%
        self.assertAlmostEqual(line["change_pct"], -30.0, places=1)

    def test_buddhist_era_dates(self):
        self.assertEqual(
            self.report.format_report_date("2026-02-28", "be"), "28/02/2569"
        )
        self.assertEqual(
            self.report.format_report_date("2026-02-28", "ce"), "28/02/2026"
        )

    # ------------------------------------------------------------------
    def test_xlsx_export_produces_workbook(self):
        wizard = self.env["biz.trial.balance.wizard"].create({
            "date_from": self.date_from,
            "date_to": self.date_to,
            "journal_ids": [(6, 0, [self.journal.id])],
            "display_account": "all",
        })
        wizard.action_export_xlsx()
        self.assertTrue(wizard.xlsx_file)
        self.assertTrue(wizard.xlsx_filename.endswith(".xlsx"))

    def test_pdf_html_renders_with_thai_font(self):
        wizard = self.env["biz.trial.balance.wizard"].create({
            "date_from": self.date_from,
            "date_to": self.date_to,
            "journal_ids": [(6, 0, [self.journal.id])],
            "display_account": "all",
        })
        html = self.env["ir.actions.report"]._render_qweb_html(
            "biz_ac_trial_balance.report_trial_balance_doc",
            wizard.ids,
            data={"options": wizard._get_options()},
        )[0].decode()
        self.assertIn("งบทดลอง", html)
        self.assertIn("font-family:Sarabun", html.replace(" ", ""))
        self.assertIn("data:font/truetype;base64,", html)
        self.assertIn("รวมทั้งสิ้น", html)

    def test_xlsx_has_expected_sheets_and_no_outline_grouping(self):
        """Excel มีสองชีต และไม่มีการจัดกลุ่มแถวแบบ outline อีกแล้ว"""
        import xml.etree.ElementTree as ElementTree
        import zipfile
        from io import BytesIO

        options = self.report._normalize_options({
            "company_id": self.company.id,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "journal_ids": [self.journal.id],
            "display_account": "all",
        })
        book = zipfile.ZipFile(BytesIO(self.env["biz.trial.balance.xlsx"].generate(options)))
        self.assertEqual(
            [s.get("name") for s in ElementTree.fromstring(book.read("xl/workbook.xml")).iter(
                "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheet"
            )],
            ["งบทดลอง", "สรุปตามหมวด"],
        )
        sheet = ElementTree.fromstring(book.read("xl/worksheets/sheet1.xml"))
        levels = {
            row.get("outlineLevel")
            for row in sheet.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row")
        }
        self.assertEqual(levels, {None}, "ไม่ควรเหลือแถว outline หลังเอาบัญชีย่อยออก")

    def test_total_rows_are_column_sums_not_net(self):
        """แถวรวมต้องเป็นผลรวมของคอลัมน์ เพื่อให้ยอดหมวดย่อยบวกแล้วตรงกับแถวรวม"""
        data = self._run()
        totals = data["totals"]
        for prefix in ("opening", "period", "closing"):
            self.assertAlmostEqual(
                totals[prefix + "_debit"], totals[prefix + "_credit"], places=2,
                msg="คอลัมน์ %s ต้องดุลทั้งสองข้าง" % prefix,
            )
        self.assertGreater(totals["opening_debit"], 0.0,
                           "ยอดยกมารวมต้องไม่ถูกยุบเป็นศูนย์")
        for key in ("opening_debit", "opening_credit", "closing_debit", "closing_credit"):
            section_sum = sum(
                line[key] for line in data["lines"] if line["kind"] == "section_total"
            )
            self.assertAlmostEqual(section_sum, totals[key], places=2, msg=key)

    def test_change_pct_is_undefined_when_no_opening_balance(self):
        """ยอดยกมาเป็นศูนย์แล้วมียอดคงเหลือ = คิด % ไม่ได้ ต้องคืน None ไม่ใช่ 100"""
        data = self._run()
        expense = self._line(data, self.expense)
        self.assertAlmostEqual(expense["opening_debit"], 0.0, places=2)
        self.assertGreater(expense["closing_debit"], 0.0)
        self.assertIsNone(expense["change_pct"])
        # บัญชีที่ว่างทั้งสองฝั่งยังคงเป็น 0.0 ไม่ใช่ None
        self.assertEqual(self._line(data, self.payable)["change_pct"], 0.0)


@tagged("post_install", "-at_install")
class TestTrialBalanceMultiCompany(TransactionCase):
    """งบทดลองข้ามบริษัท — รวมเป็นงบเดียว หรือแยกแถวตามบริษัท"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.report = cls.env["biz.trial.balance.report"]
        cls.company_a = cls.env.company
        cls.company_b = cls.env["res.company"].create({"name": "TB Multi Co B"})
        # ผู้ใช้ต้องมีสิทธิ์บริษัท B ไม่งั้นสร้างรายการ/อ่านรายงานไม่ได้
        cls.env.user.company_ids = [(4, cls.company_b.id)]

        fy = cls.company_a.compute_fiscalyear_dates(fields.Date.today())
        cls.date_from = fy["date_from"] + relativedelta(months=3)
        cls.date_to = cls.date_from + relativedelta(months=1, days=-1)
        cls.date_in_period = cls.date_from + relativedelta(days=5)

        cls.journal_a = cls._journal(cls.company_a, "TBMA")
        cls.journal_b = cls._journal(cls.company_b, "TBMB")

        # บัญชี "รหัสเดียวกัน" คนละบริษัท — คือกรณีที่โหมดรวมต้องยุบให้เป็นแถวเดียว
        cls.cash_a = cls._account(cls.company_a, "TBM101", "เงินสด", "asset_current")
        cls.cash_b = cls._account(cls.company_b, "TBM101", "เงินสด", "asset_current")
        cls.income_a = cls._account(cls.company_a, "TBM400", "รายได้", "income")
        cls.income_b = cls._account(cls.company_b, "TBM400", "รายได้", "income")

        cls._move(cls.company_a, cls.journal_a, [(cls.cash_a, 1000, 0), (cls.income_a, 0, 1000)])
        cls._move(cls.company_b, cls.journal_b, [(cls.cash_b, 400, 0), (cls.income_b, 0, 400)])

    @classmethod
    def _journal(cls, company, code):
        return cls.env["account.journal"].create({
            "name": "TB Multi %s" % code,
            "code": code,
            "type": "general",
            "company_id": company.id,
        })

    @classmethod
    def _account(cls, company, code, name, account_type):
        return cls.env["account.account"].with_company(company).create({
            "code": code,
            "name": name,
            "account_type": account_type,
            "company_id": company.id,
        })

    @classmethod
    def _move(cls, company, journal, lines):
        move = cls.env["account.move"].with_company(company).create({
            "move_type": "entry",
            "date": cls.date_in_period,
            "journal_id": journal.id,
            "company_id": company.id,
            "line_ids": [
                (0, 0, {"account_id": account.id, "debit": debit, "credit": credit})
                for account, debit, credit in lines
            ],
        })
        move.action_post()
        return move

    def _run(self, **overrides):
        options = {
            "company_ids": [self.company_a.id, self.company_b.id],
            "date_from": self.date_from,
            "date_to": self.date_to,
            "journal_ids": [self.journal_a.id, self.journal_b.id],
            "display_account": "all",
        }
        options.update(overrides)
        return self.report.get_report_data(options)

    def _rows(self, data, code):
        return [
            line for line in data["lines"]
            if line["kind"] == "account" and line["code"] == code
        ]

    # ------------------------------------------------------------------
    def test_consolidated_merges_same_code_across_companies(self):
        data = self._run(company_mode="consolidated")
        rows = self._rows(data, "TBM101")
        self.assertEqual(len(rows), 1, "บัญชีรหัสเดียวกันต้องยุบเป็นแถวเดียว")
        self.assertAlmostEqual(rows[0]["closing_debit"], 1400.0, places=2)
        self.assertEqual(
            sorted(rows[0]["account_ids"]), sorted([self.cash_a.id, self.cash_b.id]),
            "แถวงบรวมต้องจำ id ของทุกบัญชีไว้ให้ drill-down ตามได้",
        )

    def test_split_keeps_one_row_per_company(self):
        data = self._run(company_mode="split")
        rows = self._rows(data, "TBM101")
        self.assertEqual(len(rows), 2)
        by_company = {row["company_name"]: row["closing_debit"] for row in rows}
        self.assertAlmostEqual(by_company[self.company_a.name], 1000.0, places=2)
        self.assertAlmostEqual(by_company[self.company_b.name], 400.0, places=2)

    def test_totals_identical_in_both_modes(self):
        """รวมหรือแยกก็เป็นข้อมูลชุดเดียวกัน ยอดรวมทั้งสิ้นต้องตรงกันเป๊ะ"""
        merged = self._run(company_mode="consolidated")["totals"]
        split = self._run(company_mode="split")["totals"]
        for key in ("opening_debit", "opening_credit", "period_debit",
                    "period_credit", "closing_debit", "closing_credit"):
            self.assertAlmostEqual(merged[key], split[key], places=2, msg=key)

    def test_totals_are_balanced_across_companies(self):
        for mode in ("consolidated", "split"):
            data = self._run(company_mode=mode)
            self.assertAlmostEqual(
                data["totals"]["closing_debit"],
                data["totals"]["closing_credit"],
                places=2, msg=mode,
            )
            self.assertTrue(data["checks"]["is_balanced"], mode)

    def test_single_company_still_works_via_legacy_company_id(self):
        """options เก่าที่ส่ง company_id เดี่ยวมาต้องยังใช้ได้เหมือนเดิม"""
        data = self.report.get_report_data({
            "company_id": self.company_b.id,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "journal_ids": [self.journal_b.id],
            "display_account": "all",
        })
        self.assertEqual(data["options"]["company_ids"], [self.company_b.id])
        self.assertEqual(len(self._rows(data, "TBM101")), 1)
        self.assertAlmostEqual(
            self._rows(data, "TBM101")[0]["closing_debit"], 400.0, places=2
        )

    def test_company_defaults_to_allowed_companies(self):
        options = self.report._normalize_options({})
        self.assertEqual(options["company_ids"], self.env.companies.ids)
        self.assertEqual(options["company_mode"], "consolidated")

    def test_payload_lists_companies_the_user_may_pick(self):
        """ช่องเลือกบริษัทบนแถบตัวกรองกินรายชื่อจาก payload นี้ ต้องตรงกับสิทธิ์จริง"""
        data = self._run()
        allowed = data["allowed_companies"]
        self.assertEqual(
            [c["id"] for c in allowed], self.env.user.company_ids.ids,
            "ต้องเสนอเฉพาะบริษัทที่ผู้ใช้เข้าถึงได้ ไม่ใช่ทุกบริษัทในระบบ",
        )
        self.assertIn(self.company_b.id, [c["id"] for c in allowed])
        self.assertTrue(all(c["name"] for c in allowed))

    def test_company_outside_user_access_is_refused(self):
        outsider = self.env["res.company"].create({"name": "TB Outsider Co"})
        # res.company.create() ผูกบริษัทใหม่เข้ากับผู้สร้างให้อัตโนมัติ ต้องถอดออกก่อน
        # ถึงจะจำลอง "บริษัทที่ผู้ใช้ไม่มีสิทธิ์" ได้จริง
        self.env.user.company_ids = [(3, outsider.id)]
        self.assertNotIn(outsider, self.env.user.company_ids)
        with self.assertRaises(AccessError):
            self.report.get_report_data({
                "company_ids": [outsider.id],
                "date_from": self.date_from,
                "date_to": self.date_to,
            })

    def test_drill_down_covers_every_company_in_the_row(self):
        data = self._run(company_mode="consolidated")
        row = self._rows(data, "TBM101")[0]
        action = self.report.action_open_journal_items(
            row["account_ids"], data["options"]
        )
        self.assertEqual(action["res_model"], "account.move.line")
        self.assertIn(("account_id", "in", row["account_ids"]), action["domain"])
        self.assertTrue(action["views"], "action ต้องมี views ติดมาเสมอ (doAction ฝั่ง OWL)")
        lines = self.env["account.move.line"].search(action["domain"])
        self.assertEqual(
            set(lines.mapped("company_id").ids),
            {self.company_a.id, self.company_b.id},
        )

    def test_split_mode_exports_without_error(self):
        wizard = self.env["biz.trial.balance.wizard"].create({
            "company_ids": [(6, 0, [self.company_a.id, self.company_b.id])],
            "company_mode": "split",
            "date_from": self.date_from,
            "date_to": self.date_to,
            "journal_ids": [(6, 0, [self.journal_a.id, self.journal_b.id])],
            "display_account": "all",
        })
        self.assertTrue(wizard.is_multi_company)
        wizard.action_export_xlsx()
        self.assertTrue(wizard.xlsx_file)
        html = self.env["ir.actions.report"]._render_qweb_html(
            "biz_ac_trial_balance.report_trial_balance_doc",
            wizard.ids,
            data={"options": wizard._get_options()},
        )[0].decode()
        self.assertIn(self.company_b.name, html, "หัวรายงานต้องมีชื่อบริษัทครบทุกตัว")
