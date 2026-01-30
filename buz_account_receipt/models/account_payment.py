from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

class AccountPayment(models.Model):
    _inherit = 'account.payment'
    
    # WHT functionality has been removed - use l10n_th_account_tax module for withholding tax features

