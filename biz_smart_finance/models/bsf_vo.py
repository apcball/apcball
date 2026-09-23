# -*- coding: utf-8 -*-
from odoo import fields, models


class BsfVariationOrder(models.Model):
    """ทะเบียนงานเพิ่ม/ลด (Variation Order) กับผลกระทบต่อ margin —
    กรอกมือจนกว่าจะมีเอกสาร VO จริงในระบบ"""

    _name = "biz.smart.finance.vo"
    _description = "Smart Finance Variation Order Register"
    _order = "date desc, id desc"

    name = fields.Char(string="รายการ VO", required=True)
    project_id = fields.Many2one(
        "project.project", string="โครงการ", required=True, index=True,
    )
    company_id = fields.Many2one(
        related="project_id.company_id", store=True, readonly=True, index=True,
    )
    currency_id = fields.Many2one(
        related="company_id.currency_id", store=True, readonly=True,
    )
    amount = fields.Monetary(
        string="มูลค่า VO", currency_field="currency_id",
        help="งานเพิ่มเป็นบวก งานลดเป็นลบ",
    )
    margin_impact = fields.Monetary(
        string="ผลต่อกำไร", currency_field="currency_id",
        help="ผลกระทบสุทธิต่อกำไรโครงการ (บวก = ดีขึ้น)",
    )
    state = fields.Selection(
        [("pending", "รออนุมัติ"), ("approved", "อนุมัติแล้ว"), ("rejected", "ตกไป")],
        string="สถานะ", required=True, default="pending", index=True,
    )
    date = fields.Date(
        string="วันที่", default=fields.Date.context_today,
    )
