# -*- coding: utf-8 -*-
from odoo import fields, models


class BsfBankFacility(models.Model):
    """วงเงินสินเชื่อ/OD ต่อธนาคาร — drawn คำนวณจากบัญชี GL ได้ หรือกรอกมือ"""

    _name = "biz.smart.finance.bank.facility"
    _description = "Smart Finance Bank Facility"
    _order = "bank_id, sequence, id"

    bank_id = fields.Many2one(
        "biz.smart.finance.bank", string="ธนาคาร",
        required=True, ondelete="cascade", index=True,
    )
    sequence = fields.Integer(string="ลำดับ", default=10)
    company_id = fields.Many2one(
        related="bank_id.company_id", store=True, readonly=True, index=True,
    )
    currency_id = fields.Many2one(
        related="bank_id.currency_id", store=True, readonly=True,
    )
    name = fields.Char(string="ชื่อวงเงิน", required=True)
    facility_type = fields.Selection(
        [
            ("od", "OD / Revolving Credit"),
            ("revolving", "Revolving Loan"),
            ("term_loan", "Term Loan"),
            ("lc_tr", "L/C, T/R"),
            ("bank_guarantee", "Bank Guarantee"),
            ("other", "อื่น ๆ"),
        ],
        string="ประเภทวงเงิน", required=True, default="od",
    )
    credit_limit = fields.Monetary(
        string="วงเงินสินเชื่อ", currency_field="currency_id", required=True,
    )
    drawn_basis = fields.Selection(
        [("manual", "กรอกมือ"), ("gl", "จากบัญชีแยกประเภท (GL)")],
        string="ที่มายอดที่ใช้ไป", required=True, default="manual",
    )
    drawn_amount = fields.Monetary(
        string="ยอดที่ใช้ไป (กรอกมือ)", currency_field="currency_id",
        help="ใช้เมื่อ 'ที่มายอดที่ใช้ไป' = กรอกมือ",
    )
    drawn_account_ids = fields.Many2many(
        "account.account", relation="bsf_facility_drawn_account_rel",
        string="บัญชีที่ใช้คำนวณยอดเบิก",
        domain="[('company_id', '=', company_id)]",
        help="ใช้เมื่อ 'ที่มายอดที่ใช้ไป' = GL — ยอดเบิก = ค่าสัมบูรณ์ของยอดสะสมบัญชีเหล่านี้",
    )
    expiry_date = fields.Date(string="วันครบกำหนดวงเงิน")
    note = fields.Char(string="หมายเหตุ")
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("bsf_facility_credit_limit_positive",
         "check(credit_limit > 0)", "วงเงินสินเชื่อต้องมากกว่า 0"),
    ]
