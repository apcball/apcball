{
    "name": "Stock Picking Export Excel",
    "version": "17.0.1.0.0",
    "category": "Inventory",
    "summary": "Export Stock Picking to Excel",
    "description": """
        Export stock picking (receipt, delivery, internal transfer) to Excel.
        Supports single picking immediate download and batch export via wizard.
    """,
    "author": "Antigravity",
    "depends": ["stock", "stock_account"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "wizard/export_wizard_views.xml",
        "wizard/import_wizard_views.xml",
        "views/stock_picking_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
