# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountBankTransferCV(models.Model):
    _inherit = "account.bank.transfer"

    buz_customer_refund_voucher_id = fields.Many2one(
        "buz.customer.refund.voucher",
        string="Customer Refund Voucher",
        readonly=True,
        copy=False,
        index=True,
        ondelete="cascade",
    )
