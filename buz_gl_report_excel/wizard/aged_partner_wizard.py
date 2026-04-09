from odoo import api, fields, models, _

class AgedPartnerWizard(models.TransientModel):
    _name = 'aged.partner.wizard'
    _description = 'Aged Partner Report Wizard'

    result_selection = fields.Selection([
        ('customer', 'Receivable Accounts'),
        ('supplier', 'Payable Accounts'),
        ('customer_supplier', 'Receivable and Payable Accounts'),
    ], string='Partner\'s', required=True, default='customer')

    direction_selection = fields.Selection([
        ('past', 'Past'),
        ('future', 'Future'),
    ], string='Aging Method', required=True, default='past')

    date_as_of = fields.Date(string='As of Date', required=True, default=fields.Date.context_today)

    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)
    period_length = fields.Integer(string='Period Length (days)', required=True, default=30)

    target_move = fields.Selection([
        ('posted', 'All Posted Entries'),
        ('all', 'All Entries'),
    ], string='Target Moves', required=True, default='posted')

    partner_ids = fields.Many2many('res.partner', string='Partners')
    account_ids = fields.Many2many('account.account', string='Accounts')
    journal_ids = fields.Many2many('account.journal', string='Journals')

    def check_report_xlsx(self):
        self.ensure_one()
        data = {}
        data['ids'] = self.env.context.get('active_ids', [])
        data['model'] = self.env.context.get('active_model', 'ir.ui.menu')
        
        read_fields = ['date_as_of', 'company_id', 'direction_selection', 
                       'period_length', 'target_move', 
                       'partner_ids', 'account_ids', 'journal_ids']
        read_fields.append('result_selection')
        
        data['form'] = self.read(read_fields)[0]
        return self.env.ref('buz_gl_report_excel.action_report_aged_partner_xlsx').report_action(self, data=data)
