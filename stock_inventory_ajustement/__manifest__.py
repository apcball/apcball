# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
#
# Copyright (c) 2022  - feddad.imad@gmail.com

{
    "name": "buz Stock Inventory Adjustment",
    "version": "17.0.0.0.0",
    "license": "LGPL-3",
    "category": "Inventory/Inventory",
    "summary": "Allows to do an easier follow up of the Inventory Adjustments",
    "author": "feddad.imad@gmail.com",
    "website": "",
    "depends": ["stock","base"],
    "data": [
        "security/ir.model.access.csv",
        "security/security.xml",
        "views/stock_inventory.xml",
        "views/stock_quant.xml",
        "views/stock_move_line.xml",
        # "views/res_config_settings_view.xml",
    ],
    'images': ['static/description/banner.png'],
    "installable": True,
    "application": False,
}
