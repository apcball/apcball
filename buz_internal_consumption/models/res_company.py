from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    ic_default_expense_account_id = fields.Many2one(
        'account.account',
        string='Default Expense Account for IC',
        domain=[('deprecated', '=', False)]
    )
    ic_default_consumption_location_id = fields.Many2one(
        'stock.location',
        string='Default Consumption Location',
        domain=[('usage', '=', 'consume')]
    )
    ic_default_journal_id = fields.Many2one(
        'account.journal',
        string='Default Journal for Manual JE',
        domain=[('type', '=', 'general')]
    )
    ic_auto_post_journal_entries = fields.Boolean(
        string='Auto Post Journal Entries',
        default=False
    )
    ic_costing_policy = fields.Selection([
        ('valuation_based', 'Valuation Based'),
        ('standard_cost', 'Standard Cost'),
        ('fifo_layer', 'FIFO Layer'),
    ], string='Default Costing Policy', default='standard_cost'
    )