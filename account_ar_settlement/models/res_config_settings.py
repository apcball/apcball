# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    payment_difference_account_id = fields.Many2one(
        'account.account',
        string='Payment Difference Account',
        help='Default account for AR settlement payment differences '
             '(e.g. 214100 Accrued Expenses).',
        config_parameter='account_ar_settlement.payment_difference_account_id',
    )
