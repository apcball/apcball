# -*- coding: utf-8 -*-
"""Engine tests — DB ที่ใช้รันมีข้อมูลจริงอยู่แล้ว (shared dev DB) จึงต้องเป็น
baseline-delta: จับ payload ก่อนสร้าง fixture แล้ว assert ส่วนต่าง
ห้าม assert ค่าสัมบูรณ์ของยอดรวม"""
import json
from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestBsfDashboard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        Users = cls.env["res.users"]
        cls.plain_user = Users.create({
            "name": "BSF Plain", "login": "bsf_plain_user",
            "groups_id": [(6, 0, [cls.env.ref("base.group_user").id])],
            "company_id": cls.company.id,
            "company_ids": [(6, 0, [cls.company.id])],
        })
        cls.viewer = Users.create({
            "name": "BSF Viewer", "login": "bsf_viewer_user",
            "groups_id": [(6, 0, [
                cls.env.ref("base.group_user").id,
                cls.env.ref("biz_smart_finance.group_bsf_user").id,
            ])],
            "company_id": cls.company.id,
            "company_ids": [(6, 0, [cls.company.id])],
        })
        cls.engine = cls.env["biz.smart.finance.dashboard"].with_user(cls.viewer)

        # baseline ก่อนสร้าง fixture ใด ๆ (กติกา baseline-delta ของ repo นี้)
        cls.baseline = cls.engine.get_dashboard_data(
            {"company_id": cls.company.id})

        Config = cls.env["biz.smart.finance.config"]
        existing = Config.search([("company_id", "=", cls.company.id)])
        cls.config = existing or Config.create({
            "company_id": cls.company.id,
            "min_cash_requirement": 1000000.0,
            "margin_leakage_alert_pct": 5.0,
        })
        cls.forecast_line = cls.env["biz.smart.finance.forecast.line"].create({
            "name": "เงินเดือน (test)", "company_id": cls.company.id,
            "flow_type": "out", "category": "payroll",
            "amount": 100000.0, "recurrence": "weekly",
        })
        cls.risk = cls.env["biz.smart.finance.risk"].create({
            "name": "ทดสอบความเสี่ยง", "company_id": cls.company.id,
            "impact": 4, "likelihood": 4,
            "early_warning": "ตัวชี้วัดทดสอบ",
        })
        cls.payload = cls.engine.get_dashboard_data(
            {"company_id": cls.company.id})

    def test_access_gate(self):
        # TransactionCase รันเป็น superuser — gate ต้องทดสอบผ่าน with_user เท่านั้น
        with self.assertRaises(AccessError):
            self.env["biz.smart.finance.dashboard"].with_user(
                self.plain_user).get_dashboard_data({})

    def test_serializable(self):
        json.dumps(self.payload)

    def test_payload_shape(self):
        payload = self.payload
        for key in ("filters", "empty_hints", "overview", "cash",
                    "sales", "margin", "ap", "risk", "statements", "compare"):
            self.assertIn(key, payload)
        self.assertEqual(len(payload["cash"]["forecast"]["weeks"]), 13)
        self.assertEqual(len(payload["cash"]["forecast"]["rows"]), 13)
        self.assertEqual(payload["filters"]["company_id"], self.company.id)
        self.assertEqual(payload["filters"]["scenario"], "base")
        self.assertEqual(len(payload["sales"]["funnel"]), 6)
        matrix = payload["risk"]["matrix"]
        self.assertTrue(matrix["columns"])
        for row in matrix["rows"]:
            # ทุกแถวต้องมีช่องครบทุกคอลัมน์ ไม่งั้นตารางบนจอเหลื่อมกัน
            self.assertEqual(len(row["cells"]), len(matrix["columns"]))
            for cell in row["cells"]:
                self.assertTrue(0 <= cell["score"] <= 25)

    def test_overview_dimensions(self):
        """control tower — ครบ 11 มิติ ทุกใบมีสถานะที่รู้จักและคีย์ครบ"""
        dims = self.payload["overview"]["dimensions"]
        self.assertEqual(
            {d["id"] for d in dims},
            {"cash", "sales", "ap", "margin", "forecast", "inventory",
             "ratios", "controlling", "statements", "compare", "risk"},
        )
        for dim in dims:
            self.assertIn(
                dim["status"], ("good", "warn", "risk", "neutral"))
            for key in ("label", "icon", "value", "fmt", "sub", "note"):
                self.assertIn(key, dim)
        json.dumps(dims)

    def test_overview_kpis_extended(self):
        kpis = self.payload["overview"]["kpis"]
        for key in ("min_13w", "min_13w_label", "min_cash_breach",
                    "working_capital", "ccc_days"):
            self.assertIn(key, kpis)
        # bu_table ได้คอลัมน์ cash/ar/ap ต่อบริษัทเพิ่ม
        for row in self.payload["overview"]["bu_table"]:
            for key in ("cash", "ar", "ap"):
                self.assertIn(key, row)

    def test_ratios_summary(self):
        summary = self.payload["ratios"]["summary"]
        for key in ("current_ratio", "debt_to_equity", "net_margin_pct",
                    "dso_days", "dio_days", "dpo_days", "ccc_days",
                    "working_capital"):
            self.assertIn(key, summary)

    def test_risk_scenarios_shape(self):
        risk = self.payload["risk"]
        # Base ต้องไม่มีสมมติฐานปรับใด ๆ — ตัวเลขทุกใบเป็นศูนย์
        self.assertTrue(
            all(t["value"] == 0 for t in risk["assumptions"]["base"]))
        self.assertTrue(
            any(t["value"] for t in risk["assumptions"]["downside"]))
        # โหมด Base ใช้ช็อกมาตรฐานของ Downside ในตอร์นาโด
        self.assertEqual(risk["shock_scenario"], "downside")
        self.assertTrue(risk["horizons"])
        for horizon in risk["horizons"]:
            outcome = risk["outcomes"][str(horizon)]
            for scenario in ("base", "downside", "stress"):
                self.assertIn("min_cash", outcome[scenario])
            # Base ไม่มีช็อก → กำไรไม่หาย; downside/stress ต้องหายมากขึ้นตามลำดับ
            self.assertEqual(outcome["base"]["ebitda_hit"], 0.0)
            self.assertLessEqual(
                outcome["downside"]["ebitda_hit"],
                outcome["stress"]["ebitda_hit"] + 0.01,
            )
            self.assertTrue(risk["sensitivity"][str(horizon)])
            for row in risk["sensitivity"][str(horizon)]:
                self.assertGreaterEqual(row["amount"], 0.0)
                self.assertIn(row["basis"], ("cash", "ebitda"))

    def test_risk_early_warning_priority(self):
        rows = self.payload["risk"]["early_warning"]
        self.assertEqual(
            [r["priority"] for r in rows], list(range(1, len(rows) + 1)))
        registered = [r for r in rows if r["id"] == self.risk.id]
        self.assertTrue(registered)
        self.assertEqual(registered[0]["status"], "not_started")

    def test_delta_risk(self):
        base_names = {
            r["name"] for r in self.baseline["risk"]["early_warning"]
        }
        new_names = {
            r["name"] for r in self.payload["risk"]["early_warning"]
        }
        self.assertIn("ทดสอบความเสี่ยง", new_names - base_names)
        found = [
            r for r in self.payload["overview"]["top_risks"]
            if r.get("id") == self.risk.id
        ]
        self.assertTrue(found)
        self.assertEqual(found[0]["level"], "high")
        self.assertEqual(found[0]["score"], 16)

    def test_delta_forecast_line(self):
        base_rows = self.baseline["cash"]["forecast"]["rows"]
        new_rows = self.payload["cash"]["forecast"]["rows"]
        # ทุกสัปดาห์ต้องมีรายจ่าย payroll เพิ่มอย่างน้อย 100k จาก fixture
        for base, new in zip(base_rows, new_rows):
            self.assertGreaterEqual(
                new["outflow_payroll_opex"] - base["outflow_payroll_opex"],
                100000.0 - 0.01,
            )

    def test_scenario_shifts_collections(self):
        downside = self.engine.get_dashboard_data({
            "company_id": self.company.id, "scenario": "downside",
        })
        base_rows = self.payload["cash"]["forecast"]["rows"]
        down_rows = downside["cash"]["forecast"]["rows"]
        # สัปดาห์แรก เงินเข้าฝั่ง downside ต้องไม่มากกว่า base
        self.assertLessEqual(
            down_rows[0]["inflow_collections"],
            base_rows[0]["inflow_collections"] + 0.01,
        )
        self.assertEqual(downside["filters"]["scenario"], "downside")
        self.assertGreater(
            downside["risk"]["multipliers"]["collection_delay_pct"], 0)

    def test_statements_shape(self):
        st = self.payload["statements"]
        for key in ("pnl", "balance_sheet", "cashflow", "ar_aging",
                    "ai_summary", "as_of", "as_of_prior"):
            self.assertIn(key, st)
        # งบแสดงฐานะการเงินแบบ waterfall — แยกหมุนเวียน/ไม่หมุนเวียน + subtotal
        bs = st["balance_sheet"]
        bs_by_key = {r["key"]: r for r in bs["rows"]}
        for k in ("asset_cash", "asset_receivable", "total_ca", "total_nca",
                  "total_assets", "liability_payable", "total_cl", "total_ncl",
                  "total_liab", "retained_earnings", "total_equity",
                  "total_liab_eq"):
            self.assertIn(k, bs_by_key)
        # subtotal หมวด = ผลรวมของบรรทัด line ในหมวดนั้น
        for sec, sub_key in (("ca", "total_ca"), ("nca", "total_nca"),
                             ("cl", "total_cl"), ("ncl", "total_ncl"),
                             ("eq", "total_equity")):
            line_sum = sum(
                r["amount"] for r in bs["rows"]
                if r["kind"] == "line" and r["sec"] == sec)
            self.assertAlmostEqual(
                bs_by_key[sub_key]["amount"], line_sum, places=1)
        self.assertAlmostEqual(
            bs_by_key["total_assets"]["amount"],
            bs_by_key["total_ca"]["amount"] + bs_by_key["total_nca"]["amount"],
            places=1)
        self.assertAlmostEqual(
            bs_by_key["total_liab_eq"]["amount"],
            bs_by_key["total_liab"]["amount"]
            + bs_by_key["total_equity"]["amount"], places=1)
        # งบดุลต้องดุล (นอกจากบัญชี off_balance ที่โชว์เป็น check)
        self.assertAlmostEqual(
            bs_by_key["total_assets"]["amount"]
            - bs_by_key["total_liab_eq"]["amount"], bs["check"], places=1)
        # งบกำไรขาดทุนแบบ waterfall — ลำดับบรรทัดต้องตรงตามงบจริง
        pnl_rows = st["pnl"]["rows"]
        self.assertEqual(
            [r["key"] for r in pnl_rows],
            ["revenue_op", "cogs", "gross_op", "sga", "other_income",
             "ebitda", "depreciation", "ebit", "interest", "pretax",
             "tax", "net"])
        self.assertEqual(
            [r["key"] for r in pnl_rows if r["kind"] == "total"],
            ["gross_op", "ebitda", "ebit", "pretax", "net"])
        # กระทบยอด: แต่ละบรรทัดสรุป = ผลรวมสะสมของบรรทัดเหนือมัน (sign ในตัวเลข)
        run = {}
        for r in pnl_rows:
            run[r["key"]] = r["amount"]
        self.assertAlmostEqual(
            run["gross_op"], run["revenue_op"] - run["cogs"], places=1)
        self.assertAlmostEqual(
            run["ebitda"],
            run["gross_op"] - run["sga"] + run["other_income"], places=1)
        self.assertAlmostEqual(
            run["ebit"], run["ebitda"] - run["depreciation"], places=1)
        self.assertAlmostEqual(
            run["pretax"], run["ebit"] - run["interest"], places=1)
        self.assertAlmostEqual(
            run["net"], run["pretax"] - run["tax"], places=1)
        # งบกระแสเงินสดแบบ waterfall — CFO → CFI → CFF → Net change
        cf = st["cashflow"]
        cf_by_key = {r["key"]: r for r in cf["rows"]}
        self.assertEqual(
            [r["key"] for r in cf["rows"] if r["kind"] == "subtotal"],
            ["total_cfo", "total_cfi", "total_cff", "net_change"])
        for sec, sub in (("cfo", "total_cfo"), ("cfi", "total_cfi"),
                         ("cff", "total_cff")):
            line_sum = sum(
                r["amount"] for r in cf["rows"]
                if r["kind"] == "line" and r["sec"] == sec)
            self.assertAlmostEqual(
                cf_by_key[sub]["amount"], line_sum, places=1)
        self.assertAlmostEqual(
            cf_by_key["net_change"]["amount"],
            cf_by_key["total_cfo"]["amount"]
            + cf_by_key["total_cfi"]["amount"]
            + cf_by_key["total_cff"]["amount"], places=1)
        self.assertAlmostEqual(cf["net_change"],
                               cf_by_key["net_change"]["amount"], places=1)
        # identity กระแสเงินสด: ปลายงวด = ต้นงวด + สุทธิ + check
        self.assertAlmostEqual(
            cf["closing_cash"],
            cf["opening_cash"] + cf["net_change"] + cf["check"], places=1)
        aging = st["ar_aging"]
        self.assertAlmostEqual(
            aging["total"],
            sum(aging["buckets"].values()), places=1)

    def test_statements_delta_invoice(self):
        """ตั้งใบแจ้งหนี้แล้วยอดต้องไหลเข้า P&L / BS / AR aging เท่ากันเป๊ะ"""
        before = self.engine.get_dashboard_data(
            {"company_id": self.company.id})
        income = self.env["account.account"].search([
            ("account_type", "=", "income"),
            ("company_id", "=", self.company.id),
            ("deprecated", "=", False),
        ], limit=1)
        partner = self.env["res.partner"].create(
            {"name": "BSF Stmt Customer", "company_id": self.company.id})
        move = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": partner.id,
            "company_id": self.company.id,
            "invoice_date": fields.Date.context_today(self.env.user),
            "invoice_line_ids": [(0, 0, {
                "name": "งานทดสอบงบการเงิน",
                "quantity": 1,
                "price_unit": 50000.0,
                "account_id": income.id,
                "tax_ids": [(6, 0, [])],
            })],
        })
        move.action_post()
        after = self.engine.get_dashboard_data(
            {"company_id": self.company.id})

        def pnl_row(payload, key):
            rows = payload["statements"]["pnl"]["rows"]
            return next(r for r in rows if r["key"] == key)

        def bs_row(payload, key):
            rows = payload["statements"]["balance_sheet"]["rows"]
            return next(r for r in rows if r["key"] == key)

        # ยอดทุกช่องถูกแปลงเป็นสกุลนำเสนอแล้ว — ถ้า DB ตั้งสกุลนำเสนอไว้คนละ
        # สกุลกับบริษัท ยอดหน้าใบแจ้งหนี้จะไม่ตรงกับจอจนกว่าจะคูณอัตราเดียวกัน
        rate = self._presentation_rate(after["filters"]["as_of"])
        # P&L: รายได้จากการดำเนินงาน YTD เพิ่มเท่ายอดก่อนภาษี
        self.assertAlmostEqual(
            pnl_row(after, "revenue_op")["amount"]
            - pnl_row(before, "revenue_op")["amount"],
            50000.0 * rate, delta=0.02)
        # BS: ลูกหนี้เพิ่มเท่ายอดรวมใบแจ้งหนี้ และงบยังดุลเท่าเดิม
        self.assertAlmostEqual(
            bs_row(after, "asset_receivable")["amount"]
            - bs_row(before, "asset_receivable")["amount"],
            move.amount_total * rate, delta=0.02)
        self.assertAlmostEqual(
            after["statements"]["balance_sheet"]["check"],
            before["statements"]["balance_sheet"]["check"], delta=0.02)
        # AR aging: ยอดรวมเพิ่มเท่ายอดค้างรับ
        self.assertAlmostEqual(
            after["statements"]["ar_aging"]["total"]
            - before["statements"]["ar_aging"]["total"],
            move.amount_total * rate, delta=0.02)

    def test_fiscal_year_non_calendar(self):
        """ปีงบไม่ตรงปีปฏิทิน: ช่วงต้องเลื่อนตาม และงวดต้องเรียงตามปีงบจริง"""
        engine = self.env["biz.smart.finance.dashboard"].sudo()
        calendar_from, calendar_to = engine._fiscal_year(self.company, 2026)
        self.assertEqual(str(calendar_from), "2026-01-01")
        self.assertEqual(str(calendar_to), "2026-12-31")

        # ย้ายวันสิ้นปีงบเป็น 30 ก.ย. → FY2026 = 1 ต.ค. 2025 – 30 ก.ย. 2026
        other = self.env["res.company"].create({
            "name": "BSF FY Co",
            "fiscalyear_last_month": "9",
            "fiscalyear_last_day": 30,
        })
        fy_from, fy_to = engine._fiscal_year(other, 2026)
        self.assertEqual(str(fy_from), "2025-10-01")
        self.assertEqual(str(fy_to), "2026-09-30")

        periods = engine._fy_periods(fy_from, fy_to)
        self.assertEqual(len(periods), 12)
        self.assertEqual(str(periods[0]["date_to"]), "2025-10-31")
        self.assertEqual(str(periods[11]["date_to"]), "2026-09-30")
        # งวดต้องต่อกันสนิทไม่มีรูโหว่และไม่ทับกัน
        for previous, nxt in zip(periods, periods[1:]):
            self.assertEqual(
                (nxt["date_from"] - previous["date_to"]).days, 1)

    def test_filters_echo_currency_and_period(self):
        echo = self.payload["filters"]
        # สกุลที่ echo คือ **สกุลนำเสนอ** ซึ่งตั้งทับได้ที่ Settings —
        # ผูกกับสกุลของบริษัทตรง ๆ ไม่ได้ (ดู _presentation_currency)
        presentation = self.env[
            "biz.smart.finance.dashboard"].sudo()._presentation_currency(
                self.company)
        self.assertEqual(echo["currency"], presentation.name)
        self.assertTrue(echo["periods"])
        self.assertEqual(len(echo["periods"]), 12)
        self.assertTrue(echo["is_calendar_fy"])
        # as_of ต้องเป็นวันสุดท้ายของงวดที่เลือกเสมอ
        chosen = echo["periods"][echo["month"] - 1]
        self.assertEqual(chosen["date_to"], echo["as_of"])

    def test_fx_conversion_scales_group_totals(self):
        """บริษัทสกุลอื่นต้องถูกแปลงก่อนรวม ไม่ใช่บวกยอดดิบ"""
        engine = self.env["biz.smart.finance.dashboard"].sudo()
        thb = self.env.ref("base.THB")
        usd = self.env.ref("base.USD")
        if thb == self.company.currency_id:
            thb, usd = usd, thb
        rates = engine._fx_rates(
            [self.company.id], self.payload["filters"]["as_of"],
            self.company.currency_id)
        # บริษัทที่ใช้สกุลนำเสนออยู่แล้วต้องได้ตัวคูณ 1 เป๊ะ (ไม่ปัดเศษหาย)
        self.assertEqual(rates[self.company.id], 1.0)

        shared = {"fx": {self.company.id: 2.0}, "fx_prior": {}}
        self.assertAlmostEqual(
            engine._conv(shared, 150.0, self.company.id), 300.0)
        # บริษัทที่ไม่รู้จักต้องไม่ทำให้ยอดหาย (ตัวคูณ 1)
        self.assertAlmostEqual(engine._conv(shared, 150.0, 99999), 150.0)

    def test_controlling_shape_and_identity(self):
        co = self.payload["controlling"]
        self.assertIn("configured", co)
        self.assertTrue(co["plans"])
        if not co["configured"]:
            return
        for row in co["rows"]:
            # Available = งบ − ใช้จริง − ภาระผูกพัน (นิยามเดียวทั้งจอ)
            self.assertAlmostEqual(
                row["available"],
                row["budget"] - row["actual_cost"] - row["commitment"],
                places=1)
            self.assertAlmostEqual(
                row["actual_net"],
                row["actual_revenue"] - row["actual_cost"], places=1)
            self.assertEqual(
                row["over_budget"],
                bool(row["budget"]
                     and row["actual_cost"] + row["commitment"] > row["budget"]))
        # ต้นทุนต้องเป็นบวก (analytic amount ติดลบถูกกลับเครื่องหมายแล้ว)
        self.assertGreaterEqual(co["totals"]["actual_cost"], 0.0)

    def test_controlling_plan_switch_is_validated(self):
        engine = self.env["biz.smart.finance.dashboard"]
        plans = engine.sudo()._controlling_plans()
        self.assertTrue(plans, "dev DB ต้องมี analytic plan อย่างน้อยหนึ่ง")
        payload = self.engine.get_dashboard_data({
            "company_id": self.company.id, "plan_id": plans[-1].id,
        })
        self.assertEqual(payload["controlling"]["plan_id"], plans[-1].id)
        # แผนที่ไม่มีจริงต้องถูกปัดทิ้ง ไม่ใช่ระเบิด
        payload = self.engine.get_dashboard_data({
            "company_id": self.company.id, "plan_id": 987654321,
        })
        self.assertEqual(payload["filters"]["plan_id"], 0)

    def test_controlling_budget_and_commitment_flow(self):
        """งบที่อนุมัติแล้ว + PO ที่ยังไม่ตั้งบิล ต้องไหลเข้าศูนย์ต้นทุนจริง

        dev DB ไม่มีงบที่อนุมัติเลย (ทุกก้อนเป็น draft) เส้นทางนี้จึงต้องสร้าง
        ข้อมูลเองถึงจะพิสูจน์ได้ — ถ้าไม่ทำ เลข 0 จะดูเหมือนถูกทั้งที่อาจพัง
        """
        if "crossovered.budget.lines" not in self.env:
            self.skipTest("ไม่ได้ติดตั้ง om_account_budget")
        engine = self.env["biz.smart.finance.dashboard"].sudo()
        plans = engine._controlling_plans()
        plan = plans[:1]
        analytic = self.env["account.analytic.account"].create({
            "name": "BSF CC Test",
            "plan_id": plan.id,
            "company_id": self.company.id,
        })
        year = self.payload["filters"]["year"]
        budget = self.env["crossovered.budget"].create({
            "name": "BSF Test Budget",
            "date_from": "%s-01-01" % year,
            "date_to": "%s-12-31" % year,
            "company_id": self.company.id,
            "crossovered_budget_line": [(0, 0, {
                "analytic_account_id": analytic.id,
                # om ให้กรอกงบต้นทุนเป็นลบได้ — engine ต้อง abs() ให้
                "planned_amount": -120000.0,
                "date_from": "%s-01-01" % year,
                "date_to": "%s-12-31" % year,
            })],
        })
        budget.action_budget_confirm()
        budget.action_budget_validate()

        payload = self.engine.get_dashboard_data({
            "company_id": self.company.id, "plan_id": plan.id,
        })
        rows = {r["analytic_id"]: r for r in payload["controlling"]["rows"]}
        self.assertIn(analytic.id, rows, "ศูนย์ต้นทุนที่มีงบต้องปรากฏในตาราง")
        row = rows[analytic.id]
        # งบถูกแปลงเป็นสกุลนำเสนอเหมือนยอดอื่นทั้งจอ จึงต้องเทียบกับยอดที่คูณ
        # อัตราแล้ว ไม่ใช่ 120,000 ที่กรอกในสกุลของบริษัท
        rate = self._presentation_rate(self.payload["filters"]["as_of"])
        # งบทั้งปีถูกเฉลี่ยตามวันจนถึง as_of → ต้องน้อยกว่ายอดเต็มแต่มากกว่า 0
        self.assertGreater(row["budget"], 0.0)
        self.assertLess(row["budget"], 120000.0 * rate)
        self.assertAlmostEqual(
            row["available"],
            row["budget"] - row["actual_cost"] - row["commitment"], places=1)

        # ---- commitment จาก PO ที่ยืนยันแล้วยังไม่ตั้งบิล ----
        product = self.env["product.product"].create({
            "name": "BSF CC Service",
            "type": "service",
            "purchase_method": "purchase",
        })
        vendor = self.env["res.partner"].create({"name": "BSF CC Vendor"})
        order = self.env["purchase.order"].create({
            "partner_id": vendor.id,
            "company_id": self.company.id,
            "order_line": [(0, 0, {
                "product_id": product.id,
                "name": "งานทดสอบภาระผูกพัน",
                "product_qty": 10.0,
                "price_unit": 1000.0,
                "product_uom": product.uom_id.id,
                "date_planned": fields.Datetime.now(),
                # คีย์ต้องเป็น str — jsonb เก็บคีย์เป็นสตริงเสมอ
                "analytic_distribution": {str(analytic.id): 100.0},
            })],
        })
        order.button_confirm()

        after = self.engine.get_dashboard_data({
            "company_id": self.company.id, "plan_id": plan.id,
        })
        row_after = {
            r["analytic_id"]: r for r in after["controlling"]["rows"]
        }[analytic.id]
        self.assertAlmostEqual(
            row_after["commitment"], 10000.0 * rate, delta=0.02)
        self.assertAlmostEqual(
            row_after["available"],
            row_after["budget"] - row_after["actual_cost"] - 10000.0 * rate,
            places=1)

    # ------------------------------------------------------------------
    # Compare (BI)
    # ------------------------------------------------------------------
    def _compare(self, mode=None, count=None, **extra):
        filters = {"company_id": self.company.id}
        if mode is not None:
            filters["compare_mode"] = mode
        if count is not None:
            filters["compare_count"] = count
        filters.update(extra)
        return self.engine.get_dashboard_data(filters)

    def test_compare_default_off(self):
        """ไม่ส่งโหมดมา = ปิด และต้องไม่มีคอลัมน์ให้ consumer เดิมต้องรับมือ"""
        compare = self.payload["compare"]
        self.assertFalse(compare["enabled"])
        self.assertEqual(compare["columns"], [])
        self.assertEqual(compare["pnl_rows"], [])
        self.assertFalse(self.payload["filters"]["compare_mode"])

    def test_compare_month_windows(self):
        payload = self._compare("month", 3)
        compare = payload["compare"]
        columns = compare["columns"]
        self.assertTrue(compare["enabled"])
        self.assertEqual(len(columns), 3)
        # เรียงเก่า → ใหม่ และงวดต่อกันสนิท
        for previous, nxt in zip(columns, columns[1:]):
            self.assertLess(previous["date_to"], nxt["date_from"])
            self.assertEqual(
                (fields.Date.to_date(nxt["date_from"])
                 - fields.Date.to_date(previous["date_to"])).days, 1)
        # คอลัมน์ขวาสุดคืองวดที่เลือกใน toolbar
        self.assertEqual(columns[-1]["as_of"], payload["filters"]["as_of"])
        self.assertTrue(columns[-1]["is_current"])
        self.assertFalse(columns[0]["is_current"])
        # ทุกแถวมีค่าครบตามจำนวนคอลัมน์ และ delta ช่องแรกไม่มีฐานเทียบ
        for row in (compare["pnl_rows"] + compare["bs_rows"]
                    + compare["cf_rows"]):
            self.assertEqual(len(row["values"]), 3)
            self.assertEqual(len(row["delta_pct"]), 3)
            self.assertIsNone(row["delta_pct"][0])
        for row in compare["kpi_rows"]:
            self.assertEqual(len(row["values"]), 3)
        json.dumps(payload)

    def test_compare_pnl_waterfall(self):
        """แท็บ Compare ส่งบรรทัด waterfall ครบชุด และกระทบยอดทุกคอลัมน์"""
        compare = self._compare("quarter", 4)["compare"]
        rows = {r["key"]: r for r in compare["pnl_rows"]}
        self.assertEqual(
            [r["key"] for r in compare["pnl_rows"]],
            ["revenue_op", "cogs", "gross_op", "sga", "other_income",
             "ebitda", "depreciation", "ebit", "interest", "pretax",
             "tax", "net"])
        for col in range(4):
            val = {k: rows[k]["values"][col] for k in rows}
            self.assertAlmostEqual(
                val["gross_op"], val["revenue_op"] - val["cogs"], places=1)
            self.assertAlmostEqual(
                val["ebitda"],
                val["gross_op"] - val["sga"] + val["other_income"], places=1)
            self.assertAlmostEqual(
                val["ebit"], val["ebitda"] - val["depreciation"], places=1)
            self.assertAlmostEqual(
                val["pretax"], val["ebit"] - val["interest"], places=1)
            self.assertAlmostEqual(
                val["net"], val["pretax"] - val["tax"], places=1)

    def test_compare_bs_waterfall(self):
        """แท็บ Compare ส่งงบดุล waterfall — subtotal กระทบยอดทุกคอลัมน์"""
        compare = self._compare("quarter", 3)["compare"]
        rows = {r["key"]: r for r in compare["bs_rows"]}
        for k in ("total_ca", "total_nca", "total_assets", "total_cl",
                  "total_ncl", "total_liab", "total_equity", "total_liab_eq"):
            self.assertIn(k, rows)
        by_sec = {}
        for r in compare["bs_rows"]:
            if r["kind"] == "line":
                by_sec.setdefault(r["sec"], []).append(r)
        for col in range(3):
            def v(key):
                return rows[key]["values"][col]
            for sec, sub in (("ca", "total_ca"), ("nca", "total_nca"),
                             ("cl", "total_cl"), ("ncl", "total_ncl"),
                             ("eq", "total_equity")):
                self.assertAlmostEqual(
                    v(sub),
                    sum(r["values"][col] for r in by_sec.get(sec, [])),
                    places=1)
            self.assertAlmostEqual(
                v("total_assets"), v("total_ca") + v("total_nca"), places=1)
            self.assertAlmostEqual(
                v("total_liab_eq"),
                v("total_liab") + v("total_equity"), places=1)

    def test_compare_cf_waterfall(self):
        """แท็บ Compare ส่งงบกระแสเงินสด waterfall — subtotal กระทบยอดทุกคอลัมน์"""
        compare = self._compare("quarter", 3)["compare"]
        rows = {r["key"]: r for r in compare["cf_rows"]}
        self.assertEqual(
            [r["key"] for r in compare["cf_rows"] if r["kind"] == "subtotal"],
            ["total_cfo", "total_cfi", "total_cff", "net_change"])
        by_sec = {}
        for r in compare["cf_rows"]:
            if r["kind"] == "line":
                by_sec.setdefault(r["sec"], []).append(r)
        for col in range(3):
            def v(key):
                return rows[key]["values"][col]
            for sec, sub in (("cfo", "total_cfo"), ("cfi", "total_cfi"),
                             ("cff", "total_cff")):
                self.assertAlmostEqual(
                    v(sub),
                    sum(r["values"][col] for r in by_sec.get(sec, [])),
                    places=1)
            self.assertAlmostEqual(
                v("net_change"),
                v("total_cfo") + v("total_cfi") + v("total_cff"), places=1)

    def test_compare_clamping(self):
        self.assertEqual(self._compare("month", 99)["filters"]["compare_count"], 6)
        self.assertEqual(len(self._compare("month", 99)["compare"]["columns"]), 6)
        self.assertEqual(self._compare("month", 1)["filters"]["compare_count"], 2)
        # โหมดที่ไม่รู้จักต้องกลายเป็นปิด ไม่ใช่ระเบิด
        bogus = self._compare("bogus", 3)
        self.assertFalse(bogus["compare"]["enabled"])
        self.assertEqual(bogus["filters"]["compare_mode"], "")

    def _presentation_rate(self, as_of):
        """ตัวคูณสกุลบริษัท → สกุลนำเสนอ ณ วันสิ้นคอลัมน์

        DB ที่ใช้รันอาจตั้งสกุลนำเสนอไว้คนละสกุลกับบริษัท (เช่น USD → THB)
        เทสจึงต้องเทียบยอดที่แปลงแล้ว ไม่ใช่ยอดหน้าใบแจ้งหนี้ดิบ
        """
        engine = self.env["biz.smart.finance.dashboard"].sudo()
        presentation = engine._presentation_currency(self.company)
        return engine._fx_rates(
            [self.company.id], fields.Date.to_date(as_of),
            presentation)[self.company.id]

    def test_compare_delta_invoice(self):
        """ยอดที่โพสต์ในงวดปัจจุบันต้องเข้าคอลัมน์ขวาสุดคอลัมน์เดียว"""
        before = self._compare("month", 3)
        income = self.env["account.account"].search([
            ("account_type", "=", "income"),
            ("company_id", "=", self.company.id),
            ("deprecated", "=", False),
        ], limit=1)
        partner = self.env["res.partner"].create(
            {"name": "BSF Compare Customer", "company_id": self.company.id})
        move = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": partner.id,
            "company_id": self.company.id,
            "invoice_date": fields.Date.context_today(self.env.user),
            "invoice_line_ids": [(0, 0, {
                "name": "งานทดสอบเปรียบเทียบ",
                "quantity": 1,
                "price_unit": 70000.0,
                "account_id": income.id,
                "tax_ids": [(6, 0, [])],
            })],
        })
        move.action_post()
        after = self._compare("month", 3)

        def revenue(payload):
            row = next(r for r in payload["compare"]["pnl_rows"]
                       if r["key"] == "revenue_op")
            return row["values"]

        rate = self._presentation_rate(
            after["compare"]["columns"][-1]["as_of"])
        before_values, after_values = revenue(before), revenue(after)
        self.assertAlmostEqual(
            after_values[-1] - before_values[-1], 70000.0 * rate, delta=0.02)
        for index in range(len(before_values) - 1):
            self.assertAlmostEqual(
                after_values[index], before_values[index], delta=0.02)
        # ลูกหนี้ (ยอดสะสม) ต้องเพิ่มเท่ายอดรวมใบแจ้งหนี้ในคอลัมน์ขวาสุด
        def ar(payload):
            return next(r for r in payload["compare"]["bs_rows"]
                        if r["key"] == "asset_receivable")["values"][-1]
        self.assertAlmostEqual(
            ar(after) - ar(before), move.amount_total * rate, delta=0.02)

    def test_compare_year_mode_is_fytd(self):
        payload = self._compare("year", 2)
        columns = payload["compare"]["columns"]
        echo = payload["filters"]
        self.assertEqual(len(columns), 2)
        # คอลัมน์ล่าสุด = FYTD ของปีที่เลือก (ต้นปีงบ → as_of)
        self.assertEqual(columns[-1]["date_from"], echo["fy_start"])
        self.assertEqual(columns[-1]["date_to"], echo["as_of"])
        self.assertEqual(columns[-2]["date_to"], echo["as_of_prior"])
        # อัตราส่วนต้องเป็น None (คำนวณไม่ได้) ไม่ใช่ 0 เมื่อคอลัมน์ไม่มีรายได้
        revenue = next(r for r in payload["compare"]["pnl_rows"]
                       if r["key"] == "revenue_op")["values"]
        gp = next(r for r in payload["compare"]["kpi_rows"]
                  if r["key"] == "gp_pct")["values"]
        for value, ratio in zip(revenue, gp):
            if not value:
                self.assertIsNone(ratio)

    def test_compare_windows_non_calendar_fy(self):
        """ปีงบสิ้นสุด ก.ย.: เดือนถอยข้ามปีงบ และไตรมาสเริ่มที่ ต.ค."""
        engine = self.env["biz.smart.finance.dashboard"].sudo()
        other = self.env["res.company"].create({
            "name": "BSF Compare FY Co",
            "fiscalyear_last_month": "9",
            "fiscalyear_last_day": 30,
        })
        base = {
            "anchor_company": other,
            "year": 2026,
            "month": 1,                       # P1 = ต.ค. 2025
            "as_of": fields.Date.to_date("2025-10-31"),
        }
        months = engine._compare_windows(
            dict(base, compare_mode="month", compare_count=3))
        self.assertEqual(
            [str(col["date_from"]) for col in months],
            ["2025-08-01", "2025-09-01", "2025-10-01"])
        self.assertTrue(months[-1]["is_current"])

        quarters = engine._compare_windows(
            dict(base, compare_mode="quarter", compare_count=2))
        # ไตรมาสปัจจุบันเริ่ม 1 ต.ค. แต่ยังไม่ครบ — ต้องถูกตัดที่ as_of
        self.assertEqual(str(quarters[-1]["date_from"]), "2025-10-01")
        self.assertEqual(str(quarters[-1]["date_to"]), "2025-10-31")
        self.assertTrue(quarters[-1]["partial"])
        # ไตรมาสก่อนหน้าเป็นไตรมาสสุดท้ายของปีงบก่อน (ก.ค.–ก.ย. 2025)
        self.assertEqual(str(quarters[0]["date_from"]), "2025-07-01")
        self.assertEqual(str(quarters[0]["date_to"]), "2025-09-30")
        self.assertFalse(quarters[0]["partial"])

    def test_compare_no_column_beyond_as_of(self):
        for mode in ("month", "quarter", "year"):
            payload = self._compare(mode, 4)
            as_of = payload["filters"]["as_of"]
            for col in payload["compare"]["columns"]:
                self.assertLessEqual(col["date_to"], as_of)
                self.assertLessEqual(col["date_from"], col["date_to"])

    def test_company_scope_not_leaked(self):
        other = self.env["res.company"].create({"name": "BSF Other Co"})
        # res.company.create ผูกบริษัทใหม่ให้ user ปัจจุบันอัตโนมัติ — ต้องถอด
        # ออกจาก viewer ก่อน ไม่งั้นเทสนี้ไม่มีความหมาย
        self.viewer.write({"company_ids": [(6, 0, [self.company.id])]})
        payload = self.engine.get_dashboard_data({"company_id": other.id})
        self.assertNotEqual(payload["filters"]["company_id"], other.id)
        listed = {c["id"] for c in payload["filters"]["companies"]}
        self.assertNotIn(other.id, listed)

    # ------------------------------------------------------------------
    # เครื่องยนต์สไลซ์บาง (ใช้โดยตัวกรอง Controlling / Compare และ cron)
    # ------------------------------------------------------------------
    def _slice_cases(self):
        return [
            ("controlling", "get_controlling_data"),
            ("compare", "get_compare_data"),
            ("forecast", "get_forecast_data"),
        ]

    def test_thin_endpoints_match_full_payload(self):
        """สไลซ์บางต้องให้ตัวเลข **เท่ากันเป๊ะ** กับ payload เต็ม

        ถ้าไม่เท่า แปลว่ามีอะไรใน `_build_*` ที่พึ่งคีย์ใน shared ที่ builder
        ตัวอื่นเขียนไว้ — จอจะบอกตัวเลขคนละตัวตอนผู้ใช้กดตัวกรองของแท็บนั้น
        """
        for filters in ({"company_id": self.company.id},
                        {"company_id": self.company.id,
                         "compare_mode": "month", "compare_count": 6}):
            full = self.engine.get_dashboard_data(filters)
            for key, method in self._slice_cases():
                thin = getattr(self.engine, method)(filters)
                self.assertEqual(
                    json.dumps(full[key], sort_keys=True, default=str),
                    json.dumps(thin[key], sort_keys=True, default=str),
                    "สไลซ์ %s ไม่ตรงกับ payload เต็ม (filters=%s)"
                    % (key, filters),
                )

    def test_thin_endpoints_are_cheaper(self):
        """กันถดถอย: สไลซ์บางต้องยิงคิวรีน้อยกว่า payload เต็มเสมอ

        assert แบบ "น้อยกว่า" ไม่ใช่ตัวเลขตายตัว เพราะจำนวนคิวรีขึ้นกับข้อมูล
        จริงใน dev DB ที่เปลี่ยนได้ระหว่างงาน (บทเรียนจากเทสชุด AI)
        """
        filters = {"company_id": self.company.id,
                   "compare_mode": "month", "compare_count": 6}

        def count(fn):
            self.env.invalidate_all()
            before = self.env.cr.sql_log_count
            fn()
            return self.env.cr.sql_log_count - before

        full = count(lambda: self.engine.get_dashboard_data(filters))
        for key, method in self._slice_cases():
            thin = count(lambda: getattr(self.engine, method)(filters))
            self.assertLess(
                thin, full,
                "%s ใช้ %s คิวรี ไม่น้อยกว่า payload เต็ม (%s) — "
                "สไลซ์บางไม่ได้บางจริง" % (key, thin, full))

    def test_auto_alerts_computed_once(self):
        """`_auto_alerts` ถูกเรียกจาก Overview และ Risk — ต้องคิดรอบเดียว

        และผู้เรียกต้องได้ **สำเนา** เพราะ `_top_risks` ต่อท้ายแล้วเรียงลิสต์
        ที่ได้ ถ้าคืนตัวเดียวกันแท็บ Risk จะเห็นรายการที่ถูกแก้ไปแล้ว
        """
        engine = self.env["biz.smart.finance.dashboard"].sudo()
        f = engine._normalize_filters({"company_id": self.company.id})
        shared = engine._build_shared(f)
        shared["cash_forecast"] = engine._build_cash_forecast(f, shared)
        engine._build_inventory(f, shared)
        engine._build_margin(f, shared)
        first = engine._auto_alerts(f, shared)
        second = engine._auto_alerts(f, shared)
        self.assertEqual(first, second)
        self.assertIsNot(first, second, "ต้องคืนสำเนา ไม่ใช่ลิสต์ตัวเดียวกัน")
        first.append({"name": "ปนเปื้อน"})
        self.assertNotIn(
            {"name": "ปนเปื้อน"}, engine._auto_alerts(f, shared),
            "ผู้เรียกแก้ลิสต์ที่ได้แล้วไปกระทบ memo")

    def test_week_index_matches_grid(self):
        """`_week_index` แบบคำนวณตรงต้องให้ผลเท่าการสแกนกริดทุกวัน"""
        engine = self.env["biz.smart.finance.dashboard"].sudo()
        today = fields.Date.context_today(engine)
        weeks = engine._week_grid(today)

        def scan(day):
            if not day:
                return 0
            if day <= weeks[0]["_to"]:
                return 0
            for week in weeks[1:]:
                if week["_from"] <= day <= week["_to"]:
                    return week["index"]
            return None

        start = weeks[0]["_from"] - timedelta(days=20)
        for offset in range((weeks[-1]["_to"] - start).days + 20):
            day = start + timedelta(days=offset)
            self.assertEqual(engine._week_index(weeks, day), scan(day), str(day))
        self.assertEqual(engine._week_index(weeks, False), 0)
