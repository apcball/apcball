# -*- coding: utf-8 -*-
# Copyright 2024 
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    discount_fixed = fields.Float(
        string='Discount (Fixed)',
        digits=(16, 4),
        help='Apply a fixed amount discount to this line. The amount is multiplied by the quantity of the product.'
    )
