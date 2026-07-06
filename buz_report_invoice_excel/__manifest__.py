{
    "name": "Invoice Excel Report",
    "version": "17.0.1.0.0",
    "category": "Sales",
    "summary": "Export Invoice report to Excel",
    "author": "Mogen Co., Ltd.",
    "license": "LGPL-3",
    "depends": [
        "sale_management",
        "account",
        "stock",
        "report_xlsx",
        "buz_dispatch_document",
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "wizard/invoice_report_wizard_views.xml",
        "account/report/report_action.xml",
    ],
    "installable": True,
    "application": False,
}
