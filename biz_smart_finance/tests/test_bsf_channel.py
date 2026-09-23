# -*- coding: utf-8 -*-
"""แท็บ Sales Channel (วิเคราะห์ช่องทางขาย)

DB ที่ใช้รันมีข้อมูลจริงอยู่แล้ว (shared dev DB) เทสจึงเป็น baseline-delta
เหมือนไฟล์อื่นในโมดูลนี้ — ห้าม assert ค่าสัมบูรณ์ของยอดรวม
"""
import json

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestBsfChannel(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        Users = cls.env["res.users"]
        cls.plain_user = Users.create({
            "name": "BSF Chn Plain", "login": "bsf_chn_plain",
            "groups_id": [(6, 0, [cls.env.ref("base.group_user").id])],
            "company_id": cls.company.id,
            "company_ids": [(6, 0, [cls.company.id])],
        })
        cls.viewer = Users.create({
            "name": "BSF Chn Viewer", "login": "bsf_chn_viewer",
            "groups_id": [(6, 0, [
                cls.env.ref("base.group_user").id,
                cls.env.ref("biz_smart_finance.group_bsf_user").id,
            ])],
            "company_id": cls.company.id,
            "company_ids": [(6, 0, [cls.company.id])],
        })
        cls.engine = cls.env["biz.smart.finance.dashboard"].with_user(cls.viewer)
        cls.filters = {"company_id": cls.company.id}
        cls.payload = cls.engine.get_channel_data(cls.filters)
        cls.channel = cls.payload["channel"]

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _rows(self, channel=None):
        channel = channel or self.channel
        return {row["key"]: row for row in channel["pnl_rows"]}

    def _postable_account(self, account_type):
        """บัญชีที่ลงรายการได้จริง

        DB นี้ติดตั้ง biz_parent_account ซึ่งห้ามลงรายการในบัญชีคลุม
        (`is_parent_account`) — เลือกบัญชีแรกแบบไม่กรองจะระเบิดที่ constraint
        """
        accounts = self.env["account.account"].search([
            ("account_type", "=", account_type),
            ("company_id", "=", self.company.id),
            ("deprecated", "=", False),
        ])
        if "is_parent_account" in accounts._fields:
            accounts = accounts.filtered(lambda a: not a.is_parent_account)
        return accounts[:1]

    def _post_invoice(self, partner, amount):
        income = self._postable_account("income")
        move = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": partner.id,
            "company_id": self.company.id,
            "invoice_date": fields.Date.context_today(self.env.user),
            "invoice_line_ids": [(0, 0, {
                "name": "ทดสอบช่องทางขาย",
                "quantity": 1,
                "price_unit": amount,
                "account_id": income.id,
                "tax_ids": [(6, 0, [])],
            })],
        })
        move.action_post()
        return move

    def _presentation_rate(self, as_of):
        engine = self.env["biz.smart.finance.dashboard"].sudo()
        presentation = engine._presentation_currency(self.company)
        return engine._fx_rates(
            [self.company.id], fields.Date.to_date(as_of),
            presentation)[self.company.id]

    # ------------------------------------------------------------------
    # โครง payload
    # ------------------------------------------------------------------
    def test_access_gate(self):
        with self.assertRaises(AccessError):
            self.env["biz.smart.finance.dashboard"].with_user(
                self.plain_user).get_channel_data({})

    def test_payload_shape(self):
        json.dumps(self.payload, default=str)
        for key in ("dims", "dim", "channel_id", "channels", "columns",
                    "matrix", "pnl_rows", "alloc"):
            self.assertIn(key, self.channel)
        # งบกระแสเงินสดถูกตัดออกจากแท็บนี้ตามที่ผู้ใช้สั่ง (2026-09-04) —
        # แยกตามช่องทางไม่ได้อยู่แล้ว ให้ไปดูที่ Statements / Compare BI
        self.assertNotIn("cf_rows", self.channel)
        self.assertEqual(
            [d["code"] for d in self.channel["dims"]],
            ["partner", "team", "analytic"])
        # คอลัมน์ = งวดของปีงบถึง as_of เท่านั้น (ไม่มีคอลัมน์อนาคต)
        as_of = self.payload["filters"]["as_of"]
        self.assertTrue(self.channel["columns"])
        for col in self.channel["columns"]:
            self.assertLessEqual(col["date_to"], as_of)
            self.assertLessEqual(col["date_from"], col["date_to"])
        # ลำดับบรรทัดต้องตรงกับงบจริง (ตามเวิร์กชีตต้นแบบ: รายได้ → EBIT)
        self.assertEqual(
            [r["key"] for r in self.channel["pnl_rows"]],
            ["revenue_op", "cogs", "gross_op", "gross_pct", "sga", "sga_pct",
             "other_income", "ebitda", "depreciation", "ebit", "ebit_pct"])

    def test_channel_tab_is_not_in_full_payload(self):
        """แท็บนี้ตั้งใจไม่อยู่ใน payload หลัก — โหลดสไลซ์ตอนเปิดแท็บเท่านั้น

        ถ้ามันหลุดเข้าไป การโหลดหน้าแรกของทุกคนจะแบกงบรายเดือนทั้งปีงบ
        """
        full = self.engine.get_dashboard_data(self.filters)
        self.assertNotIn("channel", full)

    # ------------------------------------------------------------------
    # กระทบยอด — หัวใจของแท็บนี้
    # ------------------------------------------------------------------
    def test_sum_of_channels_ties_to_company(self):
        """Σ ทุกช่องทางของบรรทัดหนึ่ง = ยอดบรรทัดเดียวกันระดับบริษัท ทุกเดือน"""
        for dim in ("partner", "team", "analytic"):
            channel = self.engine.get_channel_data(
                dict(self.filters, channel_dim=dim))["channel"]
            rows = self._rows(channel)
            span = len(channel["columns"])
            for metric, key in (("revenue", "revenue_op"), ("cogs", "cogs"),
                                ("gross", "gross_op"), ("sga", "sga"),
                                ("ebit", "ebit")):
                for index in range(span):
                    total = sum(row["metrics"][metric][index]
                                for row in channel["matrix"]["rows"])
                    self.assertAlmostEqual(
                        total, rows[key]["values"][index], places=1,
                        msg="มิติ %s บรรทัด %s เดือนที่ %s ไม่กระทบยอด"
                            % (dim, key, index))

    def test_waterfall_identity(self):
        """บรรทัดสรุปของงบต้องเป็นผลของบรรทัดข้างบนเสมอ"""
        rows = self._rows()
        span = len(self.channel["columns"])
        for index in range(span):
            def at(key):
                return rows[key]["values"][index]

            self.assertAlmostEqual(
                at("gross_op"), at("revenue_op") - at("cogs"), places=1)
            self.assertAlmostEqual(
                at("ebitda"),
                at("gross_op") - at("sga") + at("other_income"), places=1)
            self.assertAlmostEqual(
                at("ebit"), at("ebitda") - at("depreciation"), places=1)

    def test_column_total_matches_row_total(self):
        """คอลัมน์ "รวม" ต้องเท่าผลบวกของทุกเดือน (ไม่ใช่ยอดที่คิดแยก)"""
        for row in self.channel["pnl_rows"]:
            if row.get("kind") == "pct":
                continue
            self.assertAlmostEqual(
                row["total"], sum(row["values"]), places=1,
                msg="แถว %s รวมไม่ตรง" % row["key"])

    def test_sub_rows_tie_to_parent(self):
        """แถวย่อย (สาขา / ประเภทต้นทุน) ต้องบวกได้เท่าบรรทัดแม่ทุกเดือน

        เพดานจำนวนแถวย่อยต้องกลืนส่วนที่ตัดออกเข้าแถวปิดท้าย ไม่ใช่ทำให้ยอดหาย
        """
        for channel_id in (0, *[row["key"] for row in
                                self.channel["channels"][:1]]):
            channel = self.engine.get_channel_data(
                dict(self.filters, channel_id=channel_id))["channel"]
            span = len(channel["columns"])
            for row in channel["pnl_rows"]:
                if row["kind"] != "split" or not row["sub"]:
                    continue
                for index in range(span):
                    self.assertAlmostEqual(
                        sum(sub["values"][index] for sub in row["sub"]),
                        row["values"][index], places=1,
                        msg="แถวย่อยของ %s (ช่องทาง %s) เดือนที่ %s ไม่ตรง"
                            % (row["key"], channel_id, index))

    def test_direct_before_allocation(self):
        """ใบแจ้งหนี้ของลูกค้าหนึ่ง = ยอด direct ของช่องทางนั้น ไม่ถูกเฉลี่ยทิ้ง"""
        before = self.engine.get_channel_data(self.filters)["channel"]
        chain = self.env["res.partner"].create({"name": "BSF Chain Co"})
        branch = self.env["res.partner"].create({
            "name": "BSF Chain สาขาทดสอบ", "parent_id": chain.id,
            "type": "invoice",
        })
        move = self._post_invoice(branch, 40000.0)
        after = self.engine.get_channel_data(self.filters)["channel"]
        rate = self._presentation_rate(
            self.payload["filters"]["as_of"])
        expected = move.amount_untaxed * rate

        def revenue_of(payload, key):
            row = next((r for r in payload["matrix"]["rows"]
                        if r["key"] == key), None)
            return row["totals"]["revenue"] if row else 0.0

        # ยอดเข้าช่องทาง "เชน" ไม่ใช่กองที่รอเฉลี่ย
        self.assertAlmostEqual(
            revenue_of(after, chain.id) - revenue_of(before, chain.id),
            expected, delta=0.02)
        self.assertAlmostEqual(
            revenue_of(after, 0) - revenue_of(before, 0), 0.0, delta=0.02)
        # เลือกช่องทางนั้นแล้วต้องเห็นแถวย่อยระดับ "สาขา"
        scoped = self.engine.get_channel_data(
            dict(self.filters, channel_id=chain.id))["channel"]
        self.assertEqual(scoped["channel_id"], chain.id)
        revenue_row = self._rows(scoped)["revenue_op"]
        self.assertAlmostEqual(
            revenue_row["total"], expected, delta=0.02)
        self.assertIn(
            branch.id,
            [int(sub["key"].split("-")[1]) for sub in revenue_row["sub"]])

    def test_allocation_follows_revenue(self):
        """ค่าใช้จ่ายที่ผูกช่องทางไม่ได้ต้องถูกเฉลี่ยตามสัดส่วนรายได้ ครบทั้งก้อน"""
        chain_a = self.env["res.partner"].create({"name": "BSF Chain A"})
        chain_b = self.env["res.partner"].create({"name": "BSF Chain B"})
        self._post_invoice(chain_a, 300000.0)
        self._post_invoice(chain_b, 100000.0)
        expense = self._postable_account("expense")
        cash = self._postable_account("asset_cash")
        if not (expense and cash):
            self.skipTest("ผังบัญชีของบริษัทนี้ไม่มีบัญชีค่าใช้จ่าย/เงินสด")
        today = fields.Date.context_today(self.env.user)
        before = self.engine.get_channel_data(self.filters)["channel"]
        # ค่าใช้จ่ายส่วนกลาง: ไม่มีคู่ค้า จึงผูกช่องทางจาก GL ไม่ได้เลย
        self.env["account.move"].create({
            "move_type": "entry",
            "company_id": self.company.id,
            "date": today,
            "line_ids": [
                (0, 0, {"account_id": expense.id, "debit": 20000.0,
                        "credit": 0.0, "name": "ค่าใช้จ่ายส่วนกลาง (test)"}),
                (0, 0, {"account_id": cash.id, "debit": 0.0,
                        "credit": 20000.0, "name": "ค่าใช้จ่ายส่วนกลาง (test)"}),
            ],
        }).action_post()
        after = self.engine.get_channel_data(self.filters)["channel"]

        def sga_of(payload, key):
            row = next((r for r in payload["matrix"]["rows"]
                        if r["key"] == key), None)
            return row["totals"]["sga"] if row else 0.0

        rate = self._presentation_rate(self.payload["filters"]["as_of"])
        delta_a = sga_of(after, chain_a.id) - sga_of(before, chain_a.id)
        delta_b = sga_of(after, chain_b.id) - sga_of(before, chain_b.id)
        # ทั้งก้อนต้องถูกเฉลี่ยออกไป (Σ ทุกช่องทาง = ยอดที่โพสต์)
        total = sum(row["totals"]["sga"] for row in after["matrix"]["rows"]) \
            - sum(row["totals"]["sga"] for row in before["matrix"]["rows"])
        self.assertAlmostEqual(total, 20000.0 * rate, delta=0.05)
        # และช่องทางที่มีรายได้มากกว่าต้องรับส่วนแบ่งมากกว่า
        self.assertGreater(delta_a, delta_b)
        # บรรทัด SG&A ต้องบอกด้วยว่าส่วนไหนมาจากการเฉลี่ย
        self.assertTrue(any(self._rows(after)["sga"]["allocated"]))

    # ------------------------------------------------------------------
    # ตัวกรอง / ขอบเขต
    # ------------------------------------------------------------------
    def test_filters_are_validated(self):
        payload = self.engine.get_channel_data(dict(
            self.filters, channel_dim="ไม่มีจริง", channel_id=999999999))
        self.assertEqual(payload["filters"]["channel_dim"], "partner")
        self.assertEqual(payload["channel"]["dim"], "partner")
        # id ที่ไม่มีในปีงบนี้ต้องตกกลับเป็น "ทุกช่องทาง"
        self.assertEqual(payload["channel"]["channel_id"], 0)

    def test_company_scope_not_leaked(self):
        other = self.env["res.company"].create({"name": "BSF Chn Other Co"})
        # res.company.create ผูกบริษัทใหม่ให้ user ปัจจุบันอัตโนมัติ — ต้องถอดออก
        self.viewer.write({"company_ids": [(6, 0, [self.company.id])]})
        payload = self.engine.get_channel_data({"company_id": other.id})
        self.assertNotEqual(payload["filters"]["company_id"], other.id)
