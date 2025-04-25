from odoo import models, fields, api, _

class BankStatementMapping(models.Model):
    _name = 'bank.statement.mapping'
    _description = 'Bank Statement Import Mapping'

    profile_id = fields.Many2one('bank.statement.profile', string='Bank Profile', required=True)
    name = fields.Char('Description Pattern', required=True,
                      help='Regular expression pattern to match transaction description')
    partner_id = fields.Many2one('res.partner', string='Partner')
    account_id = fields.Many2one('account.account', string='Account',
                                domain=[('deprecated', '=', False)])
    label = fields.Char('Label Override',
                       help='If set, this label will replace the original transaction description')
    
    _sql_constraints = [
        ('unique_pattern_per_profile',
         'unique(profile_id, name)',
         'Pattern must be unique per profile!')
    ]