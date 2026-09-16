# -*- coding: utf-8 -*-
"""Trial Balance ภายนอกรายเดือน + ทะเบียนงวด (Monthly Close Cockpit)

DB dev ใช้ร่วมกับข้อมูลจริง — ทุก assert ตัวเลขทำบน**บริษัทที่สร้างใหม่**
(ยอดตั้งต้นเป็นศูนย์) ตามกติกาเดียวกับ test_bsf_ext.py"""
import json

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestBsfExtAccountGl(TransactionCase):
    """โมเดลชั้นต้น: ผังบัญชีภายนอก + TB หนึ่งงวด — ไม่แตะ engine"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env["res.company"].create({"name": "BSF TB Co"})
        cls.ExtAccount = cls.env["biz.smart.finance.ext.account"]
        cls.ExtGl = cls.env["biz.smart.finance.ext.gl"]
        cls.acc_rev = cls.ExtAccount.create({
            "company_id": cls.company.id, "code": "E4000",
            "name": "Sales (ext)", "account_type": "income",
        })
        cls.acc_cash = cls.ExtAccount.create({
            "company_id": cls.company.id, "code": "E1000",
            "name": "Cash (ext)", "account_type": "asset_cash",
        })

    def test_flag_constrains_account_type(self):
        with self.assertRaises(ValidationError):
            self.ExtAccount.create({
                "company_id": self.company.id, "code": "E9000",
                "name": "bad debt flag", "account_type": "income",
                "is_debt": True,
            })

    def test_resolve_creates_or_reuses(self):
        found = self.ExtAccount.resolve(
            self.company, "E4000", "ignored", "expense")
        self.assertEqual(found.id, self.acc_rev.id, "รหัสเดิมต้องไม่สร้างซ้ำ")
        with self.assertRaises(ValidationError):
            self.ExtAccount.resolve(self.company, "E5000", "New", None)
        created = self.ExtAccount.resolve(
            self.company, "E5000", "COGS (ext)", "expense_direct_cost")
        self.assertEqual(created.code, "E5000")

    def test_balance_closing_and_post_gate(self):
        gl = self.ExtGl.upsert_tb(
            self.company, "2026-01-01", "2026-01-31",
            [
                {"code": "E1000", "opening": 0.0, "debit": 500.0, "credit": 0.0},
                {"code": "E4000", "opening": 0.0, "debit": 0.0, "credit": 500.0},
            ],
            source="manual",
        )
        self.assertEqual(gl.state, "draft")
        self.assertEqual(gl.diff, 0.0)
        cash_line = gl.line_ids.filtered(
            lambda l: l.ext_account_id.code == "E1000")
        self.assertEqual(cash_line.balance, 500.0)
        self.assertEqual(cash_line.closing, 500.0)
        gl.action_post()
        self.assertEqual(gl.state, "posted")

    def test_unbalanced_tb_cannot_post(self):
        gl = self.ExtGl.upsert_tb(
            self.company, "2026-02-01", "2026-02-28",
            [{"code": "E1000", "opening": 500.0, "debit": 100.0, "credit": 0.0}],
            source="manual",
        )
        self.assertEqual(gl.diff, 100.0)
        with self.assertRaises(ValidationError):
            gl.action_post()

    def test_upsert_replace_removes_old_header(self):
        self.ExtGl.upsert_tb(
            self.company, "2026-03-01", "2026-03-31",
            [{"code": "E1000", "opening": 0.0, "debit": 10.0, "credit": 0.0},
             {"code": "E4000", "opening": 0.0, "debit": 0.0, "credit": 10.0}],
            source="manual",
        )
        gl2 = self.ExtGl.upsert_tb(
            self.company, "2026-03-01", "2026-03-31",
            [{"code": "E1000", "opening": 0.0, "debit": 20.0, "credit": 0.0},
             {"code": "E4000", "opening": 0.0, "debit": 0.0, "credit": 20.0}],
            source="import",
        )
        headers = self.ExtGl.search([
            ("company_id", "=", self.company.id),
            ("date_from", "=", "2026-03-01"),
        ])
        self.assertEqual(len(headers), 1, "replace=True ต้องแทนที่ ไม่ใช่เพิ่มซ้ำ")
        self.assertEqual(headers.id, gl2.id)
        self.assertEqual(headers.dr_total, 20.0)


class TestBsfPeriod(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env["res.company"].create({"name": "BSF Period Co"})
        cls.Period = cls.env["biz.smart.finance.period"]

    def test_generate_year_matches_engine_periods(self):
        created = self.Period.action_generate_year(self.company.id, 2026)
        self.assertEqual(created, 12)
        periods = self.Period.search([("company_id", "=", self.company.id)])
        self.assertEqual(len(periods), 12)
        jan = periods.filtered(lambda p: p.period_index == 1)
        self.assertEqual(jan.date_from, fields.Date.from_string("2026-01-01"))
        self.assertEqual(jan.date_to, fields.Date.from_string("2026-01-31"))
        # เรียกซ้ำต้องไม่สร้างซ้ำ (ข้ามงวดที่มีอยู่แล้ว)
        again = self.Period.action_generate_year(self.company.id, 2026)
        self.assertEqual(again, 0)

    def test_close_blocked_when_tb_unbalanced(self):
        self.Period.action_generate_year(self.company.id, 2026)
        jan = self.Period.search([
            ("company_id", "=", self.company.id), ("period_index", "=", 1),
        ])
        self.env["biz.smart.finance.ext.gl"].upsert_tb(
            self.company, jan.date_from, jan.date_to,
            [{"code": "E1000", "name": "Cash", "account_type": "asset_cash",
              "opening": 0.0, "debit": 100.0, "credit": 0.0}],
            source="manual", period_id=jan.id,
        )
        with self.assertRaises(ValidationError):
            jan.action_close()

    def test_source_wizard_bulk_apply(self):
        self.Period.action_generate_year(self.company.id, 2026)
        periods = self.Period.search([
            ("company_id", "=", self.company.id), ("period_index", "in", (1, 2)),
        ])
        wizard = self.env["biz.smart.finance.period.source.wizard"].create({
            "period_ids": [(6, 0, periods.ids)],
            "gl_source": "external", "invoice_source": "keep",
            "inventory_source": "keep", "ratio_source": "keep",
            "budget_source": "keep",
        })
        wizard.action_apply()
        self.assertEqual(set(periods.mapped("gl_source")), {"external"})
        # Selection ที่ไม่ถูกตั้ง อ่านกลับมาเป็น False (ไม่ใช่ "") ใน Odoo —
        # engine ใช้ `or` เทียบอยู่แล้วจึงไม่กระทบตรรกะ ทดสอบแค่ว่า "ไม่ตั้งค่า"
        self.assertTrue(all(not v for v in periods.mapped("invoice_source")))


class TestBsfDashboardExternalGl(TransactionCase):
    """engine: balances() ตัดสลับ Odoo/ภายนอกรายเดือน — จุดเสี่ยงที่สุดคือ
    ยอดสะสมข้ามจุดตัด (cutover) กับ movement ที่ต้องไม่นับซ้ำ/ตกหล่น"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env["res.company"].create({"name": "BSF Cutover Co"})
        cls.env.user.company_ids = [(4, cls.company.id)]
        cls.engine = cls.env["biz.smart.finance.dashboard"]

        cls.acc_cash = cls.env["account.account"].create({
            "code": "BCASH", "name": "Cash", "account_type": "asset_cash",
            "company_id": cls.company.id,
        })
        cls.acc_income = cls.env["account.account"].create({
            "code": "BINC", "name": "Sales", "account_type": "income",
            "company_id": cls.company.id,
        })
        cls.journal = cls.env["account.journal"].create({
            "name": "BSF Cutover Journal", "code": "BSFC", "type": "general",
            "company_id": cls.company.id,
        })
        # มีนาคม: เข้า Odoo ตามปกติ (รายได้ 1,000)
        move = cls.env["account.move"].create({
            "move_type": "entry", "journal_id": cls.journal.id,
            "company_id": cls.company.id, "date": "2026-03-15",
            "line_ids": [
                (0, 0, {"account_id": cls.acc_cash.id, "balance": 1000.0}),
                (0, 0, {"account_id": cls.acc_income.id, "balance": -1000.0}),
            ],
        })
        move.action_post()

        # ผังบัญชีภายนอก + TB มกราคม (รายได้ 500) และกุมภาพันธ์ (รายได้ 300)
        # — opening ของกุมภาพันธ์ต้องพกยอดสะสมของมกราคมมาด้วย (แบบ TB จริง)
        # รหัสบัญชีของระบบเดิมตั้งใจให้ "ต่าง" จากรหัสบัญชี Odoo ข้างบน
        # (BCASH/BINC) เพื่อไม่ให้ปนกันตอนตรวจ drillable ต่อรหัส — สถานการณ์จริง
        # ผังบัญชีสองระบบมักไม่ตรงกันอยู่แล้ว
        ExtAccount = cls.env["biz.smart.finance.ext.account"]
        ext_cash = ExtAccount.create({
            "company_id": cls.company.id, "code": "LEGCASH",
            "name": "Cash (legacy)", "account_type": "asset_cash",
        })
        ext_income = ExtAccount.create({
            "company_id": cls.company.id, "code": "LEGINC",
            "name": "Sales (legacy)", "account_type": "income",
        })
        ExtGl = cls.env["biz.smart.finance.ext.gl"]
        jan = ExtGl.upsert_tb(
            cls.company, "2026-01-01", "2026-01-31",
            [
                {"code": "LEGCASH", "opening": 0.0, "debit": 500.0, "credit": 0.0},
                {"code": "LEGINC", "opening": 0.0, "debit": 0.0, "credit": 500.0},
            ],
            source="manual",
        )
        jan.action_post()
        feb = ExtGl.upsert_tb(
            cls.company, "2026-02-01", "2026-02-28",
            [
                {"code": "LEGCASH", "opening": 500.0, "debit": 300.0, "credit": 0.0},
                {"code": "LEGINC", "opening": -500.0, "debit": 0.0, "credit": 300.0},
            ],
            source="manual",
        )
        feb.action_post()

        # ทะเบียนงวด: ม.ค.-ก.พ. = ภายนอก, มี.ค. เป็นต้นไปไม่ override (= odoo
        # ตามค่าตั้งต้นของบริษัท ไม่มี biz.smart.finance.config เลยด้วยซ้ำ)
        cls.env["biz.smart.finance.period"].create([
            {"company_id": cls.company.id, "date_from": "2026-01-01",
             "date_to": "2026-01-31", "gl_source": "external"},
            {"company_id": cls.company.id, "date_from": "2026-02-01",
             "date_to": "2026-02-28", "gl_source": "external"},
        ])

    def _payload(self, month=3):
        return self.engine.get_dashboard_data(
            {"company_id": self.company.id, "year": 2026, "month": month})

    def test_serializable(self):
        json.dumps(self._payload())

    def test_monthly_close_menu_engine_slice(self):
        """Monthly Close ย้ายเป็น client action ระดับเมนู → ใช้เครื่องยนต์บาง
        get_monthly_close_data (คืนเฉพาะสไลซ์ close) ส่วน get_dashboard_data
        ต้องไม่มีคีย์ close อีกต่อไป"""
        self.assertNotIn("close", self._payload())
        data = self.engine.get_monthly_close_data(
            {"company_id": self.company.id, "year": 2026})
        json.dumps(data)
        rows = data["close"]["rows"]
        self.assertEqual(len(rows), 12)
        by_period = {r["label"].split(" ")[0]: r for r in rows}
        # ม.ค./ก.พ. override เป็น external, มี.ค. ตกกลับค่าตั้งต้นบริษัท = odoo
        self.assertEqual(by_period["P1"]["gl_source"], "external")
        self.assertEqual(by_period["P2"]["gl_source"], "external")
        self.assertEqual(by_period["P3"]["gl_source"], "odoo")

    def test_ytd_revenue_sums_across_cutover_without_double_count(self):
        """P&L (movement): ม.ค. 500 + ก.พ. 300 (ภายนอก) + มี.ค. 1,000 (Odoo)
        = 1,800 พอดี — ถ้า trick บวก/ลบใน range_balances() พัง เลขนี้จะเพี้ยน"""
        payload = self._payload(month=3)
        self.assertEqual(payload["overview"]["kpis"]["revenue_ytd"], 1800.0)

    def test_cumulative_cash_carries_external_opening_across_cutover(self):
        """งบดุล (สะสม): เงินสด ณ 31 มี.ค. ต้องพกยอดยกมาจาก TB กุมภาพันธ์
        (800 = ยอดสะสมของภายนอกเอง ไม่ใช่แค่ movement ของกุมภาพันธ์ 300)
        บวก movement ของ Odoo เดือนมีนาคม (1,000) = 1,800"""
        payload = self._payload(month=3)
        cash_group = next(
            r for r in payload["statements"]["balance_sheet"]["rows"]
            if r["key"] == "asset_cash")
        self.assertEqual(cash_group["amount"], 1800.0)

    def test_external_only_month_reads_pure_tb_closing(self):
        """ดูถึงงวดกุมภาพันธ์เท่านั้น (as_of ยังไม่ถึงมีนาคม) — เงินสดต้อง
        มาจาก TB ล้วน ๆ (800) ไม่แตะ AML ของ Odoo เลย"""
        payload = self._payload(month=2)
        cash_group = next(
            r for r in payload["statements"]["balance_sheet"]["rows"]
            if r["key"] == "asset_cash")
        self.assertEqual(cash_group["amount"], 800.0)

    def test_external_account_rows_not_drillable(self):
        """แถวรายบัญชีของบัญชีภายนอก (id ติดลบ) ต้องมี drillable = False
        ส่วนบัญชี Odoo จริงต้อง drillable = True"""
        payload = self._payload(month=3)
        pnl_accounts = [
            row for line in payload["statements"]["pnl"]["rows"]
            for row in line["accounts"]
        ]
        by_code = {row["code"]: row for row in pnl_accounts}
        self.assertFalse(by_code["LEGINC"]["drillable"])
        self.assertTrue(by_code["BINC"]["drillable"])

    def test_fast_path_unaffected_without_period_override(self):
        """บริษัทไม่มีทะเบียนงวด/ผังบัญชีภายนอกเลย — ต้องได้ตัวเลขเท่าคิวรี AML
        ตรง ๆ (fast path เดิม) ไม่ถูกเครื่องจักรใหม่แตะเลย"""
        plain = self.env["res.company"].create({"name": "BSF Plain Co"})
        self.env.user.company_ids = [(4, plain.id)]
        acc_income = self.env["account.account"].create({
            "code": "PINC", "name": "Sales", "account_type": "income",
            "company_id": plain.id,
        })
        acc_cash = self.env["account.account"].create({
            "code": "PCASH", "name": "Cash", "account_type": "asset_cash",
            "company_id": plain.id,
        })
        journal = self.env["account.journal"].create({
            "name": "Plain Journal", "code": "PLJ", "type": "general",
            "company_id": plain.id,
        })
        move = self.env["account.move"].create({
            "move_type": "entry", "journal_id": journal.id,
            "company_id": plain.id, "date": "2026-05-10",
            "line_ids": [
                (0, 0, {"account_id": acc_cash.id, "balance": 777.0}),
                (0, 0, {"account_id": acc_income.id, "balance": -777.0}),
            ],
        })
        move.action_post()
        payload = self.engine.get_dashboard_data(
            {"company_id": plain.id, "year": 2026, "month": 12})
        self.assertEqual(payload["overview"]["kpis"]["revenue_ytd"], 777.0)


