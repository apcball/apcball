# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .bsf_input_validation import finite_values, company_error, period_error


class BsfExtGl(models.Model):
    """Trial Balance หนึ่งงวด (หนึ่งเดือน) ของระบบเดิม — หัวเอกสาร

    เก็บทั้ง **opening** (ยอดยกมา) และ **movement** (debit/credit ของงวดนั้น)
    ต่อบัญชี เพื่อให้ตรวจสอบได้สองทาง: `Σdebit = Σcredit` ของงวดนี้ และ
    `closing งวดก่อน = opening งวดนี้` — ตรงกับที่ผู้ตรวจสอบบัญชีเรียก TB จริง

    เฉพาะงวดที่ `state = posted` เท่านั้นที่ engine (`_build_shared`) อ่าน
    (กติกาเดียวกับ `parent_state = posted` ของ `account.move.line`)"""

    _name = "biz.smart.finance.ext.gl"
    _description = "Smart Finance External Trial Balance (period)"
    _order = "company_id, date_from desc"
    _rec_name = "display_name"

    company_id = fields.Many2one(
        "res.company", string="บริษัท", required=True, index=True,
        default=lambda self: self.env.company,
    )
    period_id = fields.Many2one(
        "biz.smart.finance.period", string="งวด", index=True,
        help="ทะเบียนงวด (Monthly Close Cockpit) ของเดือนนี้ — ผูกไว้เพื่อให้ "
             "หน้าสถานะปิดงวดเห็นว่ามี TB ลงแล้วหรือยัง ไม่ผูกก็นำเข้าได้ปกติ",
    )
    date_from = fields.Date(string="วันแรกของงวด", required=True, index=True)
    date_to = fields.Date(string="วันสุดท้ายของงวด", required=True, index=True)
    state = fields.Selection(
        [("draft", "ร่าง"), ("posted", "ยืนยันแล้ว")],
        string="สถานะ", required=True, default="draft", index=True,
    )
    source = fields.Selection(
        [("manual", "Manual"), ("import", "Import"), ("api", "API")],
        string="ที่มา", required=True, default="manual",
    )
    note = fields.Char(string="หมายเหตุ")
    line_ids = fields.One2many(
        "biz.smart.finance.ext.gl.line", "gl_id", string="รายการ")
    line_count = fields.Integer(
        compute="_compute_totals", store=True, string="จำนวนบัญชี")
    dr_total = fields.Monetary(
        string="รวมเดบิต", currency_field="currency_id",
        compute="_compute_totals", store=True,
    )
    cr_total = fields.Monetary(
        string="รวมเครดิต", currency_field="currency_id",
        compute="_compute_totals", store=True,
    )
    diff = fields.Monetary(
        string="ผลต่าง (เดบิต − เครดิต)", currency_field="currency_id",
        compute="_compute_totals", store=True,
        help="ต้องเป็น 0 ก่อนกดยืนยัน — ไม่ดุลแปลว่าไฟล์นำเข้าไม่ครบหรือพิมพ์ผิด",
    )
    currency_id = fields.Many2one(
        related="company_id.currency_id", store=True, readonly=True,
    )

    _sql_constraints = [
        ("bsf_ext_gl_period_uniq", "unique(company_id, date_from, date_to)",
         "มี Trial Balance ของบริษัทและงวดนี้อยู่แล้ว — แก้ไขรายการเดิมแทน"),
    ]

    @api.depends("date_from", "date_to")
    def _compute_display_name(self):
        for gl in self:
            gl.display_name = "%s: %s – %s" % (
                gl.company_id.name, gl.date_from, gl.date_to)

    @api.depends("line_ids.debit", "line_ids.credit")
    def _compute_totals(self):
        """ยอดรวมของ TB — aggregate ที่ฐาน ไม่ดูดบรรทัดขึ้นมาทั้งงวด

        TB หนึ่งงวดมีได้หลายพันบรรทัด และ compute นี้ถูกเรียกใหม่ทุกครั้งที่มี
        การแก้บรรทัดใน tree แบบแก้ในบรรทัดได้ — `mapped()` เท่ากับ materialise
        ทุกบรรทัดของทุกงวดที่อยู่บนจอ
        """
        stored = self.filtered(lambda gl: isinstance(gl.id, int))
        rows = self.env["biz.smart.finance.ext.gl.line"]._read_group(
            [("gl_id", "in", stored.ids)], groupby=["gl_id"],
            aggregates=["__count", "debit:sum", "credit:sum"],
        ) if stored else []
        by_gl = {
            gl.id: (count, debit or 0.0, credit or 0.0)
            for gl, count, debit, credit in rows
        }
        for gl in self:
            if gl in stored:
                count, debit, credit = by_gl.get(gl.id, (0, 0.0, 0.0))
            else:
                # ระเบียนที่ยังไม่บันทึก (onchange/ฟอร์มใหม่) ไม่มีแถวในฐาน
                lines = gl.line_ids
                count = len(lines)
                debit = sum(lines.mapped("debit"))
                credit = sum(lines.mapped("credit"))
            gl.line_count = count
            gl.dr_total = debit
            gl.cr_total = credit
            gl.diff = round(debit - credit, 2)

    @api.constrains("date_from", "date_to", "company_id", "period_id")
    def _check_dates(self):
        for gl in self:
            error = period_error({"date_from": gl.date_from, "date_to": gl.date_to})
            error = error or company_error(gl.company_id, gl.period_id, "งวด")
            if error:
                raise ValidationError(error)
            for line in gl.line_ids:
                line._check_input()

    def action_post(self):
        for gl in self:
            if gl.diff:
                raise ValidationError(
                    "Trial Balance ของ %s ไม่ดุล (เดบิต − เครดิต = %s) "
                    "— แก้ยอดให้ตรงก่อนยืนยัน" % (gl.display_name, gl.diff))
            if not gl.line_ids:
                raise ValidationError(
                    "Trial Balance ของ %s ไม่มีรายการ" % gl.display_name)
        self.write({"state": "posted"})

    def action_reset_to_draft(self):
        self.write({"state": "draft"})

    @api.model
    def upsert_tb(self, company, date_from, date_to, rows, source,
                   period_id=False, replace=True):
        """เขียน TB หนึ่งงวดของบริษัทเดียว — จุดเขียนร่วมของ wizard นำเข้าและ API

        rows: list ของ {"code", "name", "account_type", "opening", "debit",
                        "credit"} — บัญชีที่ยังไม่มีในผังภายนอกจะถูกสร้างให้
        replace=True แทนที่ TB เดิมของงวดนี้ทั้งชุด (ลบ header เดิม สร้างใหม่)
        คืน record `ext.gl` ที่สร้าง (state=draft — ต้อง action_post() เอง)"""
        ExtAccount = self.env["biz.smart.finance.ext.account"]
        Line = self.env["biz.smart.finance.ext.gl.line"]
        with self.env.cr.savepoint():
            if replace:
                existing = self.search([
                    ("company_id", "=", company.id),
                    ("date_from", "=", date_from), ("date_to", "=", date_to),
                ])
                existing.unlink()
            gl = self.create({
                "company_id": company.id,
                "date_from": date_from,
                "date_to": date_to,
                "period_id": period_id or False,
                "source": source,
            })
            # หาบัญชี/สร้างที่ขาดเป็นชุดเดียวก่อน — เดิม resolve() ถูกเรียก
            # ในลูปนี้ = select (+insert) ต่อบรรทัด TB หนึ่งงวดมีได้หลายร้อยบัญชี
            account_of_code = ExtAccount.resolve_many(company, rows)
            Line.create([
                {
                    "gl_id": gl.id,
                    "ext_account_id": account_of_code[r["code"]],
                    "opening": r.get("opening") or 0.0,
                    "debit": r.get("debit") or 0.0,
                    "credit": r.get("credit") or 0.0,
                }
                for r in rows
            ])
        return gl


