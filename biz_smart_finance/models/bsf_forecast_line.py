# -*- coding: utf-8 -*-
import calendar
from datetime import date, timedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError

# ช่วงเปิดปลายที่ยาวเกินนี้ถือว่า "ไม่มีกำหนดจบ" — ดู `_amount_for_month`
MAX_OPEN_ENDED_YEARS = 5


class BsfForecastLine(models.Model):
    """รายการกระแสเงินสดที่ไม่ได้อยู่ในระบบเอกสาร (เงินเดือน ค่าเช่า ภาษี ฯลฯ)
    — engine กระจายลงกริด 13 สัปดาห์ของ Cash Forecast"""

    _name = "biz.smart.finance.forecast.line"
    _description = "Smart Finance Recurring Cash Flow Line"
    _order = "flow_type, category, id"

    name = fields.Char(string="รายการ", required=True)
    company_id = fields.Many2one(
        "res.company", string="บริษัท", required=True, index=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        related="company_id.currency_id", store=True, readonly=True,
    )
    flow_type = fields.Selection(
        [("in", "เงินเข้า"), ("out", "เงินออก")],
        string="ทิศทาง", required=True, default="out",
    )
    category = fields.Selection(
        [
            ("payroll", "เงินเดือน"),
            ("opex", "ค่าใช้จ่ายดำเนินงาน"),
            ("tax", "ภาษี"),
            ("other_out", "เงินออกอื่น"),
            ("other_in", "เงินเข้าอื่น"),
        ],
        string="หมวด", required=True, default="opex",
    )
    amount = fields.Monetary(
        string="จำนวนเงิน/งวด", currency_field="currency_id", required=True,
    )
    recurrence = fields.Selection(
        [("weekly", "รายสัปดาห์"), ("monthly", "รายเดือน"), ("once", "ครั้งเดียว")],
        string="ความถี่", required=True, default="monthly",
    )
    date = fields.Date(
        string="วันที่ (ครั้งเดียว)",
        help="ใช้เมื่อความถี่เป็น 'ครั้งเดียว'",
    )
    day_of_month = fields.Integer(
        string="วันที่ของเดือน", default=25,
        help="รายเดือน: เงินออก/เข้าวันที่เท่าไรของเดือน (เดือนสั้นจะเลื่อนมาวันสุดท้าย)",
    )
    date_start = fields.Date(string="เริ่มมีผล")
    date_end = fields.Date(string="สิ้นสุด")
    active = fields.Boolean(default=True)
    # ร่างที่ AI เสนอยังไม่เข้ากริด — ต้องให้คนอ่านเหตุผลแล้วกดยืนยันก่อน
    state = fields.Selection(
        [("draft", "ร่าง (AI เสนอ)"), ("confirmed", "ใช้งาน")],
        string="สถานะ", required=True, default="confirmed", index=True,
    )
    ai_note = fields.Char(
        string="เหตุผลที่ AI เสนอ", readonly=True,
        help="AI สรุปว่าเห็นอะไรในข้อมูลย้อนหลังถึงเสนอรายการนี้",
    )

    def action_confirm(self):
        self.write({"state": "confirmed"})

    @api.constrains("amount")
    def _check_amount(self):
        for line in self:
            if line.amount <= 0:
                raise ValidationError("จำนวนเงินต้องมากกว่า 0 (เลือกทิศทางที่ช่อง เงินเข้า/ออก)")

    @api.constrains("day_of_month")
    def _check_day_of_month(self):
        for line in self:
            if line.recurrence == "monthly" and not 1 <= line.day_of_month <= 31:
                raise ValidationError("วันที่ของเดือนต้องอยู่ระหว่าง 1 ถึง 31")

    @api.constrains("recurrence", "date")
    def _check_once_date(self):
        for line in self:
            if line.recurrence == "once" and not line.date:
                raise ValidationError("รายการแบบครั้งเดียวต้องระบุวันที่")

    def _in_bounds(self, day):
        self.ensure_one()
        if self.date_start and day < self.date_start:
            return False
        if self.date_end and day > self.date_end:
            return False
        return True

    def _amount_for_week(self, week_from, week_to):
        """ยอดของบรรทัดนี้ที่ตกในสัปดาห์ [week_from..week_to] (รวมปลายทั้งสอง)"""
        self.ensure_one()
        if self.recurrence == "once":
            if self.date and week_from <= self.date <= week_to and self._in_bounds(self.date):
                return self.amount
            return 0.0
        if self.recurrence == "weekly":
            # ยึดวันจันทร์ของสัปดาห์เป็นวันเกิดรายการ
            return self.amount if self._in_bounds(week_from) else 0.0
        # monthly: หา occurrence ของทุกเดือนที่คาบเกี่ยวสัปดาห์นี้
        total = 0.0
        cursor = week_from.replace(day=1)
        while cursor <= week_to:
            last_day = calendar.monthrange(cursor.year, cursor.month)[1]
            occurrence = cursor.replace(day=min(self.day_of_month, last_day))
            if week_from <= occurrence <= week_to and self._in_bounds(occurrence):
                total += self.amount
            cursor = (cursor + timedelta(days=last_day)).replace(day=1)
        return total

    def _amount_for_month(self, month_from, month_to):
        """ยอดของบรรทัดนี้ที่ตกในช่วง [month_from..month_to] (รวมปลายทั้งสอง)

        ใช้กับกริดรายเดือนของแท็บ Forecast — ช่วงอาจสั้นกว่าเดือนเต็มได้
        (bucket แรกเริ่มนับจากวันนี้) และยาวกว่าหนึ่งเดือนได้ (bucket ท้ายสุด
        ที่ดูดทุกอย่างเลย horizon) สูตรจึงต้องเดินตามวันจริง ไม่ใช่คูณจำนวนเดือน
        """
        self.ensure_one()
        if month_to < month_from:
            return 0.0
        if self.recurrence == "once":
            if self.date and month_from <= self.date <= month_to \
                    and self._in_bounds(self.date):
                return self.amount
            return 0.0
        # ช่วงที่เปิดปลาย (คอลัมน์ "หลังจากนี้" ของกริด) ต้องถูกปิดด้วยวันสิ้นสุด
        # ของบรรทัดเสมอ — รายการประจำที่ไม่มีวันจบคือ "จ่ายตลอดไป" การนับ
        # occurrence ไปจนสุดปฏิทินจึงไม่มีความหมายเชิงธุรกิจ (และวนเป็นแสนรอบ)
        if self.date_end:
            month_to = min(month_to, self.date_end)
        elif month_to.year > month_from.year + MAX_OPEN_ENDED_YEARS:
            return 0.0
        if month_to < month_from:
            return 0.0
        if self.recurrence == "weekly":
            # ยึดวันจันทร์เป็นวันเกิดรายการ เหมือนกริดรายสัปดาห์
            total = 0.0
            cursor = month_from - timedelta(days=month_from.weekday())
            if cursor < month_from:
                cursor += timedelta(days=7)
            while cursor <= month_to:
                if self._in_bounds(cursor):
                    total += self.amount
                cursor += timedelta(days=7)
            return total
        # monthly: หา occurrence ของทุกเดือนที่คาบเกี่ยวช่วงนี้
        # (เดินด้วยเลขปี/เดือน ไม่ใช่บวก timedelta — บวกวันที่ใกล้ date.max
        # ทำให้ OverflowError)
        total = 0.0
        year, month = month_from.year, month_from.month
        while (year, month) <= (month_to.year, month_to.month):
            last_day = calendar.monthrange(year, month)[1]
            occurrence = date(year, month, min(self.day_of_month, last_day))
            if month_from <= occurrence <= month_to and self._in_bounds(occurrence):
                total += self.amount
            month += 1
            if month > 12:
                month, year = 1, year + 1
        return total
