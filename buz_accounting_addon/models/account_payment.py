from odoo import fields, models


class AccountPayment(models.Model):
    _inherit = "account.payment"

    buz_payment_voucher_id = fields.Many2one(
        "account.payment.voucher",
        string="Payment Voucher",
        ondelete="set null",
        index=True,
        copy=False,
    )
    buz_customer_refund_voucher_id = fields.Many2one(
        "buz.customer.refund.voucher",
        string="Customer Refund Voucher",
        ondelete="set null",
        index=True,
        copy=False,
    )
