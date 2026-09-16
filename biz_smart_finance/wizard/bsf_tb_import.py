# -*- coding: utf-8 -*-
from odoo import api, fields, models

from odoo.addons.biz_smart_finance.models.bsf_ext_account import (
    ACCOUNT_TYPES,
    ACCOUNT_TYPE_SET,
)

# คอลัมน์ที่คาดหวังในไฟล์ (แถวแรกเป็น header ชื่อคอลัมน์ตามนี้ ตัวเล็ก):
#   code          รหัสบัญชีตามผังของระบบเดิม
#   name          ชื่อบัญชี (ใช้เฉพาะตอนสร้างบัญชีใหม่ — บัญชีเดิมไม่ทับชื่อ)
#   account_type  ประเภทบัญชีของ Odoo — เว้นว่างได้ถ้าบัญชีนี้เคยนำเข้าไว้แล้ว
#   opening       ยอดยกมาต้นงวด (เดบิต − เครดิต)
#   debit         เดบิตระหว่างงวด
#   credit        เครดิตระหว่างงวด
FILE_COLUMNS = ["code", "name", "account_type", "opening", "debit", "credit"]


class BsfTbImport(models.TransientModel):
    """นำเข้า Trial Balance หนึ่งงวด (หนึ่งเดือน) จากไฟล์ CSV/XLSX ของระบบเดิม

    รูปแบบเดียวกับ `biz.smart.finance.fact.import`/`doc.import` ทุกประการ:
    อัปโหลด → `action_preview()` (ตรวจทีละแถว ไม่บล็อกทั้งไฟล์เมื่อเจอบัญชีใหม่
    ที่ยังไม่มีในผังภายนอก) → แก้ในตารางตัวอย่างได้ → `action_import()` เขียนผ่าน
    `ext.gl.upsert_tb()` เป็น**ร่าง** เสมอ (post เองทีหลังหลังตรวจว่าดุลจริง)"""

    _name = "biz.smart.finance.tb.import"
    _inherit = ["biz.smart.finance.import.mixin"]
    _description = "Smart Finance — Import Trial Balance"

    date_from = fields.Date(
        string="วันแรกของงวด", required=True,
        help="ระบุช่วงวันที่ให้ตรงกับ Trial Balance ของระบบเดิม",
    )
    date_to = fields.Date(string="วันสุดท้ายของงวด", required=True)
    replace_existing = fields.Boolean(
        string="แทนที่ Trial Balance เดิมของงวดนี้", default=True,
        help="ลบหัวเอกสารเดิมของ (บริษัท, งวด) นี้ทั้งชุดก่อนสร้างใหม่ "
             "(ถ้าเดิม posted อยู่แล้วจะถูกลบด้วย — ยืนยันแล้วต้อง Post ใหม่)",
    )
    line_ids = fields.One2many(
        "biz.smart.finance.tb.import.line", "wizard_id",
        string="ตัวอย่างข้อมูล (แก้ไขได้)",
    )
    new_account_count = fields.Integer(
        compute="_compute_tb_summary", help="จำนวนรหัสบัญชีที่ยังไม่มีในผังภายนอก — จะถูกสร้างใหม่")
    dr_total = fields.Float(compute="_compute_tb_summary")
    cr_total = fields.Float(compute="_compute_tb_summary")
    diff = fields.Float(compute="_compute_tb_summary")

    # ------------------------------------------------------------------
    # parse (ตัวอ่านไฟล์อยู่ใน biz.smart.finance.import.mixin)
    # ------------------------------------------------------------------
    def _file_columns(self):
        return FILE_COLUMNS

    def _required_columns(self):
        return ["code", "debit", "credit"]

    # ------------------------------------------------------------------
    # actions
    # ------------------------------------------------------------------
    _preview_fields = ("code", "name", "account_type", "opening", "debit", "credit")
    _preview_context_fields = ("date_from", "date_to")

    def _parse_rows(self, rows):
        mappings = {name: (name, self._to_float) for name in ("opening", "debit", "credit")}
        mappings.update({"code": ("code", str.strip), "name": ("name", str.strip),
                         "account_type": ("account_type", lambda v: self._selection(v, ACCOUNT_TYPE_SET) if v else False)})
        return [self._parse_cells(row, mappings) for row in rows]

    def _validation_context(self):
        return set(self.env["biz.smart.finance.ext.account"].search([
            ("company_id", "=", self.company_id.id)]).mapped("code"))

    def _row_error(self, values, context):
        from odoo.addons.biz_smart_finance.models.bsf_input_validation import finite_values, period_error
        code = (values["code"] or "").strip()
        is_new = bool(code) and code not in context
        error = "" if code else "code: ต้องระบุรหัสบัญชี"
        if not error and is_new and not values["account_type"]:
            error = "account_type: บัญชีใหม่ต้องระบุประเภทบัญชี"
        error = error or finite_values(values, ("opening", "debit", "credit"))
        error = error or period_error({"date_from": self.date_from, "date_to": self.date_to})
        return error, code, is_new

    @api.depends("preview_result", "line_ids.debit", "line_ids.credit")
    def _compute_tb_summary(self):
        for wizard in self:
            valid = [line for line, result in zip(wizard.line_ids, wizard.preview_result or []) if result["valid"]]
            wizard.new_account_count = sum(r["is_new_account"] for r in wizard.preview_result or [])
            wizard.dr_total = sum(line.debit for line in valid)
            wizard.cr_total = sum(line.credit for line in valid)
            wizard.diff = round(wizard.dr_total - wizard.cr_total, 2)

    def _import_records(self):
        period = self.env["biz.smart.finance.period"].search([
            ("company_id", "=", self.company_id.id),
            ("date_from", "=", self.date_from),
        ], limit=1)
        gl = self.env["biz.smart.finance.ext.gl"].upsert_tb(
            self.company_id, self.date_from, self.date_to,
            [
                {
                    "code": line.code,
                    "name": line.name,
                    "account_type": line.account_type,
                    "opening": line.opening,
                    "debit": line.debit,
                    "credit": line.credit,
                }
                for line in self.line_ids
            ],
            source="import",
            period_id=period.id if period else False,
            replace=self.replace_existing,
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": "biz.smart.finance.ext.gl",
            "res_id": gl.id,
            "view_mode": "form",
            "target": "current",
        }


