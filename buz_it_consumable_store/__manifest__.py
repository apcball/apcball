{
    'name': 'IT Consumable Request',
    'version': '17.0.1.2.0',
    'category': 'Services/IT',
    'summary': 'IT material requisition and issue workflow',
    'license': 'LGPL-3',
    'depends': ['buz_it_inventory_store', 'buz_it_helpdesk', 'hr', 'mail'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'views/store_action.xml',
        'views/request_views.xml',
        'views/wizard_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'buz_it_consumable_store/static/src/js/consumable_store.js',
            'buz_it_consumable_store/static/src/xml/consumable_store.xml',
            'buz_it_consumable_store/static/src/scss/consumable_store.scss',
        ],
    },
    'demo': [],
    'installable': True,
    'auto_install': False,
    'application': True,
}
