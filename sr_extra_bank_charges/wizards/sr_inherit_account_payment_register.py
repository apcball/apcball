# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) Sitaram Solutions (<https://sitaramsolutions.in/>).
#
#    For Module Support : info@sitaramsolutions.in  or Skype : contact.hiren1188
#
##############################################################################

from odoo import fields, models, api


class srAccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'
    
    journal_type = fields.Selection(related='journal_id.type')
    bank_charge_amount = fields.Monetary(string="Bank Charges (THB)", currency_field='bank_charge_currency_id')
    bank_charge_currency_id = fields.Many2one('res.currency', string='Bank Charge Currency', 
                                               default=lambda self: self.env.ref('base.THB'), 
                                               readonly=True)

    def _create_payment_vals_from_wizard(self, batch_result):
        payment_vals = super(srAccountPaymentRegister,self)._create_payment_vals_from_wizard(batch_result)
        if payment_vals:
            payment_vals.update({
                'bank_charge_amount': self.bank_charge_amount,
                'bank_charge_currency_id': self.bank_charge_currency_id.id,
            })
        return payment_vals

