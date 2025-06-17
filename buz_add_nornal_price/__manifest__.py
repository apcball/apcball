# -*- coding: utf-8 -*-
{
    'name': 'buz_add_nornal_price',
    'version': '17.0.1.0.0',
    'category': 'Product',
    'summary': 'Add Normal Price field to product.template form and display in sale order lines',
    'author': 'Your Company',
    'website': 'http://www.example.com',
    'depends': ['product', 'sale_management'],
    'data': [
        'views/product_template_views.xml',
        'views/sale_order_line_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
