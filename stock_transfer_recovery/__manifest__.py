{
    'name': 'Stock Transfer Recovery',
    'version': '17.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Safely recreate missing or canceled stock transfers from Sales and Purchase Orders.',
    'description': """
        This module provides logic to recreate missing Delivery Orders or Receipts from
        Sale Orders and Purchase Orders, while ensuring no double-delivery or double-receipt
        occurs by calculating accurately based on currently delivered/received quantities.
    """,
    'author': 'Antigravity',
    'website': 'https://www.example.com',
    'depends': ['sale_stock', 'purchase_stock'],
    'data': [
        'security/ir.model.access.csv',
        'wizard/stock_transfer_recreate_wizard_views.xml',
        'views/sale_order_views.xml',
        'views/purchase_order_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