class BsfExtGlLine(models.Model):
    """บรรทัดบัญชีหนึ่งบัญชีใน Trial Balance หนึ่งงวด"""

    _name = "biz.smart.finance.ext.gl.line"
    _description = "Smart Finance External Trial Balance Line"
    _order = "gl_id, ext_account_id"

    gl_id = fields.Many2one(
        "biz.smart.finance.ext.gl", string="Trial Balance", required=True,
        index=True, ondelete="cascade",
    )
    company_id = fields.Many2one(
        related="gl_id.company_id", store=True, index=True, readonly=True)
    # engine ยิงโดเมน (company_id, date_to, state) ต่อช่อง (บริษัท × เดือน)
    # ใน _build_shared — ไม่มี index สองตัวนี้จะกลายเป็น heap scan ทั้งตาราง
    date_to = fields.Date(
        related="gl_id.date_to", store=True, index=True, readonly=True)
    state = fields.Selection(
        related="gl_id.state", store=True, index=True, readonly=True)
    ext_account_id = fields.Many2one(
        "biz.smart.finance.ext.account", string="บัญชี", required=True,
        index=True,
        domain="[('company_id', '=', company_id)]",
    )
    account_type = fields.Selection(
        related="ext_account_id.account_type", store=True, readonly=True)
    currency_id = fields.Many2one(
        related="gl_id.currency_id", readonly=True)
    opening = fields.Monetary(
        string="ยอดยกมา", currency_field="currency_id",
        help="ยอด (เดบิต − เครดิต) ณ ต้นงวด — ต้องตรงกับ 'ยอดยกไป' ของงวดก่อนหน้า",
    )
    debit = fields.Monetary(string="เดบิตระหว่างงวด", currency_field="currency_id")
    credit = fields.Monetary(string="เครดิตระหว่างงวด", currency_field="currency_id")
    balance = fields.Monetary(
        string="ยอดเคลื่อนไหวงวดนี้ (เดบิต − เครดิต)",
        currency_field="currency_id",
        compute="_compute_balance", store=True,
    )
    closing = fields.Monetary(
        string="ยอดยกไป", currency_field="currency_id",
        compute="_compute_balance", store=True,
        help="ยอดยกมา + เดบิต − เครดิต — ใช้เป็นยอดสะสม ณ วันสิ้นงวดของบัญชีนี้",
    )

    _sql_constraints = [
        ("bsf_ext_gl_line_uniq", "unique(gl_id, ext_account_id)",
         "บัญชีนี้มีอยู่ใน Trial Balance งวดนี้แล้ว"),
    ]

    @api.constrains("opening", "debit", "credit", "ext_account_id", "gl_id", "company_id")
    def _check_input(self):
        for line in self:
            error = finite_values({name: line[name] for name in ("opening", "debit", "credit")},
                                  ("opening", "debit", "credit"))
            error = error or company_error(line.company_id, line.ext_account_id, "บัญชี")
            if error:
                raise ValidationError(error)

    @api.depends("opening", "debit", "credit")
    def _compute_balance(self):
        for line in self:
            line.balance = round(line.debit - line.credit, 2)
            line.closing = round(line.opening + line.balance, 2)
