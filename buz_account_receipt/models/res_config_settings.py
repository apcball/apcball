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

