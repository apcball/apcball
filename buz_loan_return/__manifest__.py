{
    'name': 'Show Loan and Return',
    'version': '17.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Track show-loan transfers and linked returns',
    'depends': ['stock', 'buz_inventory_delivery_report', 'buz_tag_inventory'],
    'data': [
        'security/ir.model.access.csv',
        'wizard/loan_wizard_views.xml',
        'wizard/return_wizard_views.xml',
        'views/loan_return_views.xml',
        'views/loan_return_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'buz_loan_return/static/src/js/loan_return_list_view.js',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
