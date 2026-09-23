# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import float_compare


class BsfBillingPattern(models.Model):
    """แบบแผนการวางบิลของงานที่ยังไม่เซ็นสัญญา — บอกว่าเงินจะเข้ากี่ %
    ที่เดือนไหนนับจากเดือนที่เซ็น (0 = เดือนที่เซ็น)"""

    _name = "biz.smart.finance.billing.pattern"
    _description = "Smart Finance Billing Pattern"
    _order = "name"

    name = fields.Char(string="ชื่อแบบแผน", required=True)
    company_id = fields.Many2one(
        "res.company", string="บริษัท",
        help="เว้นว่าง = ใช้ได้ทุกบริษัท",
    )
    line_ids = fields.One2many(
        "biz.smart.finance.billing.pattern.line", "pattern_id",
        string="งวด", copy=True,
    )
    active = fields.Boolean(default=True)

    @api.constrains("line_ids")
    def _check_percent_total(self):
        for pattern in self:
            total = sum(pattern.line_ids.mapped("percent"))
            if float_compare(total, 100.0, precision_digits=2) != 0:
                raise ValidationError(
                    "แบบแผน '%s': ผลรวมเปอร์เซ็นต์ทุกงวดต้องเท่ากับ 100 "
                    "(ตอนนี้ %.2f)" % (pattern.name, total))

    def _schedule(self):
        """คืน [(offset_months, สัดส่วน 0–1)] เรียงตามงวด"""
        self.ensure_one()
        return [
            (line.offset_months, (line.percent or 0.0) / 100.0)
            for line in self.line_ids.sorted("offset_months")
        ]


class BsfBillingPatternLine(models.Model):
    _name = "biz.smart.finance.billing.pattern.line"
    _description = "Smart Finance Billing Pattern Line"
    _order = "offset_months, id"

    pattern_id = fields.Many2one(
        "biz.smart.finance.billing.pattern", string="แบบแผน",
        required=True, ondelete="cascade",
    )
    name = fields.Char(string="งวด")
    offset_months = fields.Integer(
        string="เดือนที่ (นับจากเซ็น)", required=True, default=0,
        help="0 = เดือนที่เซ็นสัญญา, 1 = เดือนถัดไป",
    )
    percent = fields.Float(string="เปอร์เซ็นต์", required=True)

    @api.constrains("offset_months", "percent")
    def _check_values(self):
        for line in self:
            if line.offset_months < 0:
                raise ValidationError("เดือนที่ต้องไม่ติดลบ")
            if line.percent <= 0:
                raise ValidationError("เปอร์เซ็นต์ของงวดต้องมากกว่า 0")
