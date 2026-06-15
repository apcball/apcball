{
    'name': 'Product Policy Management',
    'version': '17.0.1.0.0',
    'category': 'Sales',
    'summary': 'Restrict editing of product policy fields (sale_ok, purchase_ok, can_be_expensed, can_be_pos)',
    'depends': [
        'product',
        'pos_lite',
    ],
    'data': [
        'security/groups.xml',
        'views/product_template_views.xml',
    ],
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
    'auto_install': False,
}
