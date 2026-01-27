# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Purchase Order Global Discount (Same as Sales Discount Odoo 17.0)',
    'version': '1.0.0',
    'category': 'Purchase',
    'summary': 'Purchase Order Global Discount (Same as Sales Discount Odoo 17.0)',
    'description': """
    Purchase Order Global Discount (Same as Sales Discount Odoo 17.0)
""",
    'license': 'OPL-1',
    'price': 0,
    'currency': 'USD',
    'author': 'Waleed Mohsen',
    'support': 'mohsen.waleed@gmail.com',
    'depends': ['purchase'],
    'data': [
        'security/ir.model.access.csv',
        'wizard/purchase_order_discount_views.xml',
        'views/purchase_order_view.xml',
    ],
    'installable': True,
    'auto_install': False,
    "images": ["static/description/main_screenshot.png"],
}
