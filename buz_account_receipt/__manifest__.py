{
    "name": "BUZ Account Receipt - Production-Ready Grouped Receipts (AR)",
    "version": "17.0.2.0.0",
    "category": "Accounting",
    "summary": "Production-ready grouped customer receipts with RV-ready architecture",
    "description": """
        Account Receipt Module - AR Side (Customer Receipts)
        ======================================================

        This module provides production-ready grouped receipt functionality for customer invoices.

        Key Features:
        -------------
        * **Grouped Receipts**: Create one receipt for multiple invoices from the same customer
        * **Amount to Collect**: Show amount to collect "this round", not historical paid amounts
        * **Outstanding Payment Fallback**: Create on-account payments when nothing is due
        * **RV-Ready Architecture**: Expose helpers and relations for external Receipt Voucher (RV) modules
        * **Multi-Currency Support**: Proper handling using signed amounts for invoices and refunds
        * **Auto-Post**: Configurable auto-posting upon creation
        * **Payment Traceability**: M2M links between receipts and payments with smart buttons
        * **Robust Validations**: Partner/company enforcement, optional single-currency constraint
        * **Professional Reports**: QWeb PDF with proper columns and totals

        Configuration:
        --------------
        * `buz.receipt_autopost`: Auto-post receipts on creation (default: True)
        * `buz.enforce_single_currency_per_receipt`: Enforce single currency (default: True)
        * `buz.default_bank_journal_id`: Default journal for payments
        * `buz.allow_outstanding_fallback`: Allow outstanding payments (default: True)

        RV-Ready Methods:
        -----------------
        * `receipt_get_unpaid_moves()`: Get invoices with residual > 0
        * `receipt_build_payment_context()`: Build payment wizard context
        * `receipt_link_payments()`: Link payments to receipt for audit
        * `receipt_reconcile_with_payment()`: Auto-reconcile payment with invoices

        Security:
        ---------
        * Accounting Users: Read, Write, Create access
        * Accounting Managers: Full access including delete

        Version: 2.0.0 - Production-Ready Release
        Author: Ball & Manow
    """,
    "author": "Ball & Manow",
    "website": "https://example.com",
    "depends": ["account", "mail"],
    "data": [
        "data/sequence.xml",
        "security/ir.model.access.csv",
        "views/account_move_views.xml",
        "views/account_receipt_views.xml",
        "views/account_receipt_voucher_views.xml",
        "views/account_payment_voucher_views.xml",
        "views/account_payment_register_wizard_views.xml",
        "views/bill_display_wizard_views.xml",
        "views/bill_register_payment_wizard_views.xml",
        "views/account_invoice_receipt_action.xml",
        "views/res_partner_receipt_action.xml",
        "views/res_config_settings_views.xml",
        "reports/payment_receipt_report.xml",
        "reports/payment_receipt_template.xml",
        "reports/receipt_voucher_report.xml",
        "reports/receipt_voucher_template.xml",
        "reports/payment_voucher_report.xml",
        "reports/payment_voucher_template.xml"
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
    "license": "LGPL-3"
}