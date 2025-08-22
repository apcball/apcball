    # -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) Sitaram Solutions (<https://sitaramsolutions.in/>).
#
#    For Module Support : info@sitaramsolutions.in  or Skype : contact.hiren1188
#
##############################################################################

from odoo import fields, models, _
from odoo.exceptions import UserError


class srAccountPayment(models.Model):
    _inherit = "account.payment"

    bank_charge_amount = fields.Monetary('Bank Charges')

    def _prepare_move_line_default_vals(self, write_off_line_vals=None, force_balance=None):
        line_vals_list = super(srAccountPayment, self)._prepare_move_line_default_vals(write_off_line_vals=write_off_line_vals, force_balance=force_balance)
        if line_vals_list:
            if  self.bank_charge_amount > 0.0:
                if not self.journal_id.default_bank_charge_account_id:
                    raise UserError('Please first configure Bank Charge Account from Invoicing Configuration -> Journals -> Bank(Extra Bank Charge Account)')
                for line in line_vals_list:
                    if line.get('debit') == 0.0:
                        amount_currency = line.get('amount_currency') + (-self.bank_charge_amount)
                        credit = line.get('credit') + self.bank_charge_amount
                        line.update({'credit': credit, 'amount_currency': amount_currency})
                
                line_vals_list.append(
                {
                    'name': "Bank Charges Payments",
                    'date_maturity': self.date,
                    'amount_currency': self.bank_charge_amount or 0.0 or 0.0,
                    'currency_id': self.currency_id.id,
                    'debit': self.bank_charge_amount or 0.0 or 0.0,
                    'credit': 0.0,
                    'partner_id': self.partner_id.id,
                    'account_id': self.journal_id.default_bank_charge_account_id.id,
                }
                )
        return line_vals_list
