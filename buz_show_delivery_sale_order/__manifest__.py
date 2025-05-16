{
    'name': 'Show Delivery Address in Sale Order',
    'version': '17.0.1.0.0',
    'category': 'Sales',
    'summary': 'Display full delivery address in sale order form',
    'description': """
        This module adds the functionality to display the full delivery address
        in the sale order form view.
    """,
    'author': 'Buzzer',
    'website': 'https://www.buzzer.com',
    'depends': ['sale', 'delivery'],
    'data': [
        'views/sale_order_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
    'license': 'LGPL-3',
}