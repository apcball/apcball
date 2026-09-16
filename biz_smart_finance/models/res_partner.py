# -*- coding: utf-8 -*-
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    bsf_strategic_supplier = fields.Boolean(
        string="ซัพพลายเออร์เชิงกลยุทธ์",
        help="ถ่วงน้ำหนักใน Payment Priority Ranking ของ CFO Cockpit — "
        "เจ้าที่หยุดส่งของแล้วงานสะดุดทั้งบริษัท",
    )
    bsf_billing_mode = fields.Selection([
        ("delivery", "วางบิลวันส่งมอบ"),
        ("monthly", "วางบิลตามรอบเดือน"),
    ], string="รอบวางบิล Sales to Cash", default="monthly")
    bsf_billing_days = fields.Char(
        string="วันที่วางบิลในเดือน", default="25",
        help="คั่นด้วยจุลภาค เช่น 10,25 หรือ 31 สำหรับวันสิ้นเดือน",
    )
    bsf_credit_limit = fields.Monetary(
        string="วงเงินเครดิต", currency_field="currency_id",
        help="0 หมายถึงยังไม่กำหนดวงเงินเครดิต",
    )
    bsf_collection_owner_id = fields.Many2one("res.users", string="ผู้ดูแลการเก็บเงิน")
