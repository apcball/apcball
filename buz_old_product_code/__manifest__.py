{
    'name': 'Product Old Code Reference',
    'version': '17.0.1.0.0',
    'category': 'Inventory',
    'summary': 'Add old product code field for reference',
    'description': """
        This module adds an old product code field to products
        to help track and search products by their previous codes.
    """,
    'author': 'Buzzer',
    'website': 'https://www.yourcompany.com',
    'depends': ['product'],
    'data': [
        'views/product_template_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}