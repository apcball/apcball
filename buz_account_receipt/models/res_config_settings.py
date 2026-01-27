# -*- coding: utf-8 -*-

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # Existing receipt settings
    buz_receipt_autopost = fields.Boolean(
        string="Auto-Post Receipts",
        config_parameter='buz_account_receipt.receipt_autopost',
        help="Automatically post receipts after creation"
    )
    
    buz_enforce_single_currency_per_receipt = fields.Boolean(
        string="Enforce Single Currency per Receipt",
        config_parameter='buz_account_receipt.enforce_single_currency',
        help="All invoices in a receipt must have the same currency"
    )
    
    buz_allow_outstanding_fallback = fields.Boolean(
        string="Allow Outstanding Payment Fallback",
        config_parameter='buz_account_receipt.allow_outstanding_fallback',
        default=True,
        help="When no unpaid invoices exist, allow creating on-account payments"
    )
    
    buz_default_bank_journal_id = fields.Many2one(
        'account.journal',
        string="Default Bank Journal",
        config_parameter='buz_account_receipt.default_bank_journal_id',
        domain=[('type', 'in', ('bank', 'cash'))],
        help="Default journal to use for creating on-account payments"
    )
    
    # New: Outstanding as Paid setting
    ar_outstanding_as_paid = fields.Boolean(
        string="Consider Outstanding Receipts as Paid",
        config_parameter='buz_account_receipt.ar_outstanding_as_paid',
        default=True,
        help="If enabled, customer invoices reconciled with Outstanding Receipts account "
             "will be considered as 'Paid' instead of 'In Payment'.\n"
             "If disabled, invoices will remain 'In Payment' until reconciled with bank statements."
    )

    payment_voucher_checker1_id = fields.Many2one(
        related='company_id.payment_voucher_checker1_id',
        string="Payment Voucher Checker (1)",
        readonly=False,
        help="User responsible for first check of payment vouchers."
    )
    
    payment_voucher_checker2_id = fields.Many2one(
        related='company_id.payment_voucher_checker2_id',
        string="Payment Voucher Checker (2)",
        readonly=False,
        help="User responsible for second check of payment vouchers."
    )

    payment_voucher_approver_id = fields.Many2one(
        related='company_id.payment_voucher_approver_id',
        string="Payment Voucher Approver",
        readonly=False,
        help="User responsible for approving payment vouchers."
    )

