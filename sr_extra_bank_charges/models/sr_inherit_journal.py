# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) Sitaram Solutions (<https://sitaramsolutions.in/>).
#
#    For Module Support : info@sitaramsolutions.in  or Skype : contact.hiren1188
#
##############################################################################

from odoo import fields, models


class srAccountJournal(models.Model):
    _inherit = 'account.journal'
    
    default_bank_charge_account_id = fields.Many2one('account.account', string="Extra Bank Charge Account")

