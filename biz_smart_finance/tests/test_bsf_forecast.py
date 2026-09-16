# -*- coding: utf-8 -*-
"""แท็บ Forecast — กริดรายเดือน, ดีล, กติกากันนับซ้ำ

กติกาของ repo นี้: DB ที่ใช้รันเป็น dev DB ที่มีข้อมูลจริงอยู่แล้ว จึงต้อง
assert เป็น **ส่วนต่าง** จาก baseline เสมอ และยอดเงินทุกตัวต้องคูณอัตรา
แลกเปลี่ยนจาก `_fx_rates` (สกุลนำเสนออาจไม่ใช่สกุลของบริษัท)
"""
from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestBsfForecastCommon(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.today = fields.Date.context_today(cls.env["res.company"])
        cls.engine = cls.env["biz.smart.finance.dashboard"]
        cls.pattern = cls.env["biz.smart.finance.billing.pattern"].create({
            "name": "ทดสอบ 50/50",
            "line_ids": [
                (0, 0, {"offset_months": 0, "percent": 50.0}),
                (0, 0, {"offset_months": 2, "percent": 50.0}),
            ],
        })

    def _rate(self, as_of):
        engine = self.engine.sudo()
        presentation = engine._presentation_currency(self.company)
        return engine._fx_rates(
            [self.company.id], fields.Date.to_date(as_of),
            presentation)[self.company.id]

    def _forecast(self):
        return self.engine.get_dashboard_data(
            {"company_id": self.company.id})["forecast"]


class TestBsfBillingPattern(TestBsfForecastCommon):
    def test_percent_must_total_100(self):
        Pattern = self.env["biz.smart.finance.billing.pattern"]
        with self.assertRaises(ValidationError):
            Pattern.create({
                "name": "ไม่ครบร้อย",
                "line_ids": [(0, 0, {"offset_months": 0, "percent": 60.0})],
            })

    def test_schedule_is_sorted(self):
        pattern = self.env["biz.smart.finance.billing.pattern"].create({
            "name": "เรียงสลับ",
            "line_ids": [
                (0, 0, {"offset_months": 3, "percent": 40.0}),
                (0, 0, {"offset_months": 0, "percent": 60.0}),
            ],
        })
        self.assertEqual(
            pattern._schedule(), [(0, 0.6), (3, 0.4)])


class TestBsfDeal(TestBsfForecastCommon):
    def _deal(self, **overrides):
        values = {
            "name": "ดีลทดสอบ",
            "company_id": self.company.id,
            "amount": 1000000.0,
            "probability": 40,
            "stage": "proposal",
            "expected_sign_date": self.today,
            "duration_months": 4,
            "billing_pattern_id": self.pattern.id,
            "expected_margin_pct": 25.0,
        }
        values.update(overrides)
        return self.env["biz.smart.finance.deal"].create(values)

    def test_weighted_amount(self):
        self.assertAlmostEqual(self._deal().weighted_amount, 400000.0, places=2)

    def test_probability_bounds(self):
        with self.assertRaises(ValidationError):
            self._deal(probability=140)

    def test_won_requires_project(self):
        deal = self._deal()
        with self.assertRaises(ValidationError):
            deal.stage = "won"

    def test_phase_cash_in_follows_pattern(self):
        deal = self._deal()
        phased = deal._phase("cash_in", collect_days=30)
        self.assertEqual(len(phased), 2)
        # ทุกบาทต้องลงงวดใดงวดหนึ่ง ไม่หายระหว่างกระจาย
        self.assertAlmostEqual(
            sum(amount for _day, amount in phased),
            deal.weighted_amount, places=2)
        self.assertEqual(phased[0][0], self.today + relativedelta(days=30))
        self.assertEqual(
            phased[1][0], self.today + relativedelta(months=2, days=30))

    def test_phase_revenue_and_cost(self):
        deal = self._deal()
        revenue = deal._phase("revenue")
        self.assertEqual(len(revenue), 4)
        self.assertAlmostEqual(
            sum(a for _d, a in revenue), deal.weighted_amount, places=2)
        cost = deal._phase("cost", default_margin_pct=90.0, cost_lag_months=1)
        # ดีลระบุ margin เอง (25%) → ต้องไม่ใช้ค่าตั้งต้นของบริษัท
        self.assertAlmostEqual(
            sum(a for _d, a in cost), deal.weighted_amount * 0.75, places=2)
        self.assertEqual(cost[0][0], self.today + relativedelta(months=1))

    def test_pipeline_stops_counting_once_won(self):
        before = self._forecast()["pipeline"]["totals"]
        deal = self._deal()
        during = self._forecast()["pipeline"]["totals"]
        rate = self._rate(self.today)
        self.assertEqual(during["count"], before["count"] + 1)
        self.assertAlmostEqual(
            during["weighted"] - before["weighted"],
            deal.weighted_amount * rate, delta=0.5)

        project = self.env["project.project"].create({
            "name": "โครงการจากดีลทดสอบ", "company_id": self.company.id,
        })
        deal.write({"stage": "won", "project_id": project.id})
        after = self._forecast()["pipeline"]["totals"]
        self.assertEqual(after["count"], before["count"])
        self.assertAlmostEqual(
            after["weighted"], before["weighted"], delta=0.5)


class TestBsfForecastEngine(TestBsfForecastCommon):
    def test_month_grid_has_tail_and_no_none_index(self):
        engine = self.engine.sudo()
        months = engine._month_grid(self.today, 12)
        self.assertEqual(len(months), 13)
        self.assertTrue(months[-1]["is_tail"])
        # เดือนแรกเริ่มนับจากวันนี้ (อดีตถือเป็น "ค้างมาถึงเดือนนี้")
        self.assertEqual(months[0]["_from"], self.today)
        self.assertEqual(
            engine._month_index(months, self.today - relativedelta(years=3)), 0)
        # เลย horizon ต้องตกคอลัมน์ท้าย ไม่ใช่ None (จุดที่กริดรายสัปดาห์ทำเงินหาย)
        self.assertEqual(
            engine._month_index(months, self.today + relativedelta(years=5)),
            months[-1]["index"])
        self.assertEqual(engine._month_index(months, False), 0)

    def test_spread_conserves_total(self):
        engine = self.engine.sudo()
        months = engine._month_grid(self.today, 12)
        series = [0.0] * len(months)
        engine._spread_months(
            months, series, 900000.0,
            self.today, self.today + relativedelta(months=8))
        self.assertAlmostEqual(sum(series), 900000.0, places=2)
        # ยาวเลยขอบกริด: ยังต้องครบ (ส่วนเกินไปกองที่คอลัมน์ท้าย)
        series = [0.0] * len(months)
        engine._spread_months(
            months, series, 500000.0,
            self.today, self.today + relativedelta(years=4))
        self.assertAlmostEqual(sum(series), 500000.0, places=2)
        self.assertGreater(series[-1], 0.0)

    def test_forecast_line_only_counts_when_confirmed(self):
        Line = self.env["biz.smart.finance.forecast.line"]
        before = self._forecast()["cash"]
        draft = Line.create({
            "name": "ร่าง AI ทดสอบ", "company_id": self.company.id,
            "flow_type": "out", "category": "opex",
            "amount": 250000.0, "recurrence": "monthly",
            "day_of_month": 15, "state": "draft",
        })
        during = self._forecast()["cash"]
        self.assertAlmostEqual(
            during["closing"][-1], before["closing"][-1], delta=0.5)
        draft.action_confirm()
        after = self._forecast()["cash"]
        self.assertLess(after["closing"][-1], before["closing"][-1])

    def test_amount_for_month(self):
        Line = self.env["biz.smart.finance.forecast.line"]
        line = Line.create({
            "name": "ค่าเช่าทดสอบ", "company_id": self.company.id,
            "flow_type": "out", "category": "opex",
            "amount": 30000.0, "recurrence": "monthly", "day_of_month": 10,
        })
        first = self.today.replace(day=1)
        last = (first + relativedelta(months=1)) - relativedelta(days=1)
        self.assertAlmostEqual(
            line._amount_for_month(first, last), 30000.0, places=2)
        # ช่วงยาวสองเดือน → สองงวด
        self.assertAlmostEqual(
            line._amount_for_month(
                first, (first + relativedelta(months=2)) - relativedelta(days=1)),
            60000.0, places=2)
        # ช่วงกลับหัว → 0 (คอลัมน์ท้ายของกริดอาจว่างได้)
        self.assertEqual(line._amount_for_month(last, first), 0.0)

    def test_pipeline_deal_reaches_cash_and_pnl(self):
        before = self._forecast()
        deal = self.env["biz.smart.finance.deal"].create({
            "name": "ดีลเข้ากริด", "company_id": self.company.id,
            "amount": 2000000.0, "probability": 50, "stage": "nego",
            "expected_sign_date": self.today + relativedelta(months=1),
            "duration_months": 3, "billing_pattern_id": self.pattern.id,
            "expected_margin_pct": 20.0,
        })
        after = self._forecast()
        rate = self._rate(self.today)
        weighted = deal.weighted_amount * rate
        self.assertAlmostEqual(
            sum(after["cash"]["rows"][i]["in_pipeline"]
                for i in range(len(after["months"])))
            - sum(before["cash"]["rows"][i]["in_pipeline"]
                  for i in range(len(before["months"]))),
            weighted, delta=1.0)
        self.assertAlmostEqual(
            sum(after["pnl"]["revenue_pipeline"])
            - sum(before["pnl"]["revenue_pipeline"]),
            weighted, delta=1.0)
        self.assertAlmostEqual(
            sum(after["pnl"]["cost_pipeline"])
            - sum(before["pnl"]["cost_pipeline"]),
            weighted * 0.8, delta=1.0)

    def test_payload_shape_and_closing_identity(self):
        forecast = self._forecast()
        months = forecast["months"]
        cash = forecast["cash"]
        self.assertEqual(len(months), forecast["horizon_months"] + 1)
        for key in ("inflow", "outflow", "net", "closing"):
            self.assertEqual(len(cash[key]), len(months))
        # เงินสดคงเหลือต้องเป็นผลสะสมของ net จริง ๆ
        running = cash["opening"]
        for index, month in enumerate(months):
            running += cash["net"][index]
            self.assertAlmostEqual(cash["closing"][index], running, delta=0.05)
        for key in ("revenue", "cost", "margin", "margin_pct"):
            self.assertEqual(len(forecast["pnl"][key]), len(months))

    def test_scenario_shift_does_not_lose_money(self):
        base = self.engine.get_dashboard_data(
            {"company_id": self.company.id, "scenario": "base"})["forecast"]
        stress = self.engine.get_dashboard_data(
            {"company_id": self.company.id, "scenario": "stress"})["forecast"]
        # เลื่อนเงินเข้าไม่ใช่ทำให้เงินเข้าหาย — ยอดรวมทั้งช่วงต้องเท่าเดิม
        self.assertAlmostEqual(
            sum(base["cash"]["inflow"]), sum(stress["cash"]["inflow"]),
            delta=1.0)
        self.assertAlmostEqual(
            base["cash"]["closing"][-1], stress["cash"]["closing"][-1],
            delta=1.0)

    def test_weekly_grid_untouched_by_refactor(self):
        """กริด 13 สัปดาห์ต้องคงรูปเดิมหลังแยก `_forecast_sources` ออกมา"""
        payload = self.engine.get_dashboard_data({"company_id": self.company.id})
        weekly = payload["cash"]["forecast"]
        self.assertEqual(len(weekly["weeks"]), 13)
        self.assertEqual(len(weekly["closing"]), 13)
        self.assertEqual(len(weekly["rows"]), 13)
        running = weekly["opening"]
        for row in weekly["rows"]:
            running += (row["inflow_collections"] + row["inflow_other"]
                        - row["outflow_ap"] - row["outflow_payroll_opex"]
                        - row["outflow_tax_other"])
            self.assertAlmostEqual(row["closing"], running, delta=0.05)


class TestBsfForecastSnapshot(TestBsfForecastCommon):
    def test_snapshot_is_idempotent_per_day(self):
        Snapshot = self.env["biz.smart.finance.forecast.snapshot"]
        Config = self.env["biz.smart.finance.config"]
        if not Config.search([("company_id", "=", self.company.id)]):
            Config.create({"company_id": self.company.id})
        Snapshot.search([("snapshot_date", "=", self.today)]).unlink()
        Snapshot.cron_snapshot()
        count = Snapshot.search_count([("snapshot_date", "=", self.today)])
        self.assertGreaterEqual(count, 1)
        Snapshot.cron_snapshot()
        self.assertEqual(
            Snapshot.search_count([("snapshot_date", "=", self.today)]), count)

    def test_snapshot_stores_kpis(self):
        forecast = self._forecast()
        values = self.env["biz.smart.finance.forecast.snapshot"]\
            ._values_from_forecast(self.company, self.today, forecast)
        self.assertAlmostEqual(
            values["kpi_revenue_12m"], sum(forecast["pnl"]["revenue"]),
            places=2)
        self.assertAlmostEqual(
            values["kpi_net_cash_low"], min(forecast["cash"]["closing"]),
            places=2)
