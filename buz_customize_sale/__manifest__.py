{
    'name': 'Customize Sale Order Form',
    'version': '17.0.1.0.0',
    'category': 'Sales',
    'summary': 'Customize Sale Order Form View',
    'description': """
        This module customizes the sale order form view:
        - Moves warehouse field after quotation template
    """,
    'depends': ['sale_stock', 'sale_management'],
    'data': [
        'views/sale_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}