# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .bsf_input_validation import budget_error, company_error


class BsfExtBudget(models.Model):
    """งบประมาณศูนย์ต้นทุนจากระบบภายนอก — ใช้เมื่อไม่ได้ตั้งงบใน Odoo

    แทน `crossovered.budget.lines` ของ om_account_budget ในแท็บ Controlling
    ทั้งสองแหล่งถูกเฉลี่ยตามจำนวนวันที่ทับช่วงงวดเหมือนกัน (pro-rata) และ
    ต้นทุนจริง/ภาระผูกพันยังมาจาก analytic line กับ PO ของ Odoo ตามเดิม
    จึงต้อง**ผูกศูนย์ต้นทุนเป็น analytic account จริง** ไม่ใช่ชื่อลอย ๆ
    (ไม่งั้นงบกับต้นทุนจริงอยู่คนละแถว เทียบกันไม่ได้)

    ยอดงบเป็น**ต้นทุนที่ตั้งไว้ (บวก)** สกุลเงินของบริษัท"""

    _name = "biz.smart.finance.ext.budget"
    _description = "Smart Finance External Cost-Centre Budget"
    _order = "date_from desc, id desc"
    _rec_name = "analytic_account_id"

    company_id = fields.Many2one(
        "res.company", string="บริษัท", required=True, index=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        related="company_id.currency_id", store=True, readonly=True,
    )
    analytic_account_id = fields.Many2one(
        "account.analytic.account", string="ศูนย์ต้นทุน", required=True,
        index=True, ondelete="cascade",
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        help="แถวนี้จะโผล่ในแท็บ Controlling ก็ต่อเมื่อศูนย์ต้นทุนอยู่ในแผน "
             "(analytic plan) ที่เลือกดูบนจอ",
    )
    date_from = fields.Date(string="ตั้งแต่วันที่", required=True, index=True)
    # โดเมน overlap ของ Controlling กรอง date_from <= X และ date_to >= Y
    date_to = fields.Date(string="ถึงวันที่", required=True, index=True)
    amount = fields.Monetary(
        string="งบต้นทุน", currency_field="currency_id", required=True,
        help="ยอดของทั้งช่วง — ระบบเฉลี่ยตามจำนวนวันที่ทับกับงวดที่ดูอยู่",
    )
    source = fields.Selection(
        [("manual", "Manual"), ("import", "Import"), ("api", "API")],
        string="ที่มา", required=True, default="manual",
    )
    external_ref = fields.Char(string="เอกสารอ้างอิง (ระบบภายนอก)")
    note = fields.Char(string="หมายเหตุ")

    _sql_constraints = [
        ("bsf_ext_budget_uniq",
         "unique(company_id, analytic_account_id, date_from, date_to)",
         "มีงบของศูนย์ต้นทุนนี้ในช่วงวันที่นี้อยู่แล้ว — แก้ไขรายการเดิมแทน"),
    ]

    @api.constrains("date_from", "date_to", "amount", "company_id", "analytic_account_id")
    def _check_input(self):
        for budget in self:
            error = budget_error({name: budget[name] for name in ("date_from", "date_to", "amount")})
            error = error or company_error(budget.company_id, budget.analytic_account_id, "ศูนย์ต้นทุน")
            if error:
                raise ValidationError(error)

    @api.model
    def upsert_budgets(self, company, rows, source, replace=True):
        """เขียนงบภายนอกของบริษัทเดียว — จุดเขียนร่วมของ wizard และ API

        rows: list ของ {"analytic_account_id", "date_from", "date_to",
                        "amount", "external_ref", "note"}
        replace=True ลบแถวเดิมที่ (ศูนย์ต้นทุน, ช่วงวันที่) ชนก่อน create"""
        if not rows:
            return 0
        with self.env.cr.savepoint():
            if replace:
                keys = {
                    (r["analytic_account_id"], str(r["date_from"]),
                     str(r["date_to"]))
                    for r in rows
                }
                # จำกัดด้วยคีย์ที่กำลังนำเข้า (เหตุผลเดียวกับ ext.invoice)
                existing = self.search([
                    ("company_id", "=", company.id),
                    ("analytic_account_id", "in",
                     list({k[0] for k in keys})),
                    ("date_from", "in", list({k[1] for k in keys})),
                    ("date_to", "in", list({k[2] for k in keys})),
                ])
                existing.filtered(
                    lambda b: (b.analytic_account_id.id, str(b.date_from),
                               str(b.date_to)) in keys
                ).unlink()
            self.create([
                {
                    "company_id": company.id,
                    "analytic_account_id": r["analytic_account_id"],
                    "date_from": r["date_from"],
                    "date_to": r["date_to"],
                    "amount": r["amount"],
                    "source": source,
                    "external_ref": r.get("external_ref") or "",
                    "note": r.get("note") or "",
                }
                for r in rows
            ])
        return len(rows)
