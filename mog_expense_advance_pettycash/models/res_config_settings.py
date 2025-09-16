
# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    petty_cash_expense_journal_id = fields.Many2one(
        'account.journal',
        string='Petty Cash Expense Journal',
        domain=[('type','in',('general','misc'))],
        help='Journal used to post expense & tax lines when Payment Source = Petty Cash. The petty cash cash account will be credited.'
    )
    petty_cash_tax_mode = fields.Selection(
        [('include','Include taxes in expense lines'),
         ('separate','Post VAT as separate lines (tax accounts)')],
        string='Petty Cash Tax Posting',
        default='separate',
        help='How to post taxes for Petty Cash expenses.'
    )
    petty_cash_skip_tax_invoice_validation = fields.Boolean(
        string='Skip Tax Invoice Validation',
        default=True,
        help='Skip Thai tax invoice number/date validation for petty cash entries. Enable this to allow posting without tax invoice details.'
    )

    def set_values(self):
        res = super().set_values()
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param('mog.petty_cash.expense_journal_id', self.petty_cash_expense_journal_id.id or False)
        icp.set_param('mog.petty_cash.tax_mode', self.petty_cash_tax_mode or 'separate')
        icp.set_param('mog.petty_cash.skip_tax_invoice_validation', self.petty_cash_skip_tax_invoice_validation)
        return res

    @api.model
    def get_values(self):
        res = super().get_values()
        icp = self.env['ir.config_parameter'].sudo()
        journal_id = icp.get_param('mog.petty_cash.expense_journal_id')
        tax_mode = icp.get_param('mog.petty_cash.tax_mode', 'separate')
        skip_validation = icp.get_param('mog.petty_cash.skip_tax_invoice_validation', 'True')
        res.update(
            petty_cash_expense_journal_id=int(journal_id) if journal_id else False,
            petty_cash_tax_mode=tax_mode or 'separate',
            petty_cash_skip_tax_invoice_validation=skip_validation == 'True',
        )
        return res
