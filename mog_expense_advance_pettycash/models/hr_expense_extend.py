
# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools import float_round

class HrExpenseSheet(models.Model):
    _inherit = 'hr.expense.sheet'

    payment_source = fields.Selection([('company','Company (AP/Bank)'), ('petty_cash','Petty Cash'), ('advance','Advance')],
                                      string='Payment Source', default='company', required=True, tracking=True)
    petty_cash_box_id = fields.Many2one('account.petty.cash.box', string='Petty Cash Box')
    advance_id = fields.Many2one('hr.expense.advance', string='Advance Used',
                                domain="[('state', '=', 'paid'), '|', ('employee_id', '=', employee_id), ('partner_id', '=', partner_id)]")
    partner_id = fields.Many2one('res.partner', string='Partner (if non-employee)')

    @api.onchange('payment_source')
    def _onchange_payment_source(self):
        """Clear fields when payment source changes"""
        if self.payment_source != 'petty_cash':
            self.petty_cash_box_id = False
        if self.payment_source != 'advance':
            self.advance_id = False

    def action_post_entries(self):
        """Hook called after approving to create accounting based on source.
        NOTE: this is a simplified example; adapt to company policies.
        """
        res = super().action_post_entries()
        for sheet in self:
            if sheet.payment_source == 'petty_cash':
                if not sheet.petty_cash_box_id:
                    raise UserError(_('Select petty cash box.'))
                petty_cash_journal = sheet.petty_cash_box_id.journal_id
                if not petty_cash_journal or not petty_cash_journal.default_account_id:
                    raise UserError(_('Define default account on petty cash journal.'))

                # Read configured expense journal from ir.config_parameter for this company
                IrConfig = self.env['ir.config_parameter'].sudo()
                cfg_key = 'mog.petty_cash.expense_journal_id'
                cfg_val = IrConfig.get_param(cfg_key, default=False, company_id=sheet.company_id.id)
                if not cfg_val:
                    raise UserError(_('Petty Cash Expense Journal is not configured for company %s.') % (sheet.company_id.name,))
                expense_journal = self.env['account.journal'].browse(int(cfg_val))
                if not expense_journal or expense_journal.type in ('bank', 'cash'):
                    raise UserError(_('Configured Petty Cash Expense Journal is invalid. Choose a General/Misc journal.'))

                # Aggregate amounts by expense account (including tax amounts where applicable)
                totals_by_account = {}
                currency = sheet.currency_id or sheet.company_id.currency_id
                prec = sheet.company_id.currency_id.decimal_places
                for line in sheet.expense_line_ids:
                    acct = line.account_id or (
                        line.product_id and line.product_id.property_account_expense_id) or (
                        line.product_id and line.product_id.categ_id and line.product_id.categ_id.property_account_expense_categ_id)
                    if not acct:
                        raise UserError(_('Expense line %s has no expense account defined.') % (line.name or line.id))

                    # Amount should be converted to company currency if needed. For simplicity assume amounts are company currency.
                    amt = float_round(line.total_amount, precision_digits=prec)
                    totals_by_account[acct.id] = totals_by_account.get(acct.id, 0.0) + amt

                    # Add tax amounts to their tax accounts (if tax has account_id)
                    # For now, include tax amounts on separate tax accounts if present
                    for tax_line in line.tax_line_ids:
                        tax_account = tax_line.account_id
                        if tax_account and tax_line.amount:
                            t_amt = float_round(tax_line.amount, precision_digits=prec)
                            totals_by_account[tax_account.id] = totals_by_account.get(tax_account.id, 0.0) + t_amt

                # Build move lines: debit expense/tax accounts, credit petty cash cash account
                lines = []
                total_debit = 0.0
                for acct_id, amt in totals_by_account.items():
                    if amt <= 0:
                        continue
                    total_debit += amt
                    lines.append((0, 0, {
                        'name': sheet.name or _('Expense'),
                        'account_id': acct_id,
                        'debit': amt,
                        'credit': 0.0,
                    }))

                if not total_debit:
                    raise UserError(_('No amounts to post for petty cash expense sheet %s') % (sheet.name or sheet.id,))

                lines.append((0, 0, {
                    'name': _('Petty Cash Payment'),
                    'account_id': petty_cash_journal.default_account_id.id,
                    'debit': 0.0,
                    'credit': total_debit,
                }))

                move_vals = {
                    'move_type': 'entry',
                    'journal_id': expense_journal.id,
                    'date': sheet.accounting_date or fields.Date.context_today(self),
                    'ref': sheet.name or _('Expense Sheet'),
                    'petty_cash_box_id': sheet.petty_cash_box_id.id,
                    'line_ids': lines,
                }
                move = self.env['account.move'].create(move_vals)
                # Post the move
                move._post()
            elif sheet.payment_source == 'advance':
                if not sheet.advance_id:
                    raise UserError(_('Select advance to clear.'))
                
                # Validate advance is in paid state
                if sheet.advance_id.state != 'paid':
                    raise UserError(_('Advance must be in "Paid" state to be cleared.'))
                
                # Validate there's sufficient balance
                if sheet.advance_id.balance_amount < sheet.total_amount:
                    raise UserError(_('Insufficient advance balance. Available: %s, Required: %s') % (
                        sheet.advance_id.balance_amount, sheet.total_amount))
                
                # Create a clearing record and automatically post it
                clearing = self.env['hr.expense.advance.clearing'].create({
                    'advance_id': sheet.advance_id.id,
                    'expense_sheet_id': sheet.id,
                    'amount': sheet.total_amount,
                })
                clearing.action_post()  # Automatically post the clearing
        return res
