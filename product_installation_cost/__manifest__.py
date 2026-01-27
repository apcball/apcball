# -*- coding: utf-8 -*-
{
    'name': 'Product Installation Cost',
    'version': '17.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Add optional installation cost to products and sale orders',
    'description': 'Optional installation cost with Retail/Project pricing controlled by Pricelist',
    'depends': ['sale', 'product'],
    'data': [
        'views/product_views.xml',
        'views/pricelist_views.xml',
        'views/sale_views.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}
