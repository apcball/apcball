from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

class AccountPayment(models.Model):
    _inherit = 'account.payment'
    
    buz_payment_voucher_id = fields.Many2one(
        'account.payment.voucher',
        string='Payment Voucher',
        ondelete='set null',
        index=True,
        copy=False,
    )

