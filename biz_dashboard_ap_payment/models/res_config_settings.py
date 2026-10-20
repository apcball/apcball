# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    apd_other_expense_account_ids = fields.Many2many(
        related='company_id.apd_other_expense_account_ids', readonly=False,
        domain="[('company_id', '=', company_id)]")
