# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError

# แหล่งข้อมูลที่เลือกได้ต่องวด — เหมือนสี่ตัวเลือกเดิมใน bsf.config ทุกประการ
# แต่ "" (ว่าง) = ยังไม่ override ที่งวดนี้ ให้ engine ใช้ค่าตั้งต้นจาก config
SOURCE_OPTIONS = [("odoo", "Odoo"), ("external", "ระบบภายนอก")]
OVERRIDE_OPTIONS = [("", "ตามค่าตั้งต้นของบริษัท")] + SOURCE_OPTIONS
SOURCE_FIELDS = (
    "gl_source", "invoice_source", "inventory_source",
    "ratio_source", "budget_source",
)


class BsfPeriod(models.Model):
    """ทะเบียนงวด (Monthly Close Cockpit) — หนึ่งแถวต่อหนึ่งเดือนปฏิทินของบริษัท

    จุดประสงค์เดียว: ให้เลือก**แหล่งข้อมูลของแต่ละแท็บ ทีละเดือน** แทนที่จะ
    เป็นสวิตช์ระดับบริษัทของ `bsf.config` — ตอบโจทย์การตัดข้อมูลจากระบบเดิมมาใช้
    Odoo แบบค่อยเป็นค่อยไป (เช่น ม.ค.–ก.ย. ใช้ระบบเดิม, ต.ค. เป็นต้นไปใช้ Odoo)

    งวดที่ไม่มีแถวในตารางนี้ = ใช้ค่าตั้งต้นจาก `bsf.config` เหมือนเดิมทุกประการ
    (นี่คือ fast path ที่ `_build_shared` ยิงคิวรีชุดเดียวกับก่อนมีโมดูลนี้)"""

    _name = "biz.smart.finance.period"
    _description = "Smart Finance Period (Monthly Close Cockpit)"
    _order = "company_id, date_from"
    _rec_name = "name"

    company_id = fields.Many2one(
        "res.company", string="บริษัท", required=True, index=True,
        default=lambda self: self.env.company,
    )
    date_from = fields.Date(string="วันแรกของเดือน", required=True, index=True)
    date_to = fields.Date(string="วันสุดท้ายของเดือน", required=True, index=True)
    name = fields.Char(string="งวด", compute="_compute_name", store=True)
    fy_year = fields.Integer(
        string="ปีงบ (FY ปิดปี)", index=True,
        help="ปีปฏิทินที่ปีงบนี้สิ้นสุด — ตรงกับตัวกรอง 'ปีงบ' บนแดชบอร์ด",
    )
    period_index = fields.Integer(string="งวดที่ (P)")

    gl_source = fields.Selection(
        OVERRIDE_OPTIONS, string="บัญชีแยกประเภท (GL)", default="")
    invoice_source = fields.Selection(
        OVERRIDE_OPTIONS, string="ใบแจ้งหนี้/บิลค้าง", default="")
    inventory_source = fields.Selection(
        OVERRIDE_OPTIONS, string="สินค้าคงเหลือ", default="")
    ratio_source = fields.Selection(
        OVERRIDE_OPTIONS, string="อัตราส่วนการเงิน", default="")
    budget_source = fields.Selection(
        OVERRIDE_OPTIONS, string="งบศูนย์ต้นทุน", default="")

    state = fields.Selection(
        [("open", "เปิดอยู่"), ("review", "รอตรวจสอบ"), ("closed", "ปิดงวดแล้ว")],
        string="สถานะ", required=True, default="open", index=True,
    )
    closed_by = fields.Many2one("res.users", string="ปิดงวดโดย", readonly=True)
    closed_date = fields.Datetime(string="วันที่ปิดงวด", readonly=True)

    gl_id = fields.Many2one(
        "biz.smart.finance.ext.gl", string="Trial Balance ภายนอก",
        compute="_compute_gl", help="TB ภายนอกของเดือนนี้ ถ้ามี (ผูกตอนนำเข้า)",
    )
    tb_diff = fields.Monetary(
        string="ผลต่าง TB", currency_field="currency_id", compute="_compute_gl")
    currency_id = fields.Many2one(
        related="company_id.currency_id", readonly=True)

    _sql_constraints = [
        ("bsf_period_company_month_uniq", "unique(company_id, date_from)",
         "มีงวดของบริษัทและเดือนนี้อยู่แล้ว"),
    ]

    @api.depends("date_from")
    def _compute_name(self):
        for period in self:
            period.name = (
                "%04d-%02d" % (period.date_from.year, period.date_from.month)
                if period.date_from else "")

    @api.depends("company_id", "date_from", "date_to")
    def _compute_gl(self):
        """หา TB ภายนอกของทุกงวดใน self ด้วยคิวรีเดียว

        เดิมยิง search ต่อ record — จอทะเบียนงวดโชว์ทั้งปีของทุกบริษัท (และ
        `decoration-danger="tb_diff"` บังคับให้คำนวณแม้ซ่อนคอลัมน์) payload
        Monthly Close ก็ขอสองฟิลด์นี้ผ่าน search_read เช่นกัน
        """
        rows = self.env["biz.smart.finance.ext.gl"].search_read(
            [("company_id", "in", self.company_id.ids),
             ("date_from", "in", list({p.date_from for p in self if p.date_from})),
             ("date_to", "in", list({p.date_to for p in self if p.date_to}))],
            ["company_id", "date_from", "date_to", "diff"],
        ) if self else []
        # คีย์ตรงกับเงื่อนไขเดิมทุกตัว — โดเมนด้านบนกว้างกว่า (product ของสาม
        # ชุด) จึงต้องจับคู่ให้ครบสามฟิลด์อีกครั้งใน Python
        by_key = {
            (row["company_id"][0], row["date_from"], row["date_to"]): row
            for row in rows
        }
        for period in self:
            row = by_key.get(
                (period.company_id.id, period.date_from, period.date_to))
            period.gl_id = row["id"] if row else False
            period.tb_diff = row["diff"] if row else 0.0

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for period in self:
            if period.date_to < period.date_from:
                raise ValidationError(
                    "วันสุดท้ายของงวด (%s) ต้องไม่ก่อนวันแรกของงวด (%s)"
                    % (period.date_to, period.date_from))

    def action_close(self):
        for period in self.filtered(lambda p: p.gl_id and p.gl_id.diff):
            raise ValidationError(
                "งวด %s: Trial Balance ยังไม่ดุล (ผลต่าง %s) — ปิดงวดไม่ได้"
                % (period.display_name, period.gl_id.diff))
        self.write({
            "state": "closed",
            "closed_by": self.env.user.id,
            "closed_date": fields.Datetime.now(),
        })

    def action_reopen(self):
        self.write({"state": "open", "closed_by": False, "closed_date": False})

    @api.model
    def action_generate_year(self, company_id, fy_year):
        """สร้าง 12 งวดของปีงบที่ปิดปี fy_year — ใช้ปฏิทินปีงบเดียวกับ engine
        (`_fy_periods`) จึงตรงกับตัวกรองบนแดชบอร์ดเป๊ะ ๆ ไม่ว่าปีงบจะไม่ตรง
        ปีปฏิทินหรือไม่ก็ตาม ข้ามงวดที่มีอยู่แล้ว คืนจำนวนงวดที่สร้างใหม่"""
        company = self.env["res.company"].browse(company_id)
        Dashboard = self.env["biz.smart.finance.dashboard"]
        fy_from, fy_to = Dashboard._fiscal_year(company, fy_year)
        periods = Dashboard._fy_periods(fy_from, fy_to)
        existing = {
            p.date_from for p in self.search([
                ("company_id", "=", company_id),
                ("date_from", "in", [pd["date_from"] for pd in periods]),
            ])
        }
        vals = [
            {
                "company_id": company_id,
                "date_from": p["date_from"],
                "date_to": p["date_to"],
                "fy_year": fy_year,
                "period_index": p["index"],
            }
            for p in periods if p["date_from"] not in existing
        ]
        created = self.create(vals) if vals else self.browse()
        return len(created)

    def action_set_source_range(self):
        """เปิดวิซาร์ดตั้งแหล่งข้อมูลของงวดที่เลือก (หลายงวดพร้อมกัน)"""
        return {
            "type": "ir.actions.act_window",
            "name": "ตั้งแหล่งข้อมูลของงวด",
            "res_model": "biz.smart.finance.period.source.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_period_ids": self.ids},
        }


