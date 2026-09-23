# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountJournal(models.Model):
    _inherit = "account.journal"

    bsf_bank_id = fields.Many2one(
        "biz.smart.finance.bank", string="ธนาคาร (Smart Finance)",
        index=True, ondelete="set null",
        help="ใช้จัดกลุ่มสมุดรายวันนี้เข้าแถวธนาคารในแท็บ Cash & Liquidity",
    )
