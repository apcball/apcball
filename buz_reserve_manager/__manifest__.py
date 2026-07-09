{
    'name': 'Reserve Manager',
    'version': '17.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Sale Order stock reservation dashboard with schedule and policy control for Odoo 17.',
    'description': """
        A compact reservation console for Sales Orders:

        - Filter by sale order, customer, warehouse, product, date, and reservation status
        - Load delivery moves linked to sale order lines
        - Reserve and unreserve using standard Odoo stock methods
        - Apply a policy window to skip long-dated orders unless paid or force-overridden
        - Schedule reserve / unreserve actions from the same screen
        - Keep a clear summary bar and status badges for warehouse users
        - Log unreserve actions to stock.unreserve.log when that module is installed
    """,
    'author': 'Mogen Co., Ltd.',
    'website': '',
    'depends': [
        'sale_stock',
        'stock',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence.xml',
        'data/ir_cron.xml',
        'views/reserve_manager_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