class BsfPeriodGenerateWizard(models.TransientModel):
    """สร้างงวดรายเดือนของทั้งปีงบให้บริษัทหนึ่ง — ใช้ปฏิทินปีงบเดียวกับ
    engine (`_fy_periods`) ผ่าน `period.action_generate_year()`"""

    _name = "biz.smart.finance.period.generate.wizard"
    _description = "Smart Finance Period Generate Wizard"

    company_id = fields.Many2one(
        "res.company", string="บริษัท", required=True,
        default=lambda self: self.env.company,
    )
    fy_year = fields.Integer(
        string="ปีงบ (FY ปิดปี)", required=True,
        default=lambda self: fields.Date.context_today(self).year,
    )

    def action_apply(self):
        self.ensure_one()
        created = self.env["biz.smart.finance.period"].action_generate_year(
            self.company_id.id, self.fy_year)
        action = self.env["ir.actions.actions"]._for_xml_id(
            "biz_smart_finance.action_bsf_period")
        action["domain"] = [
            ("company_id", "=", self.company_id.id),
            ("fy_year", "=", self.fy_year),
        ]
        action["context"] = {}
        if not created:
            # ไม่มีงวดใหม่ (มีอยู่แล้วทั้งหมด) — เปิดรายการเดิมให้ดูตรง ๆ
            action["help"] = None
        return action


