# -*- coding: utf-8 -*-
"""รายงาน CFO ประจำเดือนที่ AI เขียน — เก็บเป็น record เปิดย้อนดูได้.

`generate` เปิดให้ group_bsf_user เพราะอ่านเฉพาะข้อมูลที่ตัวเองเห็นผ่าน engine
อยู่แล้ว และเขียนเฉพาะ record ที่ตัวเองสร้าง (เขียนผ่าน sudo เพราะ ACL ฝั่ง
user ให้แค่ read+create — ตาม precedent finance.dashboard.report)"""
from odoo import _, api, fields, models
from odoo.exceptions import AccessError

MONTH_NAMES_TH = [
    "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
    "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม",
]


class BsfReport(models.Model):
    _name = "biz.smart.finance.report"
    _description = "Smart Finance AI CFO Report"
    _order = "create_date desc"

    name = fields.Char(string="ชื่อรายงาน", required=True)
    period = fields.Char(string="งวด")
    company_label = fields.Char(string="ขอบเขตบริษัท")
    year = fields.Integer(string="ปี")
    month = fields.Integer(string="เดือน")
    content = fields.Text(string="เนื้อหา (markdown)")
    state = fields.Selection(
        [("draft", "กำลังสร้าง"), ("done", "เสร็จ"), ("error", "ผิดพลาด")],
        string="สถานะ", required=True, default="draft",
    )
    error_message = fields.Text(string="สาเหตุที่ผิดพลาด")
    user_id = fields.Many2one(
        "res.users", string="ผู้สร้าง", required=True, index=True,
        default=lambda self: self.env.user,
    )
    company_id = fields.Many2one(
        "res.company", string="บริษัท",
        default=lambda self: self.env.company,
    )

    def _check_user(self):
        if self.env.su:
            return
        if not self.env.user.has_group("biz_smart_finance.group_bsf_user"):
            raise AccessError(_("ต้องเป็นสมาชิกกลุ่ม CFO Cockpit / Viewer"))

    @api.model
    def generate(self, filters=None):
        self._check_user()
        engine = self.env["biz.smart.finance.dashboard"]
        ai = self.env["biz.smart.finance.ai"]
        payload = engine.get_dashboard_data(filters or {})
        echo = payload["filters"]
        month_name = MONTH_NAMES_TH[(echo["month"] - 1) % 12]
        period = "%s %s" % (month_name, echo["year"])
        default_name = _("รายงาน CFO — %s — %s") % (
            period, echo["company_label"])
        report = self.create({
            "name": default_name,
            "period": period,
            "company_label": echo["company_label"],
            "year": echo["year"],
            "month": echo["month"],
            "company_id": echo.get("company_id") or self.env.company.id,
        })
        try:
            context = {"filters": None}
            for tab in ("overview", "cash", "forecast", "sales", "margin",
                        "ap", "risk"):
                compact = ai._compact(tab, payload)
                context["filters"] = compact.pop("filters")
                context.update(compact)
            parsed = ai.generate_report(context)
            report.sudo().write({
                "name": parsed.get("title") or default_name,
                "content": parsed.get("content") or "",
                "state": "done",
            })
        except Exception as exc:
            # ห้าม raise ต่อ — RPC ที่ raise จะ rollback ทั้ง transaction
            # แล้ว record สถานะ error ที่เพิ่งเขียนจะหายไปด้วย
            report.sudo().write({
                "state": "error",
                "error_message": str(exc),
            })
            return {
                "id": report.id,
                "name": report.name,
                "content": "",
                "state": "error",
                "error": str(exc),
            }
        return {
            "id": report.id,
            "name": report.name,
            "content": report.content,
            "state": report.state,
        }

    def get_content(self):
        self.ensure_one()
        self._check_user()
        return {
            "id": self.id, "name": self.name, "content": self.content or "",
            "state": self.state, "period": self.period or "",
        }

    @api.model
    def list_reports(self):
        self._check_user()
        reports = self.search([], limit=10)
        return [
            {"id": report.id, "name": report.name, "state": report.state,
             "period": report.period or "",
             "create_date": fields.Datetime.to_string(report.create_date),
             "user": report.user_id.name}
            for report in reports
        ]
