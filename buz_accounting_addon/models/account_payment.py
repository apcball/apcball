from odoo import _, fields, models
from odoo.exceptions import UserError


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    buz_payment_channel = fields.Selection(
        [
            ('bank_transfer', '\u0e42\u0e2d\u0e19\u0e40\u0e07\u0e34\u0e19'),
            ('cash', '\u0e40\u0e07\u0e34\u0e19\u0e2a\u0e14'),
            ('cheque', '\u0e40\u0e0a\u0e47\u0e04'),
            ('card', '\u0e1a\u0e31\u0e15\u0e23\u0e40\u0e04\u0e23\u0e14\u0e34\u0e15/\u0e40\u0e14\u0e1a\u0e34\u0e15'),
            ('other', '\u0e2d\u0e37\u0e48\u0e19 \u0e46'),
        ],
        string='\u0e0a\u0e48\u0e2d\u0e07\u0e17\u0e32\u0e07\u0e01\u0e32\u0e23\u0e0a\u0e33\u0e23\u0e30\u0e40\u0e07\u0e34\u0e19\u0e08\u0e23\u0e34\u0e07',
        copy=False,
        tracking=True,
        help='\u0e0a\u0e48\u0e2d\u0e07\u0e17\u0e32\u0e07\u0e17\u0e35\u0e48\u0e25\u0e39\u0e01\u0e04\u0e49\u0e32\u0e0a\u0e33\u0e23\u0e30\u0e40\u0e07\u0e34\u0e19\u0e08\u0e23\u0e34\u0e07 \u0e43\u0e0a\u0e49\u0e2a\u0e33\u0e2b\u0e23\u0e31\u0e1a\u0e41\u0e2a\u0e14\u0e07\u0e1a\u0e19 Receipt Voucher \u0e40\u0e17\u0e48\u0e32\u0e19\u0e31\u0e49\u0e19',
    )

    received_date = fields.Date(
        string='Received date',
        default=fields.Date.context_today,
        copy=False,
        tracking=True,
        help='วันที่รับชำระเงินจริง แยกจาก Payment Date ซึ่งเป็นวันที่ลงบัญชี',
    )

    buz_payment_voucher_id = fields.Many2one(
        'account.payment.voucher', string='Payment Voucher',
        ondelete='set null', index=True, copy=False,
    )
    buz_customer_refund_pv_id = fields.Many2one(
        'buz.customer.refund.pv', string='Customer Refund PV',
        ondelete='set null', index=True, copy=False,
    )

    def write(self, vals):
        if 'received_date' in vals:
            received_date = fields.Date.to_date(vals['received_date'])
            posted_customer_payments = self.filtered(
                lambda payment: payment.state == 'posted'
                and payment.partner_type == 'customer'
                and payment.payment_type in ('inbound', 'receive')
                and payment.received_date != received_date
            )
            if posted_customer_payments:
                raise UserError(_('Received date cannot be changed after posting.'))
        return super().write(vals)

    def action_post(self):
        customer_payments = self.filtered(
            lambda payment: payment.partner_type == 'customer'
            and payment.payment_type in ('inbound', 'receive')
            and not payment.buz_payment_channel
        )
        if customer_payments:
            raise UserError(_(
                '\u0e01\u0e23\u0e38\u0e13\u0e32\u0e40\u0e25\u0e37\u0e2d\u0e01\u0e0a\u0e48\u0e2d\u0e07\u0e17\u0e32\u0e07\u0e01\u0e32\u0e23\u0e0a\u0e33\u0e23\u0e30\u0e40\u0e07\u0e34\u0e19\u0e08\u0e23\u0e34\u0e07\u0e01\u0e48\u0e2d\u0e19 Post Customer Payment'
            ))
        return super().action_post()
