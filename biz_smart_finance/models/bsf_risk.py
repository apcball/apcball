# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class BsfRisk(models.Model):
    """Risk Register ของฝ่ายการเงิน — ป้อนความเสี่ยงพร้อม impact/likelihood
    แล้วขึ้น Risk Radar / Top Risks ให้อัตโนมัติ"""

    _name = "biz.smart.finance.risk"
    _description = "Smart Finance Risk Register"
    _order = "score desc, id"

    name = fields.Char(string="ความเสี่ยง", required=True)
    company_id = fields.Many2one(
        "res.company", string="บริษัท", required=True, index=True,
        default=lambda self: self.env.company,
    )
    project_id = fields.Many2one(
        "project.project", string="โครงการ", index=True,
        domain="[('company_id', '=', company_id)]",
    )
    category = fields.Selection(
        [
            ("cash", "สภาพคล่อง"),
            ("margin", "กำไรโครงการ"),
            ("ar", "ลูกหนี้/เก็บเงิน"),
            ("fx", "อัตราแลกเปลี่ยน"),
            ("operation", "ปฏิบัติการ"),
            ("other", "อื่น ๆ"),
        ],
        string="หมวด", required=True, default="other",
    )
    impact = fields.Integer(string="Impact (1-5)", required=True, default=3)
    likelihood = fields.Integer(string="Likelihood (1-5)", required=True, default=3)
    score = fields.Integer(
        string="Risk Score", compute="_compute_score", store=True,
    )
    level = fields.Selection(
        [("low", "Low"), ("medium", "Medium"), ("high", "High")],
        string="ระดับ", compute="_compute_score", store=True,
    )
    currency_id = fields.Many2one(
        "res.currency", related="company_id.currency_id", readonly=True,
    )
    financial_impact = fields.Monetary(
        string="ผลกระทบทางการเงิน", currency_field="currency_id",
        help="ยอดเงินที่คาดว่าจะเสียไปถ้าความเสี่ยงนี้เกิดจริง — "
             "ใช้จัดลำดับความสำคัญในตาราง Early-Warning ของ CFO Cockpit",
    )
    action_status = fields.Selection(
        [
            ("not_started", "ยังไม่เริ่ม"),
            ("in_progress", "กำลังดำเนินการ"),
            ("at_risk", "เสี่ยงพลาดเป้า"),
            ("done", "เสร็จแล้ว"),
        ],
        string="สถานะแผนรับมือ", required=True, default="not_started",
        help="ความคืบหน้าของ 'แผนรับมือ' ไม่ใช่สถานะของตัวความเสี่ยง "
             "(ตัวความเสี่ยงใช้ฟิลด์ สถานะ: เปิด/ควบคุมแล้ว/ปิด)",
    )
    early_warning = fields.Char(
        string="Early-Warning Indicator",
        help="สัญญาณเตือนล่วงหน้าที่ต้องเฝ้าดู เช่น 'AR > 60 วันเพิ่มขึ้น 2 เดือนติด'",
    )
    action = fields.Char(string="แผนรับมือ")
    action_owner_id = fields.Many2one("res.users", string="ผู้รับผิดชอบ")
    target_date = fields.Date(string="กำหนดเสร็จ")
    state = fields.Selection(
        [("open", "เปิด"), ("mitigated", "ควบคุมแล้ว"), ("closed", "ปิด")],
        string="สถานะ", required=True, default="open", index=True,
    )
    trend = fields.Selection(
        [("up", "แย่ลง"), ("flat", "ทรงตัว"), ("down", "ดีขึ้น")],
        string="แนวโน้ม", default="flat",
    )

    @api.depends("impact", "likelihood")
    def _compute_score(self):
        for risk in self:
            risk.score = (risk.impact or 0) * (risk.likelihood or 0)
            if risk.score >= 15:
                risk.level = "high"
            elif risk.score >= 8:
                risk.level = "medium"
            else:
                risk.level = "low"

    @api.constrains("impact", "likelihood")
    def _check_scale(self):
        for risk in self:
            if not (1 <= risk.impact <= 5 and 1 <= risk.likelihood <= 5):
                raise ValidationError("Impact และ Likelihood ต้องอยู่ระหว่าง 1 ถึง 5")
