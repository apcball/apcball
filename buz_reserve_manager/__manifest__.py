{
    'name': 'Reserve Manager',
    'version': '17.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Manage stock reservations linked to Sale Orders — view, manual reserve, and unreserve in one page.',
    'description': """
        Provides a single-page dashboard for managing stock reservations tied to Sales Orders:

        - Select Sale Orders, date range, and products to filter
        - Load reservation data from stock.moves linked to SO lines
        - View demand qty, reserved qty, available stock per product
        - Manual Reserve: force-assign stock to a specific SO line
        - Unreserve: release stock from a single line or entire SO
        - Summary totals and status badges for quick overview
        - Full integration with stock.unreserve.log audit trail (if stock_unreserve_manager is installed)
    """,
    'author': 'Mogen Co., Ltd.',
    'website': '',
    'depends': [
        'sale',
        'stock',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence.xml',
        'views/reserve_manager_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
