from odoo import fields, models

class ResCompany(models.Model):
    _inherit = "res.company"

    payment_voucher_checker1_id = fields.Many2one(
        "res.users",
        string="Payment Voucher Checker (1)",
        help="User responsible for first check of payment vouchers."
    )
    
    payment_voucher_checker2_id = fields.Many2one(
        "res.users",
        string="Payment Voucher Checker (2)",
        help="User responsible for second check of payment vouchers."
    )

    payment_voucher_approver_id = fields.Many2one(
        "res.users",
        string="Payment Voucher Approver",
        help="User responsible for final approval of payment vouchers."
    )

    payment_voucher_enable_approval2 = fields.Boolean(
        string="Enable Second Approval",
        default=False,
        help="Enable a second approval step for payment vouchers."
    )

    payment_voucher_approver2_id = fields.Many2one(
        "res.users",
        string="Payment Voucher Approver (2)",
        help="User responsible for second approval of payment vouchers."
    )
