{
    'name': 'Show Loan',
    'version': '17.0.1.0.0',
    'category': 'Inventory',
    'license': 'LGPL-3',
    'depends': ['stock', 'mail', 'buz_tag_inventory'],
    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        'views/show_loan_views.xml',
        'wizard/show_loan_return_views.xml',
        'views/stock_picking_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': False,
}
