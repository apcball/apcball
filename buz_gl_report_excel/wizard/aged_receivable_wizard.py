from odoo import api, fields, models, _

class AgedReceivableWizard(models.TransientModel):
    _name = 'aged.receivable.wizard'
    _description = 'Aged Receivable Report Wizard'

    direction_selection = fields.Selection([
        ('past', 'Future'),
        ('future', 'Past'),
    ], string='Aging Method', required=True, default='past')

    date_from = fields.Date(string='Start Date', required=True, default=lambda self: fields.Date.context_today(self))
    date_to = fields.Date(string='End Date', required=True, default=lambda self: fields.Date.context_today(self))

    period_length = fields.Integer(string='Period Length (days)', required=True, default=30)

    target_move = fields.Selection([
        ('posted', 'All Posted Entries'),
        ('all', 'All Entries'),
    ], string='Target Moves', required=True, default='posted')

    show_uncleared_items = fields.Boolean(string='Show Uncleared Items', default=True)

    partner_ids = fields.Many2many('res.partner', string='Partners')
    account_ids = fields.Many2many('account.account', string='Accounts')

    journal_ids = fields.Many2many('account.journal', string='Journals')

    def check_report_xlsx(self):
        self.ensure_one()
        data = {}
        data['ids'] = self.env.context.get('active_ids', [])
        data['model'] = self.env.context.get('active_model', 'ir.ui.menu')
        data['form'] = self.read(['date_from', 'date_to', 'direction_selection', 
                                   'period_length', 'target_move', 'show_uncleared_items', 
                                   'partner_ids', 'account_ids', 'journal_ids'])[0]
        return self.env.ref('buz_gl_report_excel.action_report_aged_receivable_xlsx').report_action(self, data=data)