class BsfPeriodSourceWizard(models.TransientModel):
    """ตั้งแหล่งข้อมูล 5 แท็บให้หลายงวดพร้อมกัน — เว้นช่องไหนว่างไว้ (ไม่เปลี่ยน)
    ไม่แตะฟิลด์นั้นของงวดที่เลือก ใช้ตอบโจทย์ 'ตัดจากระบบเดิมมา Odoo' เป็นช่วง ๆ"""

    _name = "biz.smart.finance.period.source.wizard"
    _description = "Smart Finance Period Source Wizard"

    period_ids = fields.Many2many(
        "biz.smart.finance.period", relation="bsf_period_source_wizard_rel",
        string="งวดที่เลือก", required=True)
    gl_source = fields.Selection(
        [("keep", "— ไม่เปลี่ยน —")] + OVERRIDE_OPTIONS,
        string="บัญชีแยกประเภท (GL)", default="keep", required=True)
    invoice_source = fields.Selection(
        [("keep", "— ไม่เปลี่ยน —")] + OVERRIDE_OPTIONS,
        string="ใบแจ้งหนี้/บิลค้าง", default="keep", required=True)
    inventory_source = fields.Selection(
        [("keep", "— ไม่เปลี่ยน —")] + OVERRIDE_OPTIONS,
        string="สินค้าคงเหลือ", default="keep", required=True)
    ratio_source = fields.Selection(
        [("keep", "— ไม่เปลี่ยน —")] + OVERRIDE_OPTIONS,
        string="อัตราส่วนการเงิน", default="keep", required=True)
    budget_source = fields.Selection(
        [("keep", "— ไม่เปลี่ยน —")] + OVERRIDE_OPTIONS,
        string="งบศูนย์ต้นทุน", default="keep", required=True)

    def action_apply(self):
        self.ensure_one()
        vals = {
            field: getattr(self, field)
            for field in SOURCE_FIELDS
            if getattr(self, field) != "keep"
        }
        if vals:
            self.period_ids.write(vals)
        return {"type": "ir.actions.act_window_close"}
