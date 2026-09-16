# -*- coding: utf-8 -*-
"""Inventory / Financial Ratios + External Figures

DB dev ใช้ร่วมกับข้อมูลจริง — ทุกการ assert ตัวเลขจึงทำบน **บริษัทที่สร้างใหม่**
(ยอดตั้งต้นเป็นศูนย์) ส่วนที่แตะ payload รวมใช้แค่ตรวจโครงสร้าง"""
import base64
import json

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestBsfExtFactModel(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env["res.company"].create({"name": "BSF Ext Co"})
        cls.Fact = cls.env["biz.smart.finance.ext.fact"]
        cls.today = fields.Date.context_today(cls.env.user)

    def test_kind_metric_constraint(self):
        with self.assertRaises(ValidationError):
            self.Fact.create({
                "company_id": self.company.id, "date": self.today,
                "kind": "inventory", "metric_key": "total_assets",
                "amount": 1.0,
            })
        with self.assertRaises(ValidationError):
            self.Fact.create({
                "company_id": self.company.id, "date": self.today,
                "kind": "ratio_input", "metric_key": "total_assets",
                "label": "หมวดหนึ่ง", "amount": 1.0,
            })

    def test_upsert_replaces_matching_keys(self):
        rows = [{"metric_key": "inventory_value", "label": "RM",
                 "amount": 100.0, "qty": 5.0}]
        self.Fact.upsert_facts(
            self.company, self.today, "inventory", rows, source="manual")
        rows[0]["amount"] = 250.0
        self.Fact.upsert_facts(
            self.company, self.today, "inventory", rows, source="import")
        facts = self.Fact.search([("company_id", "=", self.company.id)])
        self.assertEqual(len(facts), 1, "upsert ต้องแทนที่ ไม่ใช่เพิ่มซ้ำ")
        self.assertEqual(facts.amount, 250.0)
        self.assertEqual(facts.source, "import")

    def test_upsert_keeps_other_keys(self):
        self.Fact.upsert_facts(
            self.company, self.today, "ratio_input",
            [{"metric_key": "total_assets", "amount": 10.0},
             {"metric_key": "equity", "amount": 4.0}], source="manual")
        self.Fact.upsert_facts(
            self.company, self.today, "ratio_input",
            [{"metric_key": "equity", "amount": 6.0}], source="api")
        facts = self.Fact.search([("company_id", "=", self.company.id)])
        by_key = {f.metric_key: f.amount for f in facts}
        self.assertEqual(by_key, {"total_assets": 10.0, "equity": 6.0})


class TestBsfFactImport(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env["res.company"].create({"name": "BSF Import Co"})
        cls.today = fields.Date.context_today(cls.env.user)

    def _wizard(self, text):
        return self.env["biz.smart.finance.fact.import"].create({
            "company_id": self.company.id,
            "date": self.today,
            "file_name": "figures.csv",
            "file_data": base64.b64encode(text.encode("utf-8")),
        })

    def test_csv_preview_and_import(self):
        wizard = self._wizard(
            "kind,metric_key,category,amount,qty\n"
            "inventory,,Raw Material,\"1,250,000\",320\n"
            "inventory,,Finished Goods,750000,80\n"
            "ratio_input,total_assets,,99000000,\n"
        )
        wizard.action_preview()
        self.assertEqual(wizard.state, "preview")
        self.assertEqual(wizard.error_count, 0)
        self.assertEqual(wizard.valid_count, 3)
        wizard.action_import()
        facts = self.env["biz.smart.finance.ext.fact"].search(
            [("company_id", "=", self.company.id)])
        self.assertEqual(len(facts), 3)
        inventory = facts.filtered(lambda f: f.kind == "inventory")
        self.assertEqual(sum(inventory.mapped("amount")), 2000000.0)
        self.assertEqual(set(inventory.mapped("source")), {"import"})

    def test_bad_metric_blocks_import(self):
        wizard = self._wizard(
            "kind,metric_key,category,amount,qty\n"
            "ratio_input,not_a_metric,,1000,\n"
        )
        wizard.action_preview()
        self.assertEqual(wizard.error_count, 1)
        self.assertTrue(wizard.line_ids.warning)
        with self.assertRaises(UserError):
            wizard.action_import()

    def test_bad_header_raises(self):
        wizard = self._wizard("foo,bar\n1,2\n")
        with self.assertRaises(UserError):
            wizard.action_preview()


class TestBsfInventoryRatios(TransactionCase):
    """บริษัทใหม่ + move ที่สร้างเอง → assert ค่าสัมบูรณ์ได้"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env["res.company"].create({"name": "BSF Ratio Co"})
        cls.env.user.company_ids = [(4, cls.company.id)]
        cls.engine = cls.env["biz.smart.finance.dashboard"]
        cls.today = fields.Date.context_today(cls.env.user)

        def account(code, name, atype):
            return cls.env["account.account"].create({
                "code": code, "name": name, "account_type": atype,
                "company_id": cls.company.id,
            })
        cls.acc_cash = account("BSF1000", "Cash", "asset_cash")
        cls.acc_stock = account("BSF1400", "Inventory", "asset_current")
        cls.acc_ap = account("BSF2100", "Payable", "liability_payable")
        cls.acc_equity = account("BSF3000", "Equity", "equity")
        cls.acc_income = account("BSF4000", "Sales", "income")
        cls.acc_cogs = account("BSF5000", "COGS", "expense_direct_cost")

        cls.journal = cls.env["account.journal"].create({
            "name": "BSF Misc", "code": "BSFM", "type": "general",
            "company_id": cls.company.id,
        })
        # งบทดลองอย่างง่าย: เงินสด 400 + สต๊อก 600 = เจ้าหนี้ 200 + ทุน 800
        # และรายได้ 1,000 ต้นทุนขาย 600 (กำไรสุทธิ 400 อยู่ใน P&L ยังไม่ปิด)
        cls._post_move([
            (cls.acc_cash, 400.0), (cls.acc_stock, 600.0),
            (cls.acc_ap, -200.0), (cls.acc_equity, -800.0),
        ])
        cls._post_move([
            (cls.acc_cogs, 600.0), (cls.acc_income, -1000.0),
            (cls.acc_cash, 400.0), (cls.acc_equity, 0.0),
        ])

    @classmethod
    def _post_move(cls, lines):
        move = cls.env["account.move"].create({
            "move_type": "entry",
            "journal_id": cls.journal.id,
            "company_id": cls.company.id,
            "date": cls.today,
            "line_ids": [
                (0, 0, {"account_id": acc.id, "balance": balance})
                for acc, balance in lines
            ],
        })
        move.action_post()
        return move

    def _payload(self):
        return self.engine.get_dashboard_data({"company_id": self.company.id})

    def _ratio(self, payload, key):
        for group in payload["ratios"]["groups"]:
            for row in group["rows"]:
                if row["key"] == key:
                    return row
        raise AssertionError("ไม่พบอัตราส่วน %s" % key)

    def test_payload_has_new_tabs(self):
        payload = self._payload()
        self.assertIn("inventory", payload)
        self.assertIn("ratios", payload)
        json.dumps(payload)
        self.assertEqual(len(payload["ratios"]["groups"]), 4)

    def test_odoo_liquidity_ratios(self):
        """สินทรัพย์หมุนเวียน 1,400 (เงินสด 800 + สต๊อก 600) ÷ หนี้สินหมุนเวียน 200"""
        payload = self._payload()
        self.assertEqual(self._ratio(payload, "current_ratio")["value"], 7.0)
        # ยังไม่ map บัญชีสต๊อก → ห้ามเอามูลค่า SVL (คนละฐาน) มาหักยอด GL
        # จึงเท่ากับ current ratio พร้อมธงบอกว่าเป็นค่าประมาณ
        quick = self._ratio(payload, "quick_ratio")
        self.assertEqual(quick["value"], 7.0)
        self.assertIn("quick_approx", quick["flags"])

    def test_negative_denominator_returns_none(self):
        """หนี้สินหมุนเวียนติดลบ → current/quick ต้องเป็น None + ธง neg_base
        (ไม่ใช่ตัวเลขบวกที่อ่านแล้วเข้าใจว่าแข็งแรง)"""
        other = self.env["res.company"].create({"name": "BSF Neg Co"})
        self.env.user.company_ids = [(4, other.id)]
        acc_ap = self.env["account.account"].create({
            "code": "BSF2900", "name": "Payable neg",
            "account_type": "liability_payable", "company_id": other.id,
        })
        acc_cash = self.env["account.account"].create({
            "code": "BSF1900", "name": "Cash neg",
            "account_type": "asset_cash", "company_id": other.id,
        })
        journal = self.env["account.journal"].create({
            "name": "BSF Neg", "code": "BSFN", "type": "general",
            "company_id": other.id,
        })
        move = self.env["account.move"].create({
            "move_type": "entry", "journal_id": journal.id,
            "company_id": other.id, "date": self.today,
            "line_ids": [
                (0, 0, {"account_id": acc_ap.id, "balance": 500.0}),
                (0, 0, {"account_id": acc_cash.id, "balance": -500.0}),
            ],
        })
        move.action_post()
        payload = self.engine.get_dashboard_data({"company_id": other.id})
        current = self._ratio(payload, "current_ratio")
        self.assertIsNone(current["value"])
        self.assertIn("neg_base", current["flags"])

    def test_quick_ratio_uses_mapped_inventory(self):
        self.env["biz.smart.finance.config"].create({
            "company_id": self.company.id,
            "inventory_account_ids": [(6, 0, [self.acc_stock.id])],
        })
        payload = self._payload()
        quick = self._ratio(payload, "quick_ratio")
        # map บัญชีแล้ว → สต๊อกมาจาก GL ฐานเดียวกับสินทรัพย์หมุนเวียน
        # (1,400 − 600) / 200 = 4.0
        self.assertEqual(quick["value"], 4.0)
        self.assertNotIn("quick_approx", quick["flags"])
        # แท็บ Inventory ยัง headline ด้วย SVL (บริษัทใหม่ยังไม่มีชั้นมูลค่า = 0)
        # แล้วรายงานส่วนต่างกับ GL ผ่าน badge กระทบยอด
        kpis = payload["inventory"]["kpis"]
        self.assertEqual(kpis["gl_value"], 600.0)
        self.assertTrue(kpis["recon_shown"])
        self.assertEqual(kpis["recon_diff"], -600.0)

    def test_profitability_ratios(self):
        payload = self._payload()
        # gross = 1,000 − 600 = 400 → GPM 40%, NPM 40% (ไม่มี opex)
        self.assertEqual(self._ratio(payload, "gross_margin_pct")["value"], 40.0)
        self.assertEqual(self._ratio(payload, "net_margin_pct")["value"], 40.0)

    def test_interest_coverage_none_when_unmapped(self):
        payload = self._payload()
        # ไม่มีบัญชีดอกเบี้ย map ไว้ → คำนวณไม่ได้ ต้องเป็น None ไม่ใช่ 0
        self.assertIsNone(self._ratio(payload, "interest_coverage")["value"])

    def test_external_source_ratios(self):
        self.env["biz.smart.finance.config"].create({
            "company_id": self.company.id,
            "ratio_source": "external",
            "inventory_source": "external",
        })
        Fact = self.env["biz.smart.finance.ext.fact"]
        Fact.upsert_facts(
            self.company, self.today, "ratio_input", [
                {"metric_key": "current_assets", "amount": 900.0},
                {"metric_key": "current_liabilities", "amount": 300.0},
                {"metric_key": "total_assets", "amount": 2000.0},
                {"metric_key": "total_liabilities", "amount": 500.0},
                {"metric_key": "equity", "amount": 1500.0},
                {"metric_key": "revenue_ytd", "amount": 1000.0},
                {"metric_key": "cogs_ytd", "amount": 700.0},
                {"metric_key": "net_profit_ytd", "amount": 100.0},
            ], source="manual")
        Fact.upsert_facts(
            self.company, self.today, "inventory",
            [{"metric_key": "inventory_value", "label": "RM",
              "amount": 200.0, "qty": 10.0}], source="manual")

        payload = self._payload()
        self.assertEqual(payload["ratios"]["source"], "external")
        self.assertEqual(payload["inventory"]["source"], "external")
        self.assertEqual(self._ratio(payload, "current_ratio")["value"], 3.0)
        # quick = (900 − 200) / 300 = 2.33
        self.assertEqual(self._ratio(payload, "quick_ratio")["value"], 2.33)
        self.assertEqual(self._ratio(payload, "gross_margin_pct")["value"], 30.0)
        self.assertEqual(payload["inventory"]["kpis"]["total_value"], 200.0)
        self.assertEqual(
            [row["name"] for row in payload["inventory"]["by_category"]], ["RM"])

    def test_external_missing_inputs_reported(self):
        self.env["biz.smart.finance.config"].create({
            "company_id": self.company.id, "ratio_source": "external",
        })
        self.env["biz.smart.finance.ext.fact"].upsert_facts(
            self.company, self.today, "ratio_input",
            [{"metric_key": "current_assets", "amount": 900.0}],
            source="manual")
        payload = self._payload()
        missing = payload["ratios"]["missing_by_company"]
        self.assertTrue(missing)
        self.assertIn("equity", missing[0]["missing"])
        # ตัวหารหาย → ต้องเป็น None ไม่ใช่ตัวเลขมั่ว
        self.assertIsNone(self._ratio(payload, "current_ratio")["value"])
