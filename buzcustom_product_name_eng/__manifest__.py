{
    'name': 'Product Name English',
    'version': '17.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Add English name field for products',
    'description': """
        This module adds English name field for products:
        - Adds name_eng field under product name
        - Allows storing product names in English
    """,
    'depends': ['product'],
    'data': [
        'views/product_template_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}