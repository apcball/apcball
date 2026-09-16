# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .bsf_input_validation import invoice_error, company_error

# ประเภทเอกสาร — ตรงกับสองฝั่งที่ engine อ่าน (shared["ar_items"] / ["ap_items"])
DOC_TYPES = [
    ("ar", "ลูกหนี้ — ใบแจ้งหนี้ขาย"),
    ("ap", "เจ้าหนี้ — บิลซื้อ"),
]


class BsfExtInvoice(models.Model):
    """ใบแจ้งหนี้/บิลคงค้างจากระบบภายนอก — ใช้เมื่อบริษัทไม่ได้ออกเอกสารใน Odoo

    ทุกช่องทาง (กรอกมือ / import ไฟล์ / API sync) ลงตารางนี้ตารางเดียว แล้ว
    CFO Cockpit อ่านทางเดียวผ่าน `_build_shared()` เหมือนบรรทัด AR/AP ของ Odoo
    ทุกประการ — AR aging, AP & Payment Plan, 13-week cash forecast และ
    Sales to Cash จึงได้ตัวเลขชุดเดียวกัน

    ยอดเงินเป็น**สกุลเงินของบริษัท** และเป็น**บวกเสมอทั้งสองฝั่ง**
    (ยอดที่ยังไม่ได้รับ / ยังไม่ได้จ่าย) — ไม่ต้องกลับเครื่องหมายแบบ GL
    ใบลดหนี้ที่หักยอดค้างให้กรอกเป็นจำนวนติดลบทั้งยอดรวมและยอดค้าง"""

    _name = "biz.smart.finance.ext.invoice"
    _description = "Smart Finance External Invoice (AR/AP)"
    _order = "date_due desc, date desc, id desc"
    _rec_name = "number"

    company_id = fields.Many2one(
        "res.company", string="บริษัท", required=True, index=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        related="company_id.currency_id", store=True, readonly=True,
    )
    doc_type = fields.Selection(
        DOC_TYPES, string="ประเภทเอกสาร", required=True, default="ar",
        index=True,
    )
    number = fields.Char(
        string="เลขที่เอกสาร", required=True, index=True,
        help="เลขที่ในระบบภายนอก — ใช้เป็นกุญแจตอน sync ซ้ำ (แถวเดิมถูกทับ)",
    )
    partner_id = fields.Many2one(
        "res.partner", string="คู่ค้าใน Odoo", index=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        help="ผูกได้ก็ผูก — ถ้าผูกไว้ ตาราง Top Customer / Top Supplier "
             "จะคลิกเปิดดูเอกสารของคู่ค้ารายนั้นต่อได้",
    )
    partner_name = fields.Char(
        string="ชื่อคู่ค้า", required=True,
        help="ชื่อตามระบบภายนอก — ใช้จัดกลุ่มเมื่อไม่ได้ผูกคู่ค้าใน Odoo",
    )
    date = fields.Date(
        string="วันที่เอกสาร", required=True, index=True,
        default=fields.Date.context_today,
    )
    date_due = fields.Date(
        string="ครบกำหนดชำระ", index=True,
        help="เว้นว่าง = ใช้วันที่เอกสาร (ถือว่าครบกำหนดทันที)",
    )
    amount_total = fields.Monetary(
        string="ยอดรวม", currency_field="currency_id", required=True,
    )
    amount_untaxed = fields.Monetary(
        string="ยอดก่อนภาษี", currency_field="currency_id",
        help="ใช้ในกรวย Sales to Cash — เว้นว่าง (0) = ใช้ยอดรวม",
    )
    amount_residual = fields.Monetary(
        string="ยอดค้าง", currency_field="currency_id", required=True,
        help="ยอดที่ยังไม่ได้รับ/ยังไม่ได้จ่าย ณ วันนี้ — 0 = ปิดแล้ว "
             "(ยังเก็บไว้เพื่อคิดสัดส่วนเก็บเงินได้)",
    )
    source = fields.Selection(
        [("manual", "Manual"), ("import", "Import"), ("api", "API")],
        string="ที่มา", required=True, default="manual",
    )
    external_ref = fields.Char(string="เอกสารอ้างอิง (ระบบภายนอก)")
    note = fields.Char(string="หมายเหตุ")

    _sql_constraints = [
        ("bsf_ext_invoice_uniq",
         "unique(company_id, doc_type, number)",
         "มีเอกสารเลขที่นี้ของบริษัทและประเภทนี้อยู่แล้ว — แก้ไขรายการเดิมแทน"),
    ]

    @api.depends("number", "partner_name")
    def _compute_display_name(self):
        for doc in self:
            doc.display_name = "%s · %s" % (
                doc.number or "?", doc.partner_name or "")

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        if self.partner_id and not self.partner_name:
            self.partner_name = self.partner_id.display_name

    @api.constrains("amount_total", "amount_untaxed", "amount_residual", "date", "date_due",
                    "company_id", "partner_id")
    def _check_input(self):
        for doc in self:
            error = invoice_error({name: doc[name] for name in (
                "amount_total", "amount_untaxed", "amount_residual", "date", "date_due")})
            error = error or company_error(doc.company_id, doc.partner_id, "คู่ค้า")
            if error:
                raise ValidationError(error)

    @api.model
    def upsert_invoices(self, company, rows, source, replace=True):
        """เขียนเอกสารภายนอกของบริษัทเดียว — จุดเขียนร่วมของ wizard และ API

        rows: list ของ {"doc_type", "number", "partner_name", "partner_id",
                        "date", "date_due", "amount_total", "amount_untaxed",
                        "amount_residual", "external_ref", "note"}
        replace=True ลบแถวเดิมที่ (doc_type, number) ชนก่อน create
        คืนจำนวนแถวที่สร้าง"""
        if not rows:
            return 0
        with self.env.cr.savepoint():
            if replace:
                keys = {(r["doc_type"], r["number"]) for r in rows}
                # จำกัดด้วยคีย์ที่กำลังนำเข้า — เดิม search ทั้งตารางของบริษัท
                # แล้วค่อย filtered() ใน Python (นำเข้า 200 แถวก็ยังดูดหมด
                # ทุกแถวของบริษัทขึ้นมา) โดเมนนี้ตรงกับ index เฉพาะที่มีอยู่แล้ว
                existing = self.search([
                    ("company_id", "=", company.id),
                    ("doc_type", "in", list({k[0] for k in keys})),
                    ("number", "in", list({k[1] for k in keys})),
                ])
                existing.filtered(
                    lambda d: (d.doc_type, d.number) in keys
                ).unlink()
            self.create([
                {
                    "company_id": company.id,
                    "doc_type": r["doc_type"],
                    "number": r["number"],
                    "partner_id": r.get("partner_id") or False,
                    "partner_name": r.get("partner_name") or "",
                    "date": r["date"],
                    "date_due": r.get("date_due") or False,
                    "amount_total": r["amount_total"],
                    "amount_untaxed": r.get("amount_untaxed") or 0.0,
                    "amount_residual": r["amount_residual"],
                    "source": source,
                    "external_ref": r.get("external_ref") or "",
                    "note": r.get("note") or "",
                }
                for r in rows
            ])
        return len(rows)
