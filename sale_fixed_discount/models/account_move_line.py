# -*- coding: utf-8 -*-
# Copyright 2024 
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    # The discount_fixed field is already provided as a Monetary field by the 
    # dependency account_invoice_fixed_discount. No need to redefine it here.
