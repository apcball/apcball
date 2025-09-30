
{
    "name": "buz Account Receipt (Grouped Receipt)",
    "version": "17.0.1.0.0",
    "category": "Accounting",
    "summary": "Create a single Receipt document that groups multiple invoices by partner and date range",
    "description": "Generate and print a grouped customer receipt (one receipt for multiple invoices).",
    "author": "Ball & Manow",
    "website": "https://example.com",
    "depends": ["account"],
    "data": [
        "data/sequence.xml",
        "views/account_receipt_views.xml",
        "views/account_invoice_receipt_action.xml",
        "views/res_partner_receipt_action.xml",
        "reports/payment_receipt_report.xml",
        "reports/payment_receipt_template.xml",
        "security/ir.model.access.csv"
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3"
}
