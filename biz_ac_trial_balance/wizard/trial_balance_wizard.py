# -*- coding: utf-8 -*-
"""ตัวช่วยตั้งค่าและสั่งพิมพ์งบทดลอง

Wizard นี้เป็นแค่ "หน้ากรอกตัวกรอง" เท่านั้น ตัวเลขทุกตัวมาจาก
``biz.trial.balance.report.get_report_data()`` ที่เดียว — ทั้งปุ่มบนหน้าจอ OWL และ
ปุ่มในไดอะล็อกนี้จบลงที่เมธอดเดียวกัน
"""

import base64

from odoo import _, api, fields, models


class TrialBalanceWizard(models.TransientModel):
    _name = "biz.trial.balance.wizard"
    _description = "Trial Balance Wizard (งบทดลอง)"

    company_ids = fields.Many2many(
        "res.company", string="บริษัท", required=True,
        default=lambda self: self.env.companies,
        help="ค่าตั้งต้นคือบริษัทที่เลือกอยู่ใน company switcher",
    )
    is_multi_company = fields.Boolean(
        compute="_compute_is_multi_company",
        help="ใช้ซ่อน/แสดงตัวเลือกโหมดงบหลายบริษัทในฟอร์มเท่านั้น",
    )
    company_mode = fields.Selection(
        [
            ("consolidated", "รวมทุกบริษัทเป็นงบเดียว"),
            ("split", "แยกแถวตามบริษัท"),
        ],
        string="งบหลายบริษัท", required=True, default="consolidated",
        help="รวม = บัญชีรหัสเดียวกันของทุกบริษัทยุบเป็นแถวเดียว / "
             "แยก = แต่ละบริษัทมีแถวบัญชีของตัวเอง",
    )
    date_from = fields.Date(
        string="ตั้งแต่วันที่", required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1),
    )
    date_to = fields.Date(
        string="ถึงวันที่", required=True,
        default=lambda self: fields.Date.context_today(self),
    )
    journal_ids = fields.Many2many(
        "account.journal", string="สมุดรายวัน",
        domain="[('company_id', 'in', company_ids)]",
        help="ว่างไว้ = ทุกสมุดรายวัน",
    )
    target_move = fields.Selection(
        [("posted", "เฉพาะรายการที่ผ่านรายการแล้ว"), ("all", "รวมรายการที่ยังไม่ผ่านรายการ")],
        string="สถานะรายการ", required=True, default="posted",
    )
    closing_mode = fields.Selection(
        [("before", "ก่อนปิดบัญชีรายได้-ค่าใช้จ่าย"), ("after", "หลังปิดบัญชีรายได้-ค่าใช้จ่าย")],
        string="แสดงข้อมูล", required=True, default="before",
    )
    opening_basis = fields.Selection(
        [
            ("fiscalyear", "ต้นปีบัญชี (บัญชีรายได้/ค่าใช้จ่ายเริ่มนับใหม่ทุกปี)"),
            ("inception", "ทุกรายการก่อนวันเริ่มงวด"),
        ],
        string="เกณฑ์ยอดยกมา", required=True, default="fiscalyear",
    )
    display_account = fields.Selection(
        [
            ("movement", "เฉพาะบัญชีที่มีความเคลื่อนไหว"),
            ("not_zero", "เฉพาะบัญชีที่ยอดไม่เป็นศูนย์"),
            ("all", "ทุกบัญชี"),
        ],
        string="แสดงบัญชี", required=True, default="movement",
    )
    group_by_type = fields.Boolean(string="จัดกลุ่มตามหมวดบัญชี", default=True)
    compare = fields.Selection(
        [("none", "ไม่เปรียบเทียบ"), ("previous_period", "งวดก่อน"), ("previous_year", "ปีก่อน")],
        string="เปรียบเทียบ", required=True, default="none",
    )
    date_format = fields.Selection(
        [("be", "พ.ศ."), ("ce", "ค.ศ.")], string="ปีที่แสดง", required=True, default="be",
    )
    analytic_account_ids = fields.Many2many("account.analytic.account", string="บัญชีวิเคราะห์")
    partner_ids = fields.Many2many("res.partner", string="คู่ค้า")

    xlsx_file = fields.Binary(string="ไฟล์ Excel", readonly=True, attachment=False)
    xlsx_filename = fields.Char(string="ชื่อไฟล์", readonly=True)

    @api.depends("company_ids")
    def _compute_is_multi_company(self):
        for wizard in self:
            wizard.is_multi_company = len(wizard.company_ids) > 1

    @api.onchange("company_ids")
    def _onchange_company_ids(self):
        """ตัดสมุดรายวันของบริษัทที่ถูกเอาออกไปแล้วทิ้ง ไม่งั้นตัวกรองจะค้างและกรองว่าง"""
        self.journal_ids = self.journal_ids.filtered(
            lambda j: j.company_id in self.company_ids
        )

    # ------------------------------------------------------------------
    # Options bridge
    # ------------------------------------------------------------------
    def _get_options(self):
        self.ensure_one()
        return self.env["biz.trial.balance.report"]._normalize_options({
            "company_ids": self.company_ids.ids,
            "company_mode": self.company_mode,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "journal_ids": self.journal_ids.ids,
            "analytic_account_ids": self.analytic_account_ids.ids,
            "partner_ids": self.partner_ids.ids,
            "target_move": self.target_move,
            "closing_mode": self.closing_mode,
            "opening_basis": self.opening_basis,
            "display_account": self.display_account,
            "group_by_type": self.group_by_type,
            "compare": self.compare,
            "date_format": self.date_format,
        })

    @api.model
    def _create_from_options(self, options):
        """สร้าง wizard ชั่วคราวจาก options ของหน้าจอ OWL เพื่อใช้เส้นทางพิมพ์เส้นเดียวกัน"""
        opt = self.env["biz.trial.balance.report"]._normalize_options(options)
        return self.create({
            "company_ids": [(6, 0, opt["company_ids"])],
            "company_mode": opt["company_mode"],
            "date_from": opt["date_from"],
            "date_to": opt["date_to"],
            "journal_ids": [(6, 0, opt["journal_ids"])],
            "analytic_account_ids": [(6, 0, opt["analytic_account_ids"])],
            "partner_ids": [(6, 0, opt["partner_ids"])],
            "target_move": opt["target_move"],
            "closing_mode": opt["closing_mode"],
            "opening_basis": opt["opening_basis"],
            "display_account": opt["display_account"],
            "group_by_type": opt["group_by_type"],
            "compare": opt["compare"],
            "date_format": opt["date_format"],
        })

    @api.model
    def action_export_from_options(self, options, output="pdf"):
        """เรียกจากปุ่ม "พิมพ์รายงาน" บนหน้าจอ OWL"""
        wizard = self._create_from_options(options)
        if output == "xlsx":
            return wizard.action_export_xlsx()
        return wizard.action_print_pdf()

    # ------------------------------------------------------------------
    # Buttons
    # ------------------------------------------------------------------
    def action_view_report(self):
        """เปิดหน้าจองบทดลองแบบ interactive ด้วยตัวกรองชุดนี้"""
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "biz_ac_trial_balance.action_trial_balance_screen"
        )
        action["context"] = {"tb_options": self._get_options()}
        return action

    def action_print_pdf(self):
        self.ensure_one()
        return self.env.ref("biz_ac_trial_balance.action_report_trial_balance").report_action(
            self, data={"options": self._get_options()}
        )

    def action_export_xlsx(self):
        self.ensure_one()
        options = self._get_options()
        content = self.env["biz.trial.balance.xlsx"].generate(options)
        filename = _("งบทดลอง_%s_%s.xlsx") % (options["date_from"], options["date_to"])
        self.write({
            "xlsx_file": base64.b64encode(content),
            "xlsx_filename": filename,
        })
        return {
            "type": "ir.actions.act_url",
            "url": (
                "/web/content/?model=biz.trial.balance.wizard&id=%s&field=xlsx_file"
                "&filename_field=xlsx_filename&download=true" % self.id
            ),
            "target": "self",
        }
