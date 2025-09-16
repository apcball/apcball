# -*- coding: utf-8 -*-
from odoo import models, fields

class AccountMove(models.Model):
    _inherit = 'account.move'

    petty_cash_box_id = fields.Many2one('account.petty.cash.box', string='Petty Cash Box')