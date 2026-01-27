# -*- coding: utf-8 -*-
{
    "name": "BUZ Validate Control",
    "summary": "Control access to Validate/Post buttons in Stock documents",
    "version": "17.0.1.0.0",
    "category": "Extra Tools",
    "author": "BUZ Team",
    "license": "LGPL-3",
    "depends": [
        "stock",
        "base",
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/stock_picking_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}