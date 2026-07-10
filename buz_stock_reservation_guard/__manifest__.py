# -*- coding: utf-8 -*-
{
    "name": "Buz Stock Reservation Guard",
    "version": "17.0.1.0.0",
    "category": "Inventory",
    "summary": "Block manual reservations from source locations without stock",
    "description": """
        Prevent stock move lines from reserving stock at an exact source
        location when that location has no real on-hand quantity available.
    """,
    "author": "Your Company",
    "website": "https://www.yourcompany.com",
    "license": "LGPL-3",
    "depends": [
        "stock",
    ],
    "data": [],
    "installable": True,
    "application": False,
    "auto_install": False,
}
