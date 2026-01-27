from odoo import fields, models

class AccountWhtType(models.Model):
    _name = 'account.wht.type'
    _description = 'Withholding Tax Type'

    name = fields.Char(string='Name', required=True)
    rate = fields.Float(string='Rate (%)', required=True, help="Withholding Tax rate in percentage (e.g., 3.0)")
    account_id = fields.Many2one('account.account', string='WHT Account', required=True, 
                                 domain="[('deprecated', '=', False), ('account_type', 'in', ('liability_current', 'liability_payable'))]")
    active = fields.Boolean(default=True)
