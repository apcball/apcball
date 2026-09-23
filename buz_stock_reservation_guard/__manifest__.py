# -*- coding: utf-8 -*-
{
    "name": "Buz Stock Reservation Guard",
    "version": "17.0.1.2.0",
    "category": "Inventory",
    "summary": "Block manual reservations from source locations without stock",
    "description": """
        Prevent stock move lines from reserving stock at an exact source
        location when that location has no real on-hand quantity available.

        Also blocks MRP production (button_mark_done) from consuming raw
        material lines whose exact source location doesn't have enough
        physical stock - a gap the move-line guard can't cover, since raw
        material consumption moves carry no stock.picking and are already
        'done' by the time their quantity is finalized.
    """,
    "author": "Your Company",
    "website": "https://www.yourcompany.com",
    "license": "LGPL-3",
    "depends": [
        "stock",
        "mrp",
    ],
    "data": [
        "views/res_config_settings_views.xml",
        "views/stock_picking_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
