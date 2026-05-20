{
    "name": "DP Excel Report",
    "version": "17.0.1.0.0",
    "category": "Sales",
    "summary": "Export DP report from Sale Orders to Excel",
    "author": "OpenAI",
    "license": "LGPL-3",
    "depends": [
        "sale_management",
        "account",
        "stock",
        "report_xlsx",
    ],
    "data": [
        "security/ir.model.access.csv",
        "wizard/dp_report_wizard_views.xml",
        "sale/report/report_action.xml",
    ],
    "installable": True,
    "application": False,
}
