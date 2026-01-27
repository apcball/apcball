    # -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) Sitaram Solutions (<https://sitaramsolutions.in/>).
#
#    For Module Support : info@sitaramsolutions.in  or Skype : contact.hiren1188
#
##############################################################################

from odoo import fields, models, _, api
from odoo.exceptions import UserError


class srAccountPayment(models.Model):
    _inherit = "account.payment"

    journal_type = fields.Selection(related='journal_id.type')
    bank_charge_amount = fields.Monetary('Bank Charges (THB)', currency_field='bank_charge_currency_id')
    bank_charge_currency_id = fields.Many2one('res.currency', string='Bank Charge Currency', 
                                               default=lambda self: self.env.ref('base.THB'), 
                                               readonly=True)
    bank_charge_thb_note = fields.Char('Bank Charge Note', compute='_compute_bank_charge_note', store=True)
    
    @api.depends('bank_charge_amount', 'bank_charge_currency_id')
    def _compute_bank_charge_note(self):
        """Compute a note showing the original THB amount"""
        for payment in self:
            if payment.bank_charge_amount and payment.bank_charge_currency_id:
                payment.bank_charge_thb_note = f"{payment.bank_charge_amount:.2f} {payment.bank_charge_currency_id.name}"
            else:
                payment.bank_charge_thb_note = ""
    
    @api.model
    def _get_thb_currency(self):
        """Get Thai Baht currency"""
        return self.env.ref('base.THB')
    
    def _get_bank_charge_in_payment_currency(self):
        """Convert bank charge from THB to payment currency"""
        if not self.bank_charge_amount or not self.bank_charge_currency_id:
            return 0.0
        
        if self.bank_charge_currency_id == self.currency_id:
            return self.bank_charge_amount
        
        # Convert from THB to payment currency
        return self.bank_charge_currency_id._convert(
            self.bank_charge_amount,
            self.currency_id,
            self.company_id,
            self.date
        )

    def _prepare_move_line_default_vals(self, write_off_line_vals=None, force_balance=None):
        line_vals_list = super(srAccountPayment, self)._prepare_move_line_default_vals(write_off_line_vals=write_off_line_vals, force_balance=force_balance)
        if line_vals_list:
            if self.bank_charge_amount > 0.0:
                if not self.journal_id.default_bank_charge_account_id:
                    raise UserError('Please first configure Bank Charge Account from Invoicing Configuration -> Journals -> Bank(Extra Bank Charge Account)')
                
                # Convert bank charge to payment currency for payment line adjustment
                bank_charge_in_payment_currency = self._get_bank_charge_in_payment_currency()
                
                # Convert bank charge to company currency for accounting entries
                thb_currency = self.bank_charge_currency_id
                bank_charge_company_currency = 0.0
                if thb_currency != self.company_id.currency_id:
                    bank_charge_company_currency = thb_currency._convert(
                        self.bank_charge_amount,
                        self.company_id.currency_id,
                        self.company_id,
                        self.date
                    )
                else:
                    bank_charge_company_currency = self.bank_charge_amount
                
                # Adjust existing payment lines
                for line in line_vals_list:
                    if line.get('debit') == 0.0:  # This is usually the payment line (credit side)
                        amount_currency = line.get('amount_currency') + (-bank_charge_in_payment_currency)
                        credit = line.get('credit') + bank_charge_company_currency
                        line.update({'credit': credit, 'amount_currency': amount_currency})
                
                # Add bank charge line - use same currency as payment to comply with Odoo rules
                bank_charge_line = {
                    'name': f"Bank Charges Payments ({self.bank_charge_amount:.2f} THB)",
                    'date_maturity': self.date,
                    'debit': bank_charge_company_currency,
                    'credit': 0.0,
                    'partner_id': self.partner_id.id,
                    'account_id': self.journal_id.default_bank_charge_account_id.id,
                    'currency_id': self.currency_id.id,  # Use same currency as payment
                    'amount_currency': bank_charge_in_payment_currency,  # Bank charge in payment currency
                }
                
                line_vals_list.append(bank_charge_line)
        return line_vals_list
