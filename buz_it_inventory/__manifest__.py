{
    'name': 'IT Inventory Store',
    'version': '17.0.1.4.0',
    'category': 'Services/IT',
    'summary': 'IT inventory store for materials and equipment',
    'license': 'LGPL-3',
    'depends': ['buz_it_helpdesk'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'views/inventory_item_views.xml',
        'views/issue_request_views.xml',
        'views/stock_views.xml',
        'views/wizard_views.xml',
        'views/store_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'buz_it_inventory/static/src/js/it_store.js',
            'buz_it_inventory/static/src/xml/it_store.xml',
            'buz_it_inventory/static/src/scss/it_store.scss',
        ],
    },
    'installable': True,
    'auto_install': False,
    'application': True,
}
