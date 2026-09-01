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
        string='Customer Refund Voucher',
        ondelete='set null',
        index=True,
        copy=False,
    )

    def action_draft(self):
        res = super().action_draft()
        # Early exit if no CV backlink context
        for payment in self:
            cv = payment.buz_customer_refund_voucher_id
            if not cv:
                continue
            # move CV to payment_cancelled when payment is reset to draft (uncancelled part of cancel flow)
            # actual transition is handled in action_cancel -> use same
            try:
                if cv.state == 'registered':
                    cv.write({'state': 'payment_cancelled'})
                    cv.message_post(body=_("Refund Payment %s cancelled — CV set to Payment Cancelled.") % payment.name)
            except Exception:
                pass
        return res

    def action_cancel(self):
        res = super().action_cancel()
        for payment in self:
            cv = payment.buz_customer_refund_voucher_id
            if not cv:
                continue
            if cv.state == 'registered':
                try:
                    cv.write({'state': 'payment_cancelled'})
                    cv.message_post(body=_("Refund Payment %s cancelled — CV set to Payment Cancelled.") % payment.name)
                except Exception:
                    pass
        return res

