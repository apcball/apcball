{
    'name': 'IT Issue Mobile',
    'summary': 'Mobile IT equipment issue, employee signature and stock consumption',
    'version': '17.0.1.2.0',
    'category': 'Inventory/Inventory',
    'author': 'Mogen Co., Ltd.',
    'license': 'LGPL-3',
    'depends': ['stock', 'hr', 'mail', 'web', 'employee_purchase_requisition'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/categories.xml',
        'views/config_views.xml',
        'views/product_views.xml',
        'views/issue_views.xml',
        'views/replenishment_views.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'buz_it_stock_mobile/static/src/issue_app.js',
            'buz_it_stock_mobile/static/src/issue_app.xml',
            'buz_it_stock_mobile/static/src/issue_app.scss',
            'buz_it_stock_mobile/static/src/low_stock.scss',
        ],
        'web.qunit_suite_tests': [
            'buz_it_stock_mobile/static/tests/issue_app_tests.js',
        ],
    },
    'application': True,
    'installable': True,
}