class TestBsfEbitdaExtFlags(TransactionCase):
    """ธง is_interest/is_tax บนบัญชีภายนอก ต้องไหลเข้า EBITDA/ebitda_configured
    เหมือน M2M ของ bsf.config กับบัญชี Odoo จริง"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env["res.company"].create({"name": "BSF Ebitda Co"})
        cls.env.user.company_ids = [(4, cls.company.id)]
        cls.engine = cls.env["biz.smart.finance.dashboard"]
        ExtAccount = cls.env["biz.smart.finance.ext.account"]
        ExtAccount.create({
            "company_id": cls.company.id, "code": "EINT",
            "name": "Interest expense (ext)", "account_type": "expense",
            "is_interest": True,
        })
        ExtAccount.create({
            "company_id": cls.company.id, "code": "ECASH",
            "name": "Cash (ext)", "account_type": "asset_cash",
        })
        ExtGl = cls.env["biz.smart.finance.ext.gl"]
        gl = ExtGl.upsert_tb(
            cls.company, "2026-01-01", "2026-01-31",
            [
                {"code": "EINT", "opening": 0.0, "debit": 50.0, "credit": 0.0},
                {"code": "ECASH", "opening": 0.0, "debit": 0.0, "credit": 50.0},
            ],
            source="manual",
        )
        gl.action_post()
        cls.env["biz.smart.finance.period"].create({
            "company_id": cls.company.id, "date_from": "2026-01-01",
            "date_to": "2026-01-31", "gl_source": "external",
        })

    def test_interest_flag_marks_ebitda_configured(self):
        payload = self.engine.get_dashboard_data(
            {"company_id": self.company.id, "year": 2026, "month": 1})
        self.assertTrue(payload["overview"]["kpis"]["ebitda_configured"])
