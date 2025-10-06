
{
    "name": "buz Account Receipt (Grouped Receipt)",
    "version": "17.0.1.0.0",
    "category": "Accounting",
    "summary": "Create a single Receipt document that groups multiple invoices by partner and date range",
    "description": "Generate and print a grouped customer receipt (one receipt for multiple invoices).",
    "author": "Ball & Manow",
    "website": "https://example.com",
    "depends": ["account", "account_payment"],
    "data": [
        "data/sequence.xml",
        "security/ir.model.access.csv",
        "views/account_receipt_views.xml",
        "views/account_receipt_voucher_views.xml",
        "views/account_payment_voucher_views.xml",
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
    "license": "LGPL-3"
}
