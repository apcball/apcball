
# -*- coding: utf-8 -*-
{
    "name": "Transit Quick Transfer + No Valuation Locations",
    "version": "17.0.1.0.1",
    "summary": "Create Internal Transfer from Transit and skip valuation for selected locations",
    "author": "Ball & Manow",
    "license": "LGPL-3",
    "depends": ["stock", "stock_account", "purchase_stock"],
    "data": [
        "security/ir.model.access.csv",
        "views/stock_picking_views.xml",
        "views/transit_transfer_wizard_views.xml",
        "views/stock_location_views.xml"
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
