{
    'name': 'FIFO Reset Engine',
    'version': '17.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Safely deep-clean inventory by clearing reservations, open pickings, stock quantities, and valuation layers.',
    'description': """
        A robust FIFO reset engine for inventory in Odoo 17 that:
        - Clears all stock reservations
        - Cancels open pickings
        - Resets stock quantities to zero
        - Ensures stock valuation layers (SVL) are zeroed
        - Prepares system for fresh opening inventory import
    """,
    'depends': ['stock', 'stock_account', 'web'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'wizard/fifo_reset_wizard_views.xml',
        'views/fifo_reset_log_views.xml',
        'views/menu_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'fifo_reset_engine/static/src/components/fifo_reset_dashboard/fifo_reset_dashboard.js',
            'fifo_reset_engine/static/src/components/fifo_reset_dashboard/fifo_reset_dashboard.xml',
            'fifo_reset_engine/static/src/components/fifo_reset_dashboard/fifo_reset_dashboard.scss',
            'fifo_reset_engine/static/src/components/fifo_reset_result/fifo_reset_result.js',
            'fifo_reset_engine/static/src/components/fifo_reset_result/fifo_reset_result.xml',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
