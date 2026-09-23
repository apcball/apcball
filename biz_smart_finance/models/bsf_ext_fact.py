# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .bsf_input_validation import fact_error

# metric ที่ระบบภายนอกส่งได้ — ใช้ร่วมกันทั้ง wizard นำเข้า, API adapter และ engine
# แบ่งเป็น 3 กลุ่ม:
#   * BS ณ วันที่ (date = วันสิ้นงวด)
#   * P&L สะสมตั้งแต่ต้นปีงบถึงวันนั้น (*_ytd)
#   * ทางเลือก trailing 12 เดือน (*_t12m) — ถ้ามี จะชนะสำหรับ ratio ประสิทธิภาพ
#     ไม่มีก็ annualize จาก YTD (× 365 / จำนวนวันที่ผ่านมาในปีงบ)
METRIC_KEYS = [
    # ---- Balance Sheet ณ วันที่ ----
    ("cash_and_equivalents", "เงินสดและรายการเทียบเท่า"),
    ("accounts_receivable", "ลูกหนี้การค้า"),
    ("inventory_value", "สินค้าคงเหลือ"),
    ("current_assets", "สินทรัพย์หมุนเวียนรวม"),
    ("total_assets", "สินทรัพย์รวม"),
    ("accounts_payable", "เจ้าหนี้การค้า"),
    ("current_liabilities", "หนี้สินหมุนเวียนรวม"),
    ("total_liabilities", "หนี้สินรวม"),
    ("total_debt", "หนี้สินมีดอกเบี้ย"),
    ("equity", "ส่วนของผู้ถือหุ้น"),
    # ---- P&L สะสมตั้งแต่ต้นปีงบ ----
    ("revenue_ytd", "รายได้สะสม (YTD)"),
    ("cogs_ytd", "ต้นทุนขายสะสม (YTD)"),
    ("gross_profit_ytd", "กำไรขั้นต้นสะสม (YTD)"),
    ("opex_ytd", "ค่าใช้จ่ายดำเนินงานสะสม (YTD)"),
    ("net_profit_ytd", "กำไรสุทธิสะสม (YTD)"),
    ("interest_expense_ytd", "ดอกเบี้ยจ่ายสะสม (YTD)"),
    ("ebit_ytd", "EBIT สะสม (YTD)"),
    # ---- ทางเลือก trailing 12 เดือน ----
    ("revenue_t12m", "รายได้ย้อนหลัง 12 เดือน"),
    ("cogs_t12m", "ต้นทุนขายย้อนหลัง 12 เดือน"),
]
METRIC_KEY_SET = {k for k, _label in METRIC_KEYS}


class BsfExtFact(models.Model):
    """ตัวเลขการเงิน/สินค้าคงเหลือจากระบบภายนอก — ทุกช่องทาง (กรอกมือ /
    import ไฟล์ / API sync) ลงตารางนี้ตารางเดียว แล้ว CFO Cockpit อ่านทางเดียว
    ตัวเลขเป็นสกุลเงินของบริษัท ณ วันสิ้นงวด (date); engine เลือกแถวล่าสุดที่
    date <= as_of ของแต่ละ (kind, metric, หมวด)"""

    _name = "biz.smart.finance.ext.fact"
    _description = "Smart Finance External Figure"
    _order = "date desc, kind, metric_key, label"

    company_id = fields.Many2one(
        "res.company", string="บริษัท", required=True, index=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        related="company_id.currency_id", store=True, readonly=True,
    )
    date = fields.Date(
        string="วันสิ้นงวด", required=True, index=True, default=fields.Date.context_today,
        help="วันที่ของตัวเลข (snapshot ณ สิ้นงวด) — ใช้จับคู่กับงวดบนแดชบอร์ด",
    )
    kind = fields.Selection(
        [("inventory", "มูลค่าสินค้าคงเหลือ"), ("ratio_input", "ตัวเลขอัตราส่วนการเงิน")],
        string="ประเภท", required=True, default="ratio_input", index=True,
    )
    metric_key = fields.Selection(
        METRIC_KEYS, string="Metric", required=True, index=True,
        default="inventory_value",
    )
    label = fields.Char(
        string="หมวดสินค้า", default="",
        help="เฉพาะประเภทสินค้าคงเหลือ: ชื่อหมวดสินค้าในระบบภายนอก",
    )
    amount = fields.Monetary(
        string="มูลค่า", currency_field="currency_id", required=True,
    )
    qty = fields.Float(string="จำนวน", help="เฉพาะสินค้าคงเหลือ (ถ้ามี)")
    source = fields.Selection(
        [("manual", "Manual"), ("import", "Import"), ("api", "API")],
        string="ที่มา", required=True, default="manual",
    )
    external_ref = fields.Char(string="เอกสารอ้างอิง (ระบบภายนอก)")
    note = fields.Char(string="หมายเหตุ")

    _sql_constraints = [
        ("bsf_ext_fact_uniq",
         "unique(company_id, date, kind, metric_key, label)",
         "มีตัวเลขของ (บริษัท, วันที่, ประเภท, metric, หมวด) นี้อยู่แล้ว — แก้ไขรายการเดิมแทน"),
    ]

    @api.onchange("kind")
    def _onchange_kind(self):
        if self.kind == "inventory":
            self.metric_key = "inventory_value"
        else:
            self.label = ""

    @api.constrains("kind", "metric_key", "label", "amount", "qty")
    def _check_kind_metric(self):
        for fact in self:
            error = fact_error({name: fact[name] for name in ("kind", "metric_key", "label", "amount", "qty")})
            if error:
                raise ValidationError(error)

    @api.model
    def upsert_facts(self, company, date, kind, rows, source, replace=True):
        """เขียนตัวเลขหนึ่งงวดของบริษัทเดียว — จุดเขียนร่วมของ wizard และ API

        rows: list ของ {"metric_key", "label", "amount", "qty", "external_ref", "note"}
        replace=True ลบแถวเดิมที่ key ชนก่อน create (ทั้งชุดใน savepoint เดียว)
        คืนจำนวนแถวที่สร้าง"""
        if not rows:
            return 0
        with self.env.cr.savepoint():
            if replace:
                keys = [(r["metric_key"], r.get("label") or "") for r in rows]
                existing = self.search([
                    ("company_id", "=", company.id),
                    ("date", "=", date),
                    ("kind", "=", kind),
                ])
                existing.filtered(
                    lambda f: (f.metric_key, f.label or "") in keys
                ).unlink()
            self.create([
                {
                    "company_id": company.id,
                    "date": date,
                    "kind": kind,
                    "metric_key": r["metric_key"],
                    "label": r.get("label") or "",
                    "amount": r["amount"],
                    "qty": r.get("qty") or 0.0,
                    "source": source,
                    "external_ref": r.get("external_ref") or "",
                    "note": r.get("note") or "",
                }
                for r in rows
            ])
        return len(rows)
