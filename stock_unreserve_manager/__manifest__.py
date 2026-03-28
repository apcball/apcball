{
    'name': 'Stock Unreserve Manager',
    'version': '17.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Cancel stock reservations at picking, product, and global levels without breaking stock integrity.',
    'description': """
        Provides fine-grained control over stock reservations:
        - Unreserve individual pickings (assigned/partially available)
        - Force-unreserve any picking (manager-only)
        - Bulk unreserve wizard by picking, product, or all
        - Full audit log for every unreserve action
        - Security group restricts force/bulk operations to managers
    """,
    'author': 'Antigravity',
    'website': 'https://www.example.com',
    'depends': ['stock'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/stock_unreserve_log_views.xml',
        'views/stock_picking_views.xml',
        'wizard/stock_unreserve_wizard_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
