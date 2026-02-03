from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class GlReportWizard(models.TransientModel):
    _name = "gl.report.wizard"
    _description = "General Ledger Report Wizard"

    target_move = fields.Selection([
        ('posted', 'All Posted Entries'),
        ('all', 'All Entries'),
    ], string='Target Moves', required=True, default='posted')

    sortby = fields.Selection([
        ('sort_date', 'Date'),
        ('sort_journal_partner', 'Journal & Partner'),
    ], string='Sort by', required=True, default='sort_date')

    display_account = fields.Selection([
        ('all', 'All'),
        ('movement', 'With movements'),
        ('not_zero', 'With balance is not equal to 0'),
    ], string='Display Accounts', required=True, default='movement')

    initial_balance = fields.Boolean(string='Include Initial Balances',
                                    help='If you selected Date, this field allow you to add a row to display the amount of debit/credit/balance that corresponds to the column of this date.')

    date_from = fields.Date(string='Start Date')
    date_to = fields.Date(string='End Date')

    journal_ids = fields.Many2many('account.journal', string='Journals', required=True, default=lambda self: self.env['account.journal'].search([]))
    account_ids = fields.Many2many('account.account', string='Accounts')

    def check_report(self):
        self.ensure_one()
        data = {}
        data['ids'] = self.env.context.get('active_ids', [])
        data['model'] = self.env.context.get('active_model', 'ir.ui.menu')
        data['form'] = self.read(['date_from', 'date_to', 'journal_ids', 'target_move', 'sortby', 'display_account', 'initial_balance', 'account_ids'])[0]
        return self._print_report(data)

    def _print_report(self, data):
        data['form'].update(self.read(['date_from', 'date_to', 'journal_ids', 'target_move', 'sortby', 'display_account', 'initial_balance', 'account_ids'])[0])
        return self.env.ref('buz_gl_report_excel.action_report_general_ledger').report_action(self, data=data)

    def check_report_xlsx(self):
        self.ensure_one()
        data = {}
        data['ids'] = self.env.context.get('active_ids', [])
        data['model'] = self.env.context.get('active_model', 'ir.ui.menu')
        data['form'] = self.read(['date_from', 'date_to', 'journal_ids', 'target_move', 'sortby', 'display_account', 'initial_balance', 'account_ids'])[0]
        return self.env.ref('buz_gl_report_excel.action_report_general_ledger_xlsx').report_action(self, data=data)
