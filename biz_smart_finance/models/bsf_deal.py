# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError

# ขั้นที่ยังไม่เซ็น = ยังเป็นแค่โอกาส จึงเข้ากริดแบบถ่วงน้ำหนักความน่าจะเป็น
OPEN_STAGES = ("lead", "proposal", "nego")


class BsfDeal(models.Model):
    """งานขายก่อนเซ็นสัญญา — ชั้นที่ 2 ของ Forecast

    ทีมขายเก็บดีลไว้นอกระบบ (Excel/LINE) ทำให้ forecast เห็นเฉพาะงานที่เซ็นแล้ว
    จอนี้คือที่กรอกดีลแบบเบาที่สุดที่ยังพยากรณ์ได้: มูลค่า × ความน่าจะเป็น
    กระจายตามแบบแผนวางบิลนับจากเดือนที่คาดว่าจะเซ็น

    **กติกากันนับซ้ำ:** พอดีลชนะ ต้องผูก `project_id` (constraint บังคับ) แล้ว
    engine จะเลิกนับดีลนี้ทันที เพราะมูลค่าย้ายไปอยู่ชั้นที่ 1 (แผนวางบิล/
    มูลค่างานตามสัญญาของโครงการจริง) แล้ว
    """

    _name = "biz.smart.finance.deal"
    _description = "Smart Finance Sales Deal (pipeline)"
    _order = "expected_sign_date, id"

    name = fields.Char(string="ชื่อดีล/โครงการ", required=True)
    company_id = fields.Many2one(
        "res.company", string="บริษัท", required=True, index=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        related="company_id.currency_id", store=True, readonly=True,
    )
    partner_id = fields.Many2one("res.partner", string="ลูกค้า")
    customer_name = fields.Char(
        string="ชื่อลูกค้า (ยังไม่มีในระบบ)",
        help="ใช้เมื่อยังไม่ได้สร้างผู้ติดต่อในระบบ",
    )
    amount = fields.Monetary(
        string="มูลค่าคาด (ก่อน VAT)", currency_field="currency_id", required=True,
    )
    probability = fields.Integer(
        string="ความน่าจะเป็น (%)", required=True, default=50,
    )
    stage = fields.Selection(
        [
            ("lead", "สนใจ"),
            ("proposal", "เสนอราคา"),
            ("nego", "ต่อรอง"),
            ("won", "ชนะ/เซ็นแล้ว"),
            ("lost", "แพ้/ยกเลิก"),
        ],
        string="ขั้น", required=True, default="lead", index=True,
    )
    expected_sign_date = fields.Date(string="คาดว่าจะเซ็น", required=True)
    duration_months = fields.Integer(
        string="ระยะเวลางาน (เดือน)", required=True, default=3,
    )
    billing_pattern_id = fields.Many2one(
        "biz.smart.finance.billing.pattern", string="แบบแผนวางบิล", required=True,
    )
    expected_margin_pct = fields.Float(
        string="กำไรขั้นต้นคาด (%)",
        help="เว้น 0 = ใช้ค่าตั้งต้นของบริษัทในหน้าตั้งค่า Smart Finance",
    )
    project_id = fields.Many2one(
        "project.project", string="โครงการที่เกิดขึ้นจริง",
        help="บังคับกรอกเมื่อดีลชนะ — เพื่อให้ระบบเลิกนับดีลนี้และไปนับ"
             "แผนวางบิลของโครงการจริงแทน (กันนับซ้ำ)",
    )
    sale_order_id = fields.Many2one("sale.order", string="ใบสั่งขาย")
    note = fields.Text(string="บันทึก")
    active = fields.Boolean(default=True)
    weighted_amount = fields.Monetary(
        string="มูลค่าถ่วงน้ำหนัก", currency_field="currency_id",
        compute="_compute_weighted_amount", store=True,
    )

    @api.depends("amount", "probability")
    def _compute_weighted_amount(self):
        for deal in self:
            deal.weighted_amount = (deal.amount or 0.0) * (
                min(max(deal.probability, 0), 100)) / 100.0

    @api.constrains("probability")
    def _check_probability(self):
        for deal in self:
            if not 0 <= deal.probability <= 100:
                raise ValidationError("ความน่าจะเป็นต้องอยู่ระหว่าง 0 ถึง 100")

    @api.constrains("amount")
    def _check_amount(self):
        for deal in self:
            if deal.amount <= 0:
                raise ValidationError("มูลค่าคาดต้องมากกว่า 0")

    @api.constrains("duration_months")
    def _check_duration(self):
        for deal in self:
            if deal.duration_months < 1:
                raise ValidationError("ระยะเวลางานต้องอย่างน้อย 1 เดือน")

    @api.constrains("stage", "project_id")
    def _check_won_project(self):
        for deal in self:
            if deal.stage == "won" and not deal.project_id:
                raise ValidationError(
                    "ดีล '%s' ชนะแล้วต้องผูกโครงการ — ไม่งั้นมูลค่าจะถูกนับซ้ำ "
                    "ทั้งจากดีลและจากแผนวางบิลของโครงการ" % deal.name)

    def _margin_pct(self, default_margin_pct):
        self.ensure_one()
        return self.expected_margin_pct or default_margin_pct

    def _phase(self, kind, collect_days=0, default_margin_pct=30.0,
               cost_lag_months=0):
        """กระจายมูลค่าถ่วงน้ำหนักของดีลนี้ลงบนไทม์ไลน์ — [(date, amount)]

        * ``cash_in``  — ตามแบบแผนวางบิล + วันเก็บเงินเฉลี่ยของบริษัท
        * ``revenue``  — รับรู้รายได้เฉลี่ยตลอดระยะเวลางาน
        * ``cost``     — ต้นทุนตามกำไรขั้นต้นที่คาด เลื่อนตาม cost_lag_months

        ยอดเป็น**สกุลของบริษัทดีล** — ผู้เรียกเป็นคนแปลงเป็นสกุลนำเสนอ
        """
        self.ensure_one()
        base = self.weighted_amount or 0.0
        start = self.expected_sign_date
        if not base or not start:
            return []
        months = max(self.duration_months or 1, 1)

        if kind == "cash_in":
            schedule = self.billing_pattern_id._schedule() if self.billing_pattern_id else []
            if not schedule:
                schedule = [(0, 1.0)]
            return [
                (start + relativedelta(months=offset, days=collect_days),
                 base * ratio)
                for offset, ratio in schedule
            ]

        if kind == "revenue":
            share = base / months
            return [
                (start + relativedelta(months=i), share) for i in range(months)
            ]

        if kind == "cost":
            margin = self._margin_pct(default_margin_pct)
            total_cost = base * max(100.0 - margin, 0.0) / 100.0
            share = total_cost / months
            return [
                (start + relativedelta(months=i + cost_lag_months), share)
                for i in range(months)
            ]

        return []
