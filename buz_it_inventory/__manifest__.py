{
    'name': 'IT Inventory Store',
    'version': '17.0.1.1.0',
    'category': 'Services/IT',
    'summary': 'IT inventory store for materials and equipment',
    'license': 'LGPL-3',
    'depends': ['buz_it_helpdesk'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/inventory_item_views.xml',
        'views/stock_views.xml',
        'views/wizard_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': True,
}