class BsfTbImportLine(models.TransientModel):
    _name = "biz.smart.finance.tb.import.line"
    _inherit = ["biz.smart.finance.import.line.mixin"]
    _description = "Smart Finance — TB Import Preview Line"
    _order = "row_index, id"

    wizard_id = fields.Many2one(
        "biz.smart.finance.tb.import", required=True, ondelete="cascade")
    row_index = fields.Integer(string="แถวในไฟล์", readonly=True)
    code = fields.Char(string="รหัสบัญชี")
    name = fields.Char(string="ชื่อบัญชี")
    account_type = fields.Selection(ACCOUNT_TYPES, string="ประเภทบัญชี")
    opening = fields.Float(string="ยอดยกมา")
    debit = fields.Float(string="เดบิต")
    credit = fields.Float(string="เครดิต")
    is_new_account = fields.Boolean(
        string="บัญชีใหม่", compute="_compute_new_account",
        help="รหัสนี้ยังไม่มีในผังภายนอก — นำเข้าแล้วจะถูกสร้างให้อัตโนมัติ")

    @api.depends("wizard_id.preview_result")
    def _compute_new_account(self):
        for wizard in self.mapped("wizard_id"):
            for line, result in zip(wizard.line_ids, wizard.preview_result or []):
                line.is_new_account = result["is_new_account"]
        for line in self.filtered(lambda row: not row.wizard_id):
            line.is_new_account = False
