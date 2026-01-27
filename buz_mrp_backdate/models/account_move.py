# -*- coding: utf-8 -*-

from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    mrp_backdate_remark = fields.Text(
        string='MRP Backdate Remark',
        help='Remark from manufacturing order backdate',
        copy=False,
    )
