{
    "name": "Picking Return Report (Excel)",
    "version": "17.0.1.0.0",
    "category": "Inventory/Reporting",
    "summary": "Excel report of pickings that have returns: source doc, return doc, moves, locations",
    "author": "Mogen Co., Ltd.",
    "license": "LGPL-3",
    "depends": ["stock"],
    "data": [
        "security/ir.model.access.csv",
        "wizard/picking_return_report_wizard_views.xml",
    ],
    "installable": True,
    "application": False,
}
