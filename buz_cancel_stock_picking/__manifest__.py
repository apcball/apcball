{
    'name': 'Buz Cancel Stock Picking',
    'version': '17.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Bulk cancel stock pickings from list view',
    'description': """
        This module allows users to select multiple stock picking records from the list view
        and cancel them in batch, properly unreserving them if necessary, 
        and handling errors gracefully without rolling back the entire transaction.
    """,
    'author': 'Buz',
    'depends': ['stock'],
    'data': [
        'security/ir.model.access.csv',
        'data/server_action.xml',
        'views/stock_picking_bulk_cancel_log_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
