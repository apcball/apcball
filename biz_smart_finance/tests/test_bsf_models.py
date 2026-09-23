# -*- coding: utf-8 -*-
from datetime import date

from psycopg2 import IntegrityError

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger


class TestBsfModels(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company

    def test_config_unique_per_company(self):
        Config = self.env["biz.smart.finance.config"]
        Config.search([("company_id", "=", self.company.id)]).unlink()
        Config.create({"company_id": self.company.id})
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"):
            with self.env.cr.savepoint():
                Config.create({"company_id": self.company.id})

    def test_risk_score_level(self):
        risk = self.env["biz.smart.finance.risk"].create({
            "name": "ลูกค้ารายใหญ่จ่ายช้า",
            "impact": 4,
            "likelihood": 4,
        })
        self.assertEqual(risk.score, 16)
        self.assertEqual(risk.level, "high")
        risk.write({"likelihood": 2})
        self.assertEqual(risk.score, 8)
        self.assertEqual(risk.level, "medium")
        risk.write({"impact": 1, "likelihood": 2})
        self.assertEqual(risk.level, "low")

    def test_risk_scale_bounds(self):
        with self.assertRaises(ValidationError):
            self.env["biz.smart.finance.risk"].create({
                "name": "เกินสเกล", "impact": 6, "likelihood": 3,
            })

    def test_forecast_line_amount_for_week(self):
        Line = self.env["biz.smart.finance.forecast.line"]
        week_from = date(2026, 8, 24)  # จันทร์
        week_to = date(2026, 8, 30)

        weekly = Line.create({
            "name": "ค่าแรงรายสัปดาห์", "flow_type": "out",
            "category": "payroll", "amount": 100.0, "recurrence": "weekly",
        })
        self.assertEqual(weekly._amount_for_week(week_from, week_to), 100.0)

        monthly = Line.create({
            "name": "เงินเดือน", "flow_type": "out", "category": "payroll",
            "amount": 500.0, "recurrence": "monthly", "day_of_month": 25,
        })
        self.assertEqual(monthly._amount_for_week(week_from, week_to), 500.0)
        # สัปดาห์ที่ไม่มีวันที่ 25
        self.assertEqual(
            monthly._amount_for_week(date(2026, 8, 3), date(2026, 8, 9)), 0.0)

        # day 31 ในเดือนที่มี 30 วัน → เลื่อนมาวันสุดท้ายของเดือน
        clamp = Line.create({
            "name": "สิ้นเดือน", "flow_type": "out", "category": "opex",
            "amount": 70.0, "recurrence": "monthly", "day_of_month": 31,
        })
        self.assertEqual(
            clamp._amount_for_week(date(2026, 9, 28), date(2026, 10, 4)), 70.0)

        once = Line.create({
            "name": "ภาษีครึ่งปี", "flow_type": "out", "category": "tax",
            "amount": 900.0, "recurrence": "once", "date": date(2026, 8, 26),
        })
        self.assertEqual(once._amount_for_week(week_from, week_to), 900.0)
        self.assertEqual(
            once._amount_for_week(date(2026, 8, 31), date(2026, 9, 6)), 0.0)

        # ขอบเขต date_start/date_end ตัดรายการออก
        bounded = Line.create({
            "name": "ค่าเช่าหมดสัญญา", "flow_type": "out", "category": "opex",
            "amount": 40.0, "recurrence": "weekly",
            "date_end": date(2026, 8, 1),
        })
        self.assertEqual(bounded._amount_for_week(week_from, week_to), 0.0)

    def test_forecast_line_amount_positive(self):
        with self.assertRaises(ValidationError):
            self.env["biz.smart.finance.forecast.line"].create({
                "name": "ติดลบ", "flow_type": "out", "category": "opex",
                "amount": -5.0,
            })
