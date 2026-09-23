# -*- coding: utf-8 -*-
"""ตั้งค่ารายงานอายุสินค้าคงเหลือ — หนึ่งแถวต่อบริษัท

ขอบช่วงอายุ เกณฑ์สถานะ และจำนวนเดือนที่ใช้คำนวณ "ใช้เฉลี่ยต่อเดือน" เป็นนโยบายของ
แต่ละบริษัท ไม่ใช่ตัวเลือกที่ผู้ใช้เปลี่ยนไปมาบนจอ — เปลี่ยนที่นี่ที่เดียวแล้วทุกช่องทาง
(จอ / PDF / Excel) ใช้ค่าเดียวกัน
"""

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

DEFAULT_EDGES = (30, 60, 90, 180, 365)


class StockAgingConfig(models.Model):
    _name = "biz.stock.aging.config"
    _description = "Stock Aging Settings (ตั้งค่าอายุสินค้าคงเหลือ)"
    _rec_name = "company_id"

    company_id = fields.Many2one(
        "res.company", string="บริษัท", required=True, index=True,
        default=lambda self: self.env.company,
    )
    bucket_1 = fields.Integer(string="ช่วงที่ 1 ถึง (วัน)", default=30, required=True)
    bucket_2 = fields.Integer(string="ช่วงที่ 2 ถึง (วัน)", default=60, required=True)
    bucket_3 = fields.Integer(string="ช่วงที่ 3 ถึง (วัน)", default=90, required=True)
    bucket_4 = fields.Integer(string="ช่วงที่ 4 ถึง (วัน)", default=180, required=True)
    bucket_5 = fields.Integer(string="ช่วงที่ 5 ถึง (วัน)", default=365, required=True,
                              help="ช่วงที่ 6 คือทุกอย่างที่เก่ากว่านี้")
    usage_months = fields.Integer(
        string="เดือนที่ใช้คำนวณการใช้เฉลี่ย", default=6, required=True,
        help="ใช้เฉลี่ย/เดือน = จำนวนที่จ่ายออกจากบริษัทในช่วงนี้ ÷ จำนวนเดือน",
    )
    slow_mos_months = fields.Float(
        string="ช้า เมื่อ MOS เกิน (เดือน)", default=6.0, required=True,
        help="MOS = คงเหลือ ÷ ใช้เฉลี่ยต่อเดือน",
    )
    non_moving_days = fields.Integer(
        string="ไม่เคลื่อนไหว เมื่อไม่จ่ายเกิน (วัน)", default=90, required=True,
    )
    obsolete_days = fields.Integer(
        string="ตาย (Obsolete) เมื่อไม่จ่ายเกิน (วัน)", default=365, required=True,
    )

    _sql_constraints = [
        ("company_uniq", "unique(company_id)", "ตั้งค่าอายุสินค้าได้บริษัทละหนึ่งชุดเท่านั้น"),
    ]

    @api.constrains("bucket_1", "bucket_2", "bucket_3", "bucket_4", "bucket_5")
    def _check_edges(self):
        for config in self:
            edges = config.edges()
            if edges[0] <= 0 or any(b >= a for b, a in zip(edges, edges[1:])):
                raise ValidationError(_(
                    "ขอบช่วงอายุต้องเป็นจำนวนวันบวกและเพิ่มขึ้นตามลำดับ (เช่น 30 < 60 < 90 < 180 < 365)"
                ))

    @api.constrains("usage_months", "slow_mos_months", "non_moving_days", "obsolete_days")
    def _check_thresholds(self):
        for config in self:
            if not 1 <= config.usage_months <= 36:
                raise ValidationError(_("เดือนที่ใช้คำนวณการใช้เฉลี่ยต้องอยู่ระหว่าง 1 ถึง 36"))
            if config.slow_mos_months <= 0:
                raise ValidationError(_("เกณฑ์ MOS ต้องมากกว่าศูนย์"))
            if config.non_moving_days <= 0 or config.obsolete_days <= config.non_moving_days:
                raise ValidationError(_(
                    "เกณฑ์ 'ไม่เคลื่อนไหว' ต้องมากกว่าศูนย์ และเกณฑ์ 'ตาย' ต้องมากกว่าเกณฑ์ 'ไม่เคลื่อนไหว'"
                ))

    def edges(self):
        self.ensure_one()
        return [self.bucket_1, self.bucket_2, self.bucket_3, self.bucket_4, self.bucket_5]

    @api.model
    def get_for_company(self, company_id):
        """แถวตั้งค่าของบริษัท — สร้างค่าตั้งต้นให้ถ้ายังไม่มี (idempotent)

        อ่านผ่าน sudo เพราะรายงานเปิดได้โดย stock user ซึ่งไม่มีสิทธิ์สร้าง
        แต่ต้องได้ค่าตั้งต้นชุดเดียวกับที่ผู้จัดการจะเห็นในฟอร์ม
        """
        config = self.sudo().search([("company_id", "=", company_id)], limit=1)
        if not config:
            config = self.sudo().create({"company_id": company_id})
        return config

    def to_options(self):
        self.ensure_one()
        return {
            "bucket_edges": self.edges(),
            "usage_months": self.usage_months,
            "slow_mos_months": self.slow_mos_months,
            "non_moving_days": self.non_moving_days,
            "obsolete_days": self.obsolete_days,
        }
