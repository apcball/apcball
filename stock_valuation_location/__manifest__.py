{
    "name": "buz Stock Valuation Location",
    "version": "17.0.1.0.1",
    "summary": "Add Location Information to Stock Valuation (Performance Fixed)",
    "category": "Inventory/Accounting",
    "author": "Apcball",
    "website": "https://mogdev.work",
    "license": "LGPL-3",
    "depends": ["stock_account"],
    "data": [
        "security/stock_valuation_location_groups.xml",
        "security/ir.model.access.csv",
        "views/stock_valuation_layer_views.xml",
        "views/stock_valuation_location_fast_sql_wizard_views.xml",
        "views/stock_valuation_location_menu.xml",
        # ORM Recompute and Cron removed - use SQL Fast Path for large databases
    ],
    "assets": {},
    "installable": True,
    "auto_install": False,
}
