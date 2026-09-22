{
    "name": "BOM Excel Report",
    "version": "17.0.1.0.3",
    "category": "Manufacturing",
    "summary": "Export all Bills of Materials to a fixed-format Excel report",
    "description": "Export first-level BOM components to Excel with fixed columns.",
    "author": "Mogen Co., Ltd.",
    "license": "LGPL-3",
    "depends": ["mrp", "report_xlsx"],
    "data": [
        "security/ir.model.access.csv",
        "wizard/bom_excel_wizard_views.xml",
        "views/bom_excel_menu.xml",
        "report/bom_excel_report_action.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
