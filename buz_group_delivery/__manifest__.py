{
    'name': 'Group Delivery Addresses',
    'version': '17.0.1.0.0',
    'category': 'Sales',
    'summary': 'Group delivery addresses in Sale Order',
    'description': """
        This module adds grouping functionality for delivery addresses in Sale Order form.
    """,
    'depends': ['sale_management'],
    'data': [
        'views/sale_order_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}