# -*- coding: utf-8 -*-
"""แท็บ Cash & Liquidity รายธนาคาร — DB ที่ใช้รันมีข้อมูลจริงอยู่แล้ว (shared
dev DB) จึงต้องเป็น baseline-delta: จับ payload ก่อนสร้าง fixture แล้ว assert
ส่วนต่าง ห้าม assert ค่าสัมบูรณ์ของยอดรวม (ยกเว้นค่าที่ fixture ควบคุมเองทั้ง
100% เช่นวงเงินสินเชื่อที่สร้างขึ้นมาเพื่อเทสโดยเฉพาะ)"""
import json
from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestBsfCashBank(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        Users = cls.env["res.users"]
        cls.viewer = Users.create({
            "name": "BSF Bank Viewer", "login": "bsf_bank_viewer_user",
            "groups_id": [(6, 0, [
                cls.env.ref("base.group_user").id,
                cls.env.ref("biz_smart_finance.group_bsf_user").id,
            ])],
            "company_id": cls.company.id,
            "company_ids": [(6, 0, [cls.company.id])],
        })
        cls.manager = Users.create({
            "name": "BSF Bank Manager", "login": "bsf_bank_manager_user",
            "groups_id": [(6, 0, [
                cls.env.ref("base.group_user").id,
                cls.env.ref("biz_smart_finance.group_bsf_manager").id,
            ])],
            "company_id": cls.company.id,
            "company_ids": [(6, 0, [cls.company.id])],
        })
        cls.engine = cls.env["biz.smart.finance.dashboard"].with_user(cls.viewer)

        # baseline ก่อนสร้าง fixture ใด ๆ (กติกา baseline-delta ของ repo นี้)
        cls.baseline = cls.engine.get_dashboard_data(
            {"company_id": cls.company.id})

        Account = cls.env["account.account"]
        cls.account_a = Account.create({
            "name": "BSF Test Bank A", "code": "BSFA100",
            "account_type": "asset_cash", "company_id": cls.company.id,
        })
        cls.account_b = Account.create({
            "name": "BSF Test Bank B", "code": "BSFB100",
            "account_type": "asset_cash", "company_id": cls.company.id,
        })
        cls.journal_a = cls.env["account.journal"].create({
            "name": "BSF Test Journal A", "type": "bank", "code": "BSFJA",
            "company_id": cls.company.id, "default_account_id": cls.account_a.id,
        })
        cls.journal_b = cls.env["account.journal"].create({
            "name": "BSF Test Journal B", "type": "bank", "code": "BSFJB",
            "company_id": cls.company.id, "default_account_id": cls.account_b.id,
        })

        # ธนาคาร A: รับภาระจ่ายทั้งหมด (100%) ไม่รับเงินเข้าเลย (0%) —
        # รับประกันว่าจะติดลบ/หลุด buffer แน่นอน ไม่ขึ้นกับข้อมูลจริงใน dev DB
        cls.bank_a = cls.env["biz.smart.finance.bank"].create({
            "name": "BSF Test Bank A", "company_id": cls.company.id,
            "journal_ids": [(6, 0, [cls.journal_a.id])],
            "min_balance": 10000.0,
            "receipt_share_pct": 0.0, "payment_share_pct": 100.0,
        })
        # ธนาคาร B: รับเงินเข้าทั้งหมด (100%) ไม่จ่ายเลย (0%) + มียอดยกมา
        # ก้อนใหญ่ — เป็นธนาคารที่มีเงินเหลือให้โอนไปช่วยธนาคาร A ได้เสมอ
        cls.bank_b = cls.env["biz.smart.finance.bank"].create({
            "name": "BSF Test Bank B", "company_id": cls.company.id,
            "journal_ids": [(6, 0, [cls.journal_b.id])],
            "min_balance": 0.0,
            "receipt_share_pct": 100.0, "payment_share_pct": 0.0,
        })

        # ต้องผ่านสมุดรายวันของธนาคาร B เอง (journal_b) ไม่ใช่สมุดรายวัน
        # อื่น — _bank_balances กรองด้วย account_id ของ default_account_id
        # ต่อธนาคาร ไม่ใช่ journal_id (ดูหมายเหตุใน _build_shared) แต่การผ่าน
        # journal_b ก็ยังจำเป็นสำหรับให้ debit/credit ไปเข้าประวัติของ
        # ธนาคาร B ใน _bank_shares ด้วยเช่นกัน
        income_account = Account.search([
            ("company_id", "=", cls.company.id),
            ("account_type", "=", "income"),
        ], limit=1)
        move = cls.env["account.move"].create({
            "journal_id": cls.journal_b.id,
            "date": fields.Date.context_today(cls.env.user) - timedelta(days=30),
            "line_ids": [
                (0, 0, {"account_id": cls.account_b.id,
                        "debit": 1000000.0, "credit": 0.0}),
                (0, 0, {"account_id": income_account.id,
                        "debit": 0.0, "credit": 1000000.0}),
            ],
        })
        move.action_post()

        # รายจ่ายประจำรายสัปดาห์ — รับประกันว่ามี outflow ให้ธนาคาร A แบกทุก
        # สัปดาห์ (ไม่พึ่งข้อมูล AR/AP จริงใน dev DB ที่ไม่รู้ปริมาณล่วงหน้า)
        cls.forecast_line = cls.env["biz.smart.finance.forecast.line"].create({
            "name": "เงินเดือน (test bank)", "company_id": cls.company.id,
            "flow_type": "out", "category": "payroll",
            "amount": 50000.0, "recurrence": "weekly",
        })

        cls.facility = cls.env["biz.smart.finance.bank.facility"].create({
            "bank_id": cls.bank_a.id, "name": "OD ทดสอบ",
            "facility_type": "od", "credit_limit": 1000000.0,
            "drawn_basis": "manual", "drawn_amount": 300000.0,
        })

        cls.payload = cls.engine.get_dashboard_data(
            {"company_id": cls.company.id})
        cls.cash = cls.payload["cash"]

    # ------------------------------------------------------------------
    def test_serializable(self):
        json.dumps(self.cash)

    def test_bank_total_matches_group_opening(self):
        total_banks = sum(
            row["current_balance"] for row in self.cash["banks"]["rows"])
        self.assertAlmostEqual(
            total_banks, self.cash["forecast"]["opening"], delta=0.05)

    def test_weekly_closing_reconciles(self):
        rows = self.cash["banks"]["rows"]
        closing = self.cash["forecast"]["closing"]
        for i, expected in enumerate(closing):
            total = sum(row["weeks"][i]["ending"] for row in rows)
            self.assertAlmostEqual(
                total, expected, delta=0.05,
                msg="สัปดาห์ %s: Σ ending รายธนาคาร (%.2f) ต้องเท่ากับ "
                    "forecast.closing (%.2f)" % (i, total, expected))

    def test_share_override_normalises(self):
        f = self.engine._normalize_filters({"company_id": self.company.id})
        shared = self.engine.sudo()._build_shared(f)
        shared["cash_forecast"] = self.engine.sudo()._build_cash_forecast(
            f, shared)
        balances = self.engine.sudo()._bank_balances(f, shared)
        receipt_share, payment_share, basis = self.engine.sudo()._bank_shares(
            f, shared, balances)
        self.assertAlmostEqual(sum(receipt_share.values()), 1.0, places=6)
        self.assertAlmostEqual(sum(payment_share.values()), 1.0, places=6)
        self.assertEqual(basis, "override")
        # bank_a ตั้งทับ receipt=0% payment=100% ตรงตามที่กรอก
        self.assertAlmostEqual(receipt_share[self.bank_a.id], 0.0, places=6)
        self.assertAlmostEqual(payment_share[self.bank_a.id], 1.0, places=6)

    def test_facility_utilisation(self):
        # เลข credit_limit/drawn ที่ engine คืนผ่าน _conv (แปลงเป็นสกุลนำ
        # เสนอ) แล้ว — dev DB นี้บริษัทตั้งต้นไม่ใช่สกุลเดียวกับสกุลนำเสนอ
        # (พบ ~38.4x ระหว่างพัฒนา) จึงต้องเทียบกับค่าที่แปลงแล้วเช่นกัน ไม่ใช่
        # ตัวเลขดิบ 1,000,000/300,000 ตรง ๆ — utilisation_pct/status เป็น
        # อัตราส่วนจึงไม่ผันตาม fx และเทียบตรง ๆ ได้อยู่แล้ว
        rows = [
            r for r in self.cash["facilities"]["rows"]
            if r["id"] == self.facility.id
        ]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        f = self.engine._normalize_filters({"company_id": self.company.id})
        shared = self.engine.sudo()._build_shared(f)
        expected_limit = self.engine.sudo()._conv(
            shared, 1000000.0, self.company.id)
        expected_drawn = self.engine.sudo()._conv(
            shared, 300000.0, self.company.id)
        self.assertAlmostEqual(row["credit_limit"], expected_limit, delta=0.05)
        self.assertAlmostEqual(row["drawn"], expected_drawn, delta=0.05)
        self.assertAlmostEqual(
            row["available"], expected_limit - expected_drawn, delta=0.05)
        self.assertAlmostEqual(row["utilisation_pct"], 30.0, places=1)
        self.assertEqual(row["status"], "healthy")

    def test_transfer_is_zero_sum(self):
        before = self.engine.get_dashboard_data(
            {"company_id": self.company.id})["cash"]
        transfer = self.env["biz.smart.finance.bank.transfer"].sudo().create({
            "source_bank_id": self.bank_b.id, "dest_bank_id": self.bank_a.id,
            "amount": 50000.0,
            "execution_date": fields.Date.context_today(self.env.user),
            "purpose": "liquidity", "state": "draft",
        })
        after = self.engine.get_dashboard_data(
            {"company_id": self.company.id})["cash"]

        # เงินสดรวมทั้งกลุ่มต้องไม่ขยับจากแผนโอน (โอนภายในกลุ่มเดียวกัน)
        for b, a in zip(before["forecast"]["closing"],
                         after["forecast"]["closing"]):
            self.assertAlmostEqual(b, a, delta=0.05)

        def week0_ending(payload, bank_id):
            row = next(
                r for r in payload["banks"]["rows"] if r["bank_id"] == bank_id)
            return row["weeks"][0]["ending"]

        delta_a = (week0_ending(after, self.bank_a.id)
                   - week0_ending(before, self.bank_a.id))
        delta_b = (week0_ending(after, self.bank_b.id)
                   - week0_ending(before, self.bank_b.id))
        # 50,000 เป็นสกุลของธนาคาร (company currency) — engine แปลงเป็นสกุล
        # นำเสนอก่อนคำนวณเสมอ (ดูเหตุผลใน test_facility_utilisation)
        f = self.engine._normalize_filters({"company_id": self.company.id})
        shared = self.engine.sudo()._build_shared(f)
        expected_amount = self.engine.sudo()._conv(
            shared, 50000.0, transfer.company_id.id)
        self.assertAlmostEqual(delta_a, expected_amount, delta=0.05)
        self.assertAlmostEqual(delta_b, -expected_amount, delta=0.05)

    def test_no_bank_master_hint(self):
        f = self.engine._normalize_filters({"company_id": self.company.id})
        shared = dict(self.engine.sudo()._build_shared(f))

        shared["bank_rows"] = []
        hints_empty = {
            h["code"] for h in self.engine.sudo()._empty_hints(f, shared)}
        self.assertIn("no_bank_master", hints_empty)

        shared["bank_rows"] = [{"id": self.bank_a.id}]
        hints_full = {
            h["code"] for h in self.engine.sudo()._empty_hints(f, shared)}
        self.assertNotIn("no_bank_master", hints_full)

    def test_suggest_requires_manager(self):
        with self.assertRaises(AccessError):
            self.engine.action_bsf_suggest_transfers(
                {"company_id": self.company.id})

    def test_suggest_idempotent(self):
        manager_engine = self.env["biz.smart.finance.dashboard"].with_user(
            self.manager)
        Transfer = self.env["biz.smart.finance.bank.transfer"]
        suggested_domain = [
            ("company_id", "=", self.company.id),
            ("origin", "=", "suggested"), ("state", "=", "draft"),
        ]

        result1 = manager_engine.action_bsf_suggest_transfers(
            {"company_id": self.company.id})
        self.assertGreater(
            result1["created"], 0,
            "ธนาคาร A ตั้งไว้ให้ต้องหลุด buffer แน่นอน — ควรเสนอแผนโอนได้")
        count_after_1 = Transfer.search_count(suggested_domain)

        result2 = manager_engine.action_bsf_suggest_transfers(
            {"company_id": self.company.id})
        count_after_2 = Transfer.search_count(suggested_domain)

        self.assertEqual(count_after_1, count_after_2)
