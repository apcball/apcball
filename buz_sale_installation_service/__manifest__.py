# -*- coding: utf-8 -*-
{
    'name': 'Sale Installation Service',
    'version': '17.0.1.0.0',
    'category': 'Sales',
    'summary': 'Add installation service fees to sale orders automatically',
    'description': """
        Sale Installation Service
        =========================
        
        Features:
        ---------
        * Add installation fee to products
        * Automatically create installation service lines in sale orders
        * Sync quantities between product and installation lines
        * Separate revenue accounting for installation fees
        * Company-level default installation service product
        * Protection against manual manipulation of installation lines
    """,
    'author': 'Buz',
    'website': '',
    'depends': [
        'sale_management',
        'product',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/installation_service_product.xml',
        'views/product_views.xml',
        'views/sale_order_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
    'post_init_hook': 'post_init_hook',
}
