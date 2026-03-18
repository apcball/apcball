{
    'name': 'BOM Version Selector on Sales',
    'version': '17.0.1.0.0',
    'category': 'Manufacturing',
    'summary': 'Select specific BOM version on Sale Order Lines for Manufacturing and Kits.',
    'description': """
        This module allows users to select a specific Bill of Materials (BOM) on Sale Order Lines.
        The selected BOM will be used for:
        - Manufacturing Orders (MO) creation.
        - Kit component explosion in Delivery Orders.
    """,
    'author': 'Your Company',
    'depends': ['sale', 'stock', 'mrp'],
    'data': [
        'views/sale_order_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
