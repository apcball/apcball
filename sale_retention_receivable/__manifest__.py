{
    "name": "Sale Retention Receivable",
    "version": "17.0.1.0.0",
    "summary": "Manage sales retention receivable for customer invoices",
    "description": """
        Handle sales retention receivable when customers deduct retention from payment.
        Keeps invoices fully paid while tracking retained amounts separately.
    """,
    "author": "Your Company",
    "website": "https://www.yourcompany.com",
    "category": "Accounting/Accounting",
    "depends": [
        "sale",
        "account",
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/res_partner_views.xml",
        "views/res_config_settings_views.xml",
        "views/sale_order_views.xml",
        "views/account_move_views.xml",
        "views/sale_retention_receivable_views.xml",
        "views/menu_views.xml",
        "reports/retention_aging_report.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
    "license": "LGPL-3",
}