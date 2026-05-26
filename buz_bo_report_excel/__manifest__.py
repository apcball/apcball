{
    "name": "buz BO Report Excel",
    "version": "17.0.1.0.0",
    "category": "Purchases",
    "summary": "Export Purchase Blanket Orders (Purchase Agreements) to Excel",
    "description": """
        Export purchase.requisition (Purchase Agreement / Blanket Order) to Excel.
        Features:
        - Wizard to filter by date range, vendor, state
        - Export selected or all records to .xlsx
        - Support export from form view (single) and tree view (multiple)
    """,
    "author": "Ball",
    "license": "LGPL-3",
    "depends": ["purchase"],
    "data": [
        "security/ir.model.access.csv",
        "wizard/bo_report_excel_wizard_views.xml",
        "views/purchase_requisition_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
