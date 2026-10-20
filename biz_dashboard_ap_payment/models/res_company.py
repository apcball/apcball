# -*- coding: utf-8 -*-
from odoo import fields, models

from .ap_dashboard import clear_cache


class ResCompany(models.Model):
    _inherit = 'res.company'

    apd_other_expense_account_ids = fields.Many2many(
        'account.account', 'apd_company_other_expense_account_rel',
        'company_id', 'account_id',
        string='บัญชีรายจ่ายนอกบิล (Payment Dashboard)',
        domain="[('company_id', '=', id)]",
        help='บัญชีที่รายการสมุดรายวัน (ไม่ผ่านบิลเจ้าหนี้) ถูกนับรวมในยอดจ่ายประจำเดือน '
             'เช่น เงินเดือน ดอกเบี้ย')

    def write(self, vals):
        res = super().write(vals)
        if 'apd_other_expense_account_ids' in vals:
            clear_cache()
        return res
