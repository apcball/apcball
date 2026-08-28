{
    "name": "BUZ Stock Freeze",
    "version": "17.0.1.0.0",
    "category": "Inventory/Inventory",
    "summary": "Freeze stock movements during inventory counting",
    "description": """
BUZ Stock Freeze
================
Lock stock movements for selected warehouses / locations during a physical
inventory count.

- Freeze Period document with warehouse / location scope, start & end datetime
- Backend enforcement at stock.move._action_done() - covers pickings, MRP,
  scrap, unbuild, barcode, import and API
- Inventory counting and Inventory Adjustment stay allowed (configurable)
- Stock Freeze Manager / Override security groups with audit trail
- Automatic activation / deactivation cron
""",
    "author": "Mogen Co.",
    "website": "https://www.mogen.co.th",
    "license": "LGPL-3",
    "depends": [
        "stock",
        "mrp",
        "mail",
    ],
    "data": [
        "security/stock_freeze_security.xml",
        "security/ir.model.access.csv",
        "data/stock_freeze_cron.xml",
        "views/stock_freeze_period_views.xml",
        "views/stock_picking_views.xml",
        "views/menu_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
