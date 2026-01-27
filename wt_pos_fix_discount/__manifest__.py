# -*- coding: utf-8 -*-
{
    "name": "buz Pos Fix Discount",
    "version": "17.0.0.1",
    "category": "Sales/Point of Sale",
    "summary": "Pos Fix Discount",
    "description": """Pos Fix Discount""",
    "author": "Warlock Technologies Pvt Ltd.",
    "website": "http://warlocktechnologies.com",
    "support": "info@warlocktechnologies.com",
    "depends": ['base','point_of_sale'],
    "data": [
        "views/pos_order.xml",
    ],
    'assets':{
        'point_of_sale._assets_pos': [
            "/wt_pos_fix_discount/static/src/apps/screens/product_screen/fix_discount_button/fix_discount_button.xml",
            "/wt_pos_fix_discount/static/src/apps/screens/product_screen/fix_discount_button/fix_discount_button.js",
            "/wt_pos_fix_discount/static/src/apps/store/models.js",
            "/wt_pos_fix_discount/static/src/apps/screens/product_screen/orderline/orderline.xml",
        ],
    },
    "images": ["static/images/screen_image.png"],
    "price": 0.0,
    "currency": "USD",
    'sequence': 4,
    "application": True,
    "installable": True,
    "auto_install": False,
    "image": [""],
    "license": "OPL-1",
}
