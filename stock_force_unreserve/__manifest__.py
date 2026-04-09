{
    'name': 'Stock Force Unreserve',
    'version': '17.0.1.0.0',
    'category': 'Inventory',
    'summary': 'Force unreserve stock from other pickings and reallocate',
    'depends': ['stock', 'web'],
    'data': [
        'security/stock_force_unreserve_groups.xml',
        'security/ir.model.access.csv',
        'views/stock_picking_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'stock_force_unreserve/static/src/js/force_unreserve_dialog.js',
            'stock_force_unreserve/static/src/xml/force_unreserve_dialog.xml',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
