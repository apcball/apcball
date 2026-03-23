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
        line_vals_list = super(srAccountPayment, self)._prepare_move_line_default_vals(
            write_off_line_vals=write_off_line_vals, force_balance=force_balance
        )
        if not line_vals_list or not (self.bank_charge_amount > 0.0):
            return line_vals_list

        if not self.journal_id.default_bank_charge_account_id:
            raise UserError(
                'Please first configure Bank Charge Account from Invoicing Configuration '
                '-> Journals -> Bank(Extra Bank Charge Account)'
            )

        # ── Currency helpers ────────────────────────────────────────────
        thb_currency = self.bank_charge_currency_id
        company_currency = self.company_id.currency_id

        # bank_charge in company currency (for debit/credit amounts)
        if thb_currency != company_currency:
            bank_charge_company = thb_currency._convert(
                self.bank_charge_amount, company_currency,
                self.company_id, self.date
            )
        else:
            bank_charge_company = self.bank_charge_amount

        # bank_charge in payment currency (for amount_currency on payment lines)
        bank_charge_payment_cur = self._get_bank_charge_in_payment_currency()

        # Odoo 17: amount_currency must strictly equal (debit - credit) for same currency
        is_same_currency = (self.currency_id == company_currency)

        # ── Identify the bank/liquidity line ────────────────────────────
        # Use default_account_id from the journal; also collect all account IDs
        # whose account_type is 'asset_cash' to handle outstanding payment accounts.
        # This avoids touching write-off or AR lines.
        liquidity_account_ids = set()
        if self.journal_id.default_account_id:
            liquidity_account_ids.add(self.journal_id.default_account_id.id)
        # Also add any other cash/bank-type accounts referenced in existing lines
        all_account_ids = [line.get('account_id') for line in line_vals_list if line.get('account_id')]
        if all_account_ids:
            cash_accounts = self.env['account.account'].sudo().search([
                ('id', 'in', all_account_ids),
                ('account_type', '=', 'asset_cash'),
            ])
            liquidity_account_ids.update(cash_accounts.ids)


        # ── Adjust the bank (liquidity) line only ───────────────────────
        for line in line_vals_list:
            if line.get('account_id') not in liquidity_account_ids:
                continue  # skip write-off, AR, and other lines

            if self.payment_type == 'inbound':
                # Inbound: bank is a debit line — reduce debit by bank charge
                new_debit = line.get('debit', 0.0) - bank_charge_company
                line['debit'] = new_debit
                if is_same_currency:
                    line['amount_currency'] = new_debit - line.get('credit', 0.0)
                else:
                    line['amount_currency'] = line.get('amount_currency', 0.0) - bank_charge_payment_cur
            else:
                # Outbound: bank is a credit line — increase credit by bank charge
                new_credit = line.get('credit', 0.0) + bank_charge_company
                line['credit'] = new_credit
                if is_same_currency:
                    line['amount_currency'] = line.get('debit', 0.0) - new_credit
                else:
                    line['amount_currency'] = line.get('amount_currency', 0.0) - bank_charge_payment_cur

        # ── Add bank charge expense line (always a debit) ───────────────
        bank_charge_line = {
            'name': f"Bank Charges Payments ({self.bank_charge_amount:.2f} THB)",
            'date_maturity': self.date,
            'debit': bank_charge_company,
            'credit': 0.0,
            'partner_id': self.partner_id.id,
            'account_id': self.journal_id.default_bank_charge_account_id.id,
            'currency_id': self.currency_id.id,
            # Debit line: amount_currency > 0 always
            #   same currency → must equal debit exactly
            #   foreign       → use payment-currency equivalent
            'amount_currency': bank_charge_company if is_same_currency else bank_charge_payment_cur,
        }
        line_vals_list.append(bank_charge_line)
        return line_vals_list

