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
    buz_customer_refund_voucher_id = fields.Many2one(
        'buz.customer.refund.voucher',
        string='Customer Refund PV',
        ondelete='restrict',
        index=True,
        copy=False,
    )

